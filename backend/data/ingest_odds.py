"""
Live odds ingestion via The Odds API.
Runs 3x/day via APScheduler to stay within 500 req/month free tier.
Triggers arb detection and value bet scanner after each update.

Usage (one-shot):
  python -m data.ingest_odds
"""

import asyncio
import httpx
import logging
from datetime import datetime, timezone
from supabase import create_client
from config import get_settings

logger = logging.getLogger(__name__)

ODDS_API_BASE = "https://api.the-odds-api.com/v4"

SPORT_KEYS = [
    "basketball_nba",
    "soccer_epl",
    "soccer_spain_la_liga",
    "soccer_germany_bundesliga",
    "soccer_italy_serie_a",
    "soccer_france_ligue_one",
]

BOOKMAKERS = [
    "pinnacle",
    "betway",
    "onexbet",
    "unibet",
    "williamhill",
    "bet365",
]


def get_supabase():
    s = get_settings()
    return create_client(s.supabase_url, s.supabase_service_role_key)


async def fetch_odds(client: httpx.AsyncClient, sport_key: str) -> list[dict]:
    params = {
        "apiKey": get_settings().odds_api_key,
        "regions": "eu,uk",
        "markets": "h2h",
        "oddsFormat": "decimal",
        "bookmakers": ",".join(BOOKMAKERS),
    }
    r = await client.get(f"{ODDS_API_BASE}/sports/{sport_key}/odds", params=params)
    if r.status_code == 422:
        return []
    r.raise_for_status()
    remaining = r.headers.get("x-requests-remaining", "?")
    used = r.headers.get("x-requests-used", "?")
    logger.info(f"{sport_key}: {len(r.json())} events | used={used} remaining={remaining}")
    return r.json()


def find_match_uuid(supabase, home_name: str, away_name: str) -> str | None:
    """Fuzzy-match Odds API team names to our DB matches."""
    res = supabase.table("matches").select(
        "id, home_team:teams!home_team_id(name), away_team:teams!away_team_id(name)"
    ).eq("status", "scheduled").execute()

    for row in (res.data or []):
        ht = (row.get("home_team") or {}).get("name", "").lower()
        at = (row.get("away_team") or {}).get("name", "").lower()
        hn = home_name.lower()
        an = away_name.lower()
        if (hn in ht or ht in hn) and (an in at or at in an):
            return row["id"]
    return None


def parse_h2h_outcomes(outcomes: list[dict], home_name: str, away_name: str) -> dict:
    result = {"home": None, "draw": None, "away": None}
    for o in outcomes:
        n = o["name"].lower()
        if n == "draw":
            result["draw"] = o["price"]
        elif home_name.lower() in n or n in home_name.lower():
            result["home"] = o["price"]
        else:
            result["away"] = o["price"]
    return result


async def process_event(supabase, event: dict):
    home_name = event["home_team"]
    away_name = event["away_team"]
    match_uuid = find_match_uuid(supabase, home_name, away_name)
    if not match_uuid:
        return

    now = datetime.now(timezone.utc).isoformat()
    odds_rows = []

    for bm in event.get("bookmakers", []):
        for market in bm.get("markets", []):
            if market["key"] != "h2h":
                continue
            parsed = parse_h2h_outcomes(market["outcomes"], home_name, away_name)
            odds_rows.append({
                "match_id": match_uuid,
                "bookmaker": bm["key"],
                "market": "h2h",
                "home_odds": parsed["home"],
                "draw_odds": parsed["draw"],
                "away_odds": parsed["away"],
                "recorded_at": now,
            })

    if odds_rows:
        supabase.table("odds").upsert(odds_rows, on_conflict="match_id,bookmaker,market").execute()
        supabase.table("odds_history").insert(odds_rows).execute()
        detect_arb(supabase, match_uuid)
        detect_value_bets(supabase, match_uuid)


def detect_arb(supabase, match_uuid: str):
    rows = supabase.table("odds").select("*").eq("match_id", match_uuid).execute().data or []
    if not rows:
        return

    home_opts = [(r["home_odds"], r["bookmaker"]) for r in rows if r.get("home_odds")]
    away_opts = [(r["away_odds"], r["bookmaker"]) for r in rows if r.get("away_odds")]
    draw_opts = [(r["draw_odds"], r["bookmaker"]) for r in rows if r.get("draw_odds")]

    if not home_opts or not away_opts:
        return

    h, hb = max(home_opts)
    a, ab = max(away_opts)
    d, db = max(draw_opts) if draw_opts else (0, None)

    margin = 1/h + 1/a + (1/d if d else 0)
    if margin < 1.0:
        profit_pct = (1 - margin) * 100
        total = 1000
        stakes = {
            "home": {"stake": round(total / (h * margin), 2), "book": hb},
            "away": {"stake": round(total / (a * margin), 2), "book": ab},
        }
        if d:
            stakes["draw"] = {"stake": round(total / (d * margin), 2), "book": db}

        supabase.table("arb_alerts").insert({
            "match_id": match_uuid,
            "profit_pct": round(profit_pct, 4),
            "stakes_json": stakes,
            "notified": False,
        }).execute()
        logger.info(f"ARB FOUND match={match_uuid} profit={profit_pct:.2f}%")


def detect_value_bets(supabase, match_uuid: str):
    pred_res = supabase.table("predictions").select("*").eq("match_id", match_uuid)\
        .order("created_at", desc=True).limit(1).execute()
    if not pred_res.data:
        return
    pred = pred_res.data[0]

    rows = supabase.table("odds").select("*").eq("match_id", match_uuid).execute().data or []
    if not rows:
        return

    best_home = max((r["home_odds"] for r in rows if r.get("home_odds")), default=0)
    best_draw = max((r["draw_odds"] for r in rows if r.get("draw_odds")), default=0)
    best_away = max((r["away_odds"] for r in rows if r.get("away_odds")), default=0)

    threshold = 0.05
    for selection, model_prob, odds in [
        ("home", pred.get("home_prob"), best_home),
        ("draw", pred.get("draw_prob"), best_draw),
        ("away", pred.get("away_prob"), best_away),
    ]:
        if not model_prob or not odds or odds <= 1.0:
            continue
        market_prob = 1.0 / odds
        edge = model_prob - market_prob
        if edge >= threshold:
            supabase.table("value_bets").insert({
                "match_id": match_uuid,
                "selection": selection,
                "edge_pct": round(edge * 100, 2),
                "model_prob": round(model_prob, 4),
                "market_prob": round(market_prob, 4),
                "best_odds": odds,
                "notified": False,
            }).execute()
            logger.info(f"VALUE BET: {match_uuid} {selection} edge={edge*100:.1f}%")


async def run_once():
    supabase = get_supabase()
    async with httpx.AsyncClient(timeout=30) as client:
        for sport_key in SPORT_KEYS:
            try:
                events = await fetch_odds(client, sport_key)
                for event in events:
                    await process_event(supabase, event)
                await asyncio.sleep(2)
            except Exception as e:
                logger.error(f"Odds ingestion failed for {sport_key}: {e}")
    logger.info("Odds ingestion complete")


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    asyncio.run(run_once())
