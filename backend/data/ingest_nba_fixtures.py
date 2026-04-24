"""
Quick NBA fixture refresh — fetches upcoming games for the next 14 days.
Much faster than full ingest (no historical seasons, just upcoming schedule).

Usage:
  python -m data.ingest_nba_fixtures
"""

import asyncio
import httpx
import logging
from datetime import datetime, timedelta, timezone
from data.ingest_nba import (
    BALLDONTLIE_BASE, LEAGUE, SPORT, get_supabase,
    upsert_teams, upsert_match, _headers,
)
from config import get_settings

logger = logging.getLogger(__name__)


async def fetch_upcoming_games(client: httpx.AsyncClient, start: str, end: str) -> list[dict]:
    games = []
    page = 1
    while True:
        params = {"start_date": start, "end_date": end, "per_page": 100, "page": page}
        r = await client.get(f"{BALLDONTLIE_BASE}/games", params=params, headers=_headers())
        if r.status_code == 429:
            logger.warning("Rate limited, sleeping 60s...")
            await asyncio.sleep(60)
            continue
        if r.status_code != 200:
            logger.warning(f"HTTP {r.status_code} fetching upcoming games")
            break
        data = r.json()
        batch = data.get("data", [])
        games.extend(batch)
        meta = data.get("meta", {})
        if page >= meta.get("total_pages", 1) or not batch:
            break
        page += 1
        await asyncio.sleep(1.0)
    return games


async def run():
    logging.basicConfig(level=logging.INFO)
    supabase = get_supabase()

    now = datetime.now(timezone.utc)
    start = now.strftime("%Y-%m-%d")
    end = (now + timedelta(days=14)).strftime("%Y-%m-%d")
    logger.info(f"Fetching NBA games {start} → {end}...")

    async with httpx.AsyncClient(timeout=60) as client:
        # Fetch all teams first so we have the ID map
        from data.ingest_nba import fetch_all_teams
        raw_teams = await fetch_all_teams(client)

    team_id_map = upsert_teams(supabase, raw_teams)
    logger.info(f"Teams ready: {len(team_id_map)}")

    async with httpx.AsyncClient(timeout=60) as client:
        games = await fetch_upcoming_games(client, start, end)

    upserted = 0
    for game in games:
        match_uuid = upsert_match(supabase, game, team_id_map)
        if match_uuid:
            upserted += 1

    logger.info(f"NBA fixture refresh complete: {upserted} matches upserted")


if __name__ == "__main__":
    asyncio.run(run())
