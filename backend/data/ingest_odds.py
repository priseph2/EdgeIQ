"""
Live odds ingestion via The Odds API.
Runs every 60s via APScheduler.
Stores current odds + snapshot history.
Triggers arb detection and value bet scanner after each update.

Usage (one-shot):
  python -m data.ingest_odds

Cron is handled by scheduler.py.
"""

import asyncio
import httpx
import logging
from datetime import datetime, timezone
from supabase import create_client
from config import get_settings

logger = logging.getLogger(__name__)

ODDS_API_BASE = "https://api.the-odds-api.com/v4"

# Sports keys used by The Odds API
SPORT_KEYS = [
    "basketball_nba",
    "soccer_epl",
    "soccer_spain_la_liga",
    "soccer_germany_bundesliga",
    "soccer_italy_serie_a",
    "soccer_france_ligue_one",
]

# Nigerian-accessible bookmakers + Pinnacle as sharp benchmark
BOOKMAKERS = [
    "pinnacle",
    "betway",
    "onexbet",    # 1xBet
    "sport888",
    "unibet",
    "williamhill",
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
    logger.info(f"{sport_key}: {len(r.json())} events | {remaining} requests remaining")
    return r.json()


def find_match_uuid(supabase, external_event_id: str, home_name: str, away_name: str) -> str | None:
    res = supabase.table("matches").select("id").eq("external_id", f"odds:{external_event_id}").execute()
    if res.data:
        return res.data[0]["id"]

    res = supabase.table("matches").select("id, home_team:teams!home_team_id(name), away_team:teams!away_team_id(name)")\
        .eq("status", "scheduled").execute()
    for row in (res.data or []):
        ht = row.get("home_team", {}).get("name", "").lower()
        at = row.get("away_team", {}).get("name", "").lower()
        if home_name.lower() in ht or ht in home_name.lower():
            if away_name.lower() in at or at in away_name.lower():
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
    match_uuid = find_match_uuid(supabase, event["id"], home_name, away_name)
    if not match_uuid:
        return

    now = datetime.now(timezone.utc).isoformat()
    odds_rows = []
    history_rows = []

    for bm in event.get("bookmakers", []):
        for market in bm.get("markets", []):
            if market["key"] != "h2h":
                continue
            parsed = parse_h2h_outcomes(market["outcomes"], home_name, away_name)
            row = {
                "match_id": match_uuid,
                "bookmaker": bm["key"],
                "market": "h2h",
                "home_odds": parsed["home"],
                "draw_odds": parsed["draw"],
                "away_odds": parsed["away"],
                "recorded_at": now,
            }
            odds_rows.append(row)
            history_rows.append({**row, "snapshot_at": now})

    if odds_rows:
        supabase.table("odds").upsert(odds_rows, on_conflict="match_id,bookmaker,market").execute()
        supabase.table("odds_history").insert(history_rows).execute()


def detect_arb(supabase, match_uuid: str):
    res = supabase.table("odds").select("*").eq("match_id", match_uuid).execute()
    rows = res.data or []
    if not rows:
        return

    best_home = max((r["home_odds"] or 0, r["bookmaker"]) for r in rows if r["home_odds"])
    best_away = max((r["away_odds"] or 0, r["bookmaker"]) for r in rows if r["away_odds"])
    draw_rows = [r for r in rows if r["draw_odds"]]
    best_draw = max((r["draw_odds"] or 0, r["bookmaker"]) for r in draw_rows) if draw_rows else (0, None)

    h, hb = best_home
    a, ab = best_away
    d, db = best_draw

    margin = 1/h + 1/a + (1/d if d else 0) if h and a else 1.0
    if margin < 1.0:
        profit_pct = (1 - margin) * 100
        total_stake = 1000
        stakes = {
            "home": round(total_stake / (h * margin), 2),
            "away": round(total_stake / (a * margin), 2),
        }
        if d:
            stakes["draw"] = round(total_stake / (d * margin), 2)

        supabase.table("arb_alerts").insert({
            "match_id": match_uuid,
            "profit_pct": round(profit_pct, 4),
            "stakes_json": stakes,
            "best_home_book": hb,
            "best_draw_book": db,
            "best_away_book": ab,
            "notified": False,
        }).execute()
        logger.info(f"ARB FOUND match={match_uuid} profit={profit_pct:.2f}%")


async def run_once():
    logging.basicConfig(level=logging.INFO)
    supabase = get_supabase()

    async with httpx.AsyncClient(timeout=30) as client:
        for sport_key in SPORT_KEYS:
            try:
                events = await fetch_odds(client, sport_key)
                for event in events:
                    await process_event(supabase, event)
                    detect_arb(supabase, event["id"])
                await asyncio.sleep(1)
            except Exception as e:
                logger.error(f"Odds ingestion failed for {sport_key}: {e}")


if __name__ == "__main__":
    asyncio.run(run_once())
