"""
EdgeIQ Telegram Bot.

Commands:
  /start          — register + welcome message
  /today          — today's predictions digest
  /value          — value bets only
  /predict <team> — prediction for a team's next match
  /stats          — model performance stats
  /help           — command list

Daily digest sent at 9am Africa/Lagos via scheduler.py.
Value bets and arb alerts pushed immediately via send_alert().

Run standalone: python telegram_bot.py
"""

import asyncio
import logging
import os
from datetime import datetime, timezone
import pytz
from telegram import Update, BotCommand
from telegram.ext import Application, CommandHandler, ContextTypes
from telegram.constants import ParseMode

from config import get_settings
from db import get_supabase

logger = logging.getLogger(__name__)
LAGOS_TZ = pytz.timezone("Africa/Lagos")

CONF_EMOJI = {"high": "🟢", "medium": "🟡", "low": "🔴"}
SPORT_EMOJI = {"basketball": "🏀", "football": "⚽"}


def _build_prediction_text(p: dict) -> str:
    sport_e = SPORT_EMOJI.get(p.get("sport", ""), "🎯")
    conf_e = CONF_EMOJI.get(p.get("confidence", "low"), "⚪")
    value_tag = " 💰 *VALUE BET*" if p.get("value_flag") else ""

    home = p.get("home_team", "Home")
    away = p.get("away_team", "Away")
    league = p.get("league", "")
    pick = p.get("pick", "").upper()
    home_prob = p.get("home_prob", 0)
    away_prob = p.get("away_prob", 0)
    draw_prob = p.get("draw_prob")
    home_odds = p.get("best_home_odds")
    away_odds = p.get("best_away_odds")
    draw_odds = p.get("best_draw_odds")

    text = f"{sport_e} *{home} vs {away}*\n"
    text += f"_{league}_\n"
    text += f"{conf_e} Pick: *{pick}*{value_tag}\n"

    probs = f"H {home_prob*100:.1f}%"
    if draw_prob is not None:
        probs += f" · D {draw_prob*100:.1f}%"
    probs += f" · A {away_prob*100:.1f}%"
    text += f"`{probs}`\n"

    if home_odds or away_odds:
        odds_str = f"Odds → H:{home_odds:.2f}" if home_odds else "Odds → H:–"
        if draw_odds:
            odds_str += f" D:{draw_odds:.2f}"
        if away_odds:
            odds_str += f" A:{away_odds:.2f}"
        text += f"_{odds_str}_\n"

    return text


async def fetch_today_predictions(sport: str | None = None) -> list[dict]:
    import httpx
    base = get_settings().backend_url
    url = f"{base}/predictions/today"
    if sport:
        url += f"?sport={sport}"
    try:
        async with httpx.AsyncClient(timeout=30) as client:
            r = await client.get(url)
            r.raise_for_status()
            return r.json()
    except Exception as e:
        logger.error(f"Failed to fetch predictions: {e}")
        return []


async def cmd_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat_id = str(update.effective_chat.id)
    supabase = get_supabase()
    supabase.table("users").upsert(
        {"telegram_chat_id": chat_id, "email": f"telegram_{chat_id}@edgeiq.app"},
        on_conflict="telegram_chat_id"
    ).execute()

    await update.message.reply_text(
        "👋 Welcome to *EdgeIQ*!\n\n"
        "Your personal sports betting intelligence tool.\n\n"
        "Commands:\n"
        "/today — today's predictions\n"
        "/value — value bets only\n"
        "/predict <team> — predict a team's next match\n"
        "/stats — model performance\n"
        "/help — this menu",
        parse_mode=ParseMode.MARKDOWN,
    )


