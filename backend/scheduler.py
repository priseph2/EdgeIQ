"""
APScheduler cron jobs:
  - Every 60s: ingest live odds
  - Every Sunday 3am: retrain models
  - Every day 9am Africa/Lagos: send Telegram daily digest
  - Every 5 min: settle finished matches (update bet P&L)

Run standalone: python scheduler.py
Or import and start from main.py.
"""

import asyncio
import logging
from datetime import datetime, timezone
import pytz
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.cron import CronTrigger
from apscheduler.triggers.interval import IntervalTrigger

logger = logging.getLogger(__name__)

LAGOS_TZ = pytz.timezone("Africa/Lagos")


async def job_ingest_odds():
    from data.ingest_odds import run_once
    try:
        await run_once()
    except Exception as e:
        logger.error(f"Odds ingestion job failed: {e}")


async def job_retrain_models():
    import subprocess
    import sys
    logger.info("Starting weekly model retraining...")
    try:
        result = subprocess.run(
            [sys.executable, "-m", "ml.train", "--sport", "all"],
            capture_output=True, text=True, timeout=3600
        )
        logger.info(f"Retraining complete: {result.stdout[-500:]}")
        if result.returncode != 0:
            logger.error(f"Retraining failed: {result.stderr[-500:]}")
    except Exception as e:
        logger.error(f"Retraining job failed: {e}")


async def job_daily_digest():
    from telegram_bot import send_daily_digest
    try:
        await send_daily_digest()
    except Exception as e:
        logger.error(f"Daily digest job failed: {e}")


async def job_settle_bets():
    """Auto-settle bets for finished matches."""
    from db import get_supabase
    supabase = get_supabase()
    try:
        pending = supabase.table("bets").select("id, match_id, odds, stake")\
            .eq("status", "pending").execute()
        for bet in (pending.data or []):
            match = supabase.table("matches").select("result, status")\
                .eq("id", bet["match_id"]).single().execute()
            if not match.data or match.data["status"] != "finished":
                continue
            result = match.data.get("result")
            if not result:
                continue
            # Map selection to result (simplified — assumes selection = "home"/"draw"/"away")
            bet_sel = supabase.table("bets").select("selection").eq("id", bet["id"]).single().execute()
            selection = bet_sel.data.get("selection", "").lower() if bet_sel.data else ""

            if selection == result:
                pnl = round((bet["odds"] - 1) * bet["stake"], 2)
                status = "won"
            else:
                pnl = round(-bet["stake"], 2)
                status = "lost"

            supabase.table("bets").update({
                "status": status,
                "pnl": pnl,
                "settled_at": datetime.now(timezone.utc).isoformat(),
            }).eq("id", bet["id"]).execute()
            logger.info(f"Settled bet {bet['id']}: {status} PnL={pnl}")
    except Exception as e:
        logger.error(f"Bet settlement job failed: {e}")


def create_scheduler() -> AsyncIOScheduler:
    scheduler = AsyncIOScheduler(timezone=str(LAGOS_TZ))

    # Odds ingestion every 60 seconds
    scheduler.add_job(job_ingest_odds, IntervalTrigger(seconds=60), id="ingest_odds")

    # Model retraining every Sunday at 3am Lagos time
    scheduler.add_job(
        job_retrain_models,
        CronTrigger(day_of_week="sun", hour=3, minute=0, timezone=LAGOS_TZ),
        id="retrain_models"
    )

    # Daily digest at 9am Lagos time
    scheduler.add_job(
        job_daily_digest,
        CronTrigger(hour=9, minute=0, timezone=LAGOS_TZ),
        id="daily_digest"
    )

    # Bet settlement every 5 minutes
    scheduler.add_job(job_settle_bets, IntervalTrigger(minutes=5), id="settle_bets")

    return scheduler


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    scheduler = create_scheduler()
    scheduler.start()
    logger.info("Scheduler running. Press Ctrl+C to stop.")
    try:
        asyncio.get_event_loop().run_forever()
    except (KeyboardInterrupt, SystemExit):
        pass