async def cmd_today(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("Fetching today's predictions…")
    preds = await fetch_today_predictions()

    if not preds:
        await update.message.reply_text("No predictions available yet. Make sure the backend is running and models are trained.")
        return

    value = [p for p in preds if p.get("value_flag")]
    high_conf = [p for p in preds if p.get("confidence") == "high" and not p.get("value_flag")]
    rest = [p for p in preds if p.get("confidence") != "high" and not p.get("value_flag")]

    now_lagos = datetime.now(LAGOS_TZ).strftime("%a %d %b, %I:%M %p")
    header = f"📊 *EdgeIQ Daily Intel* — {now_lagos}\n{len(preds)} matches analysed\n\n"

    sections = []
    if value:
        block = "💰 *VALUE BETS*\n" + "─" * 20 + "\n"
        block += "\n".join(_build_prediction_text(p) for p in value)
        sections.append(block)

    if high_conf:
        block = "🟢 *HIGH CONFIDENCE*\n" + "─" * 20 + "\n"
        block += "\n".join(_build_prediction_text(p) for p in high_conf[:5])
        sections.append(block)

    if rest:
        block = "📌 *OTHER PICKS*\n" + "─" * 20 + "\n"
        block += "\n".join(_build_prediction_text(p) for p in rest[:5])
        sections.append(block)

    full_msg = header + "\n\n".join(sections)

    # Telegram has a 4096 char limit — split if needed
    for i in range(0, len(full_msg), 4000):
        await update.message.reply_text(full_msg[i:i+4000], parse_mode=ParseMode.MARKDOWN)


async def cmd_value(update: Update, context: ContextTypes.DEFAULT_TYPE):
    preds = await fetch_today_predictions()
    value = [p for p in preds if p.get("value_flag")]
    if not value:
        await update.message.reply_text("No value bets detected today. The market is efficient right now.")
        return
    msg = f"💰 *{len(value)} Value Bet(s) Today*\n\n"
    msg += "\n".join(_build_prediction_text(p) for p in value)
    await update.message.reply_text(msg, parse_mode=ParseMode.MARKDOWN)


async def cmd_predict(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not context.args:
        await update.message.reply_text("Usage: /predict <team name>\nExample: /predict Lakers")
        return
    team_query = " ".join(context.args).lower()
    preds = await fetch_today_predictions()
    matches = [
        p for p in preds
        if team_query in p.get("home_team", "").lower() or team_query in p.get("away_team", "").lower()
    ]
    if not matches:
        await update.message.reply_text(f"No match found for '{' '.join(context.args)}' today.")
        return
    msg = "\n\n".join(_build_prediction_text(p) for p in matches)
    await update.message.reply_text(msg, parse_mode=ParseMode.MARKDOWN)


async def cmd_stats(update: Update, context: ContextTypes.DEFAULT_TYPE):
    import httpx
    base = get_settings().backend_url
    try:
        async with httpx.AsyncClient(timeout=10) as client:
            r = await client.get(f"{base}/predictions/model/stats")
            stats = r.json()
    except Exception:
        await update.message.reply_text("Could not fetch model stats. Is the backend running?")
        return

    if not stats:
        await update.message.reply_text("No trained models found. Run: python -m ml.train --sport all")
        return

    msg = "📈 *Model Performance*\n\n"
    for sport, s in stats.items():
        msg += f"*{sport.capitalize()}*\n"
        msg += f"  Accuracy: {(s.get('accuracy', 0)*100):.1f}%\n"
        msg += f"  Brier:    {s.get('brier_score', 0):.3f}\n"
        msg += f"  AUC:      {s.get('auc', 0):.3f}\n"
        msg += f"  Trained:  {s.get('trained_at', 'N/A')[:10]}\n\n"
    await update.message.reply_text(msg, parse_mode=ParseMode.MARKDOWN)


async def cmd_help(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "📖 *EdgeIQ Commands*\n\n"
        "/today — All predictions for today\n"
        "/value — Value bets only\n"
        "/predict <team> — Lookup a team's match\n"
        "/stats — Model accuracy & Brier score\n"
        "/help — This menu",
        parse_mode=ParseMode.MARKDOWN,
    )


async def send_daily_digest():
    """Called by scheduler at 9am Lagos time."""
    s = get_settings()
    if not s.telegram_bot_token or not s.telegram_chat_id:
        logger.warning("Telegram not configured — skipping daily digest")
        return

    preds = await fetch_today_predictions()
    if not preds:
        return

    value = [p for p in preds if p.get("value_flag")]
    high_conf = [p for p in preds if p.get("confidence") == "high"]

    now_lagos = datetime.now(LAGOS_TZ).strftime("%a %d %b")
    msg = f"📊 *EdgeIQ Morning Intel — {now_lagos}*\n"
    msg += f"{len(preds)} matches | {len(value)} value bets | {len(high_conf)} high confidence\n\n"

    if value:
        msg += "💰 *VALUE BETS TODAY:*\n"
        for p in value:
            msg += _build_prediction_text(p) + "\n"

    if high_conf:
        msg += "🟢 *HIGH CONFIDENCE PICKS:*\n"
        for p in high_conf[:3]:
            msg += _build_prediction_text(p) + "\n"

    app = Application.builder().token(s.telegram_bot_token).build()
    async with app:
        await app.bot.send_message(
            chat_id=s.telegram_chat_id,
            text=msg,
            parse_mode=ParseMode.MARKDOWN,
        )
    logger.info(f"Daily digest sent to {s.telegram_chat_id}")


async def send_alert(alert_type: str, message: str):
    """Send immediate alert (value bet found, arb found)."""
    s = get_settings()
    if not s.telegram_bot_token or not s.telegram_chat_id:
        return
    app = Application.builder().token(s.telegram_bot_token).build()
    async with app:
        await app.bot.send_message(
            chat_id=s.telegram_chat_id,
            text=message,
            parse_mode=ParseMode.MARKDOWN,
        )


def run_bot():
    logging.basicConfig(level=logging.INFO)
    s = get_settings()
    if not s.telegram_bot_token:
        logger.error("TELEGRAM_BOT_TOKEN not set")
        return

    app = Application.builder().token(s.telegram_bot_token).build()
    app.add_handler(CommandHandler("start", cmd_start))
    app.add_handler(CommandHandler("today", cmd_today))
    app.add_handler(CommandHandler("value", cmd_value))
    app.add_handler(CommandHandler("predict", cmd_predict))
    app.add_handler(CommandHandler("stats", cmd_stats))
    app.add_handler(CommandHandler("help", cmd_help))

    logger.info("EdgeIQ Telegram bot starting...")
    app.run_polling(allowed_updates=Update.ALL_TYPES)


if __name__ == "__main__":
    run_bot()
