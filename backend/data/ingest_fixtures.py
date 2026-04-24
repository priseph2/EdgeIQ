"""
Quick fixture refresh — fetches only the current matchday for each Top 5 league.
Much faster than full ingest (no historical seasons, no stats).
Run whenever you need to refresh upcoming match schedule.

Usage:
  python -m data.ingest_fixtures
"""

import asyncio
import httpx
import logging
from datetime import datetime
from typing import Optional
from supabase import create_client
from config import get_settings
from data.ingest_football import (
    LEAGUE_CODES, SPORT, get_fd_headers, get_supabase,
    parse_fd_match, upsert_team,
)

logger = logging.getLogger(__name__)

FD_BASE = "https://api.football-data.org/v4"


async def fetch_matchday(client: httpx.AsyncClient, competition_code: str) -> list[dict]:
    """Fetch the current matchday fixtures from football-data.org."""
    url = f"{FD_BASE}/competitions/{competition_code}/matches"
    r = await client.get(url, params={"status": "SCHEDULED"}, headers=get_fd_headers())
    if r.status_code == 429:
        logger.warning("Rate limited, sleeping 65s...")
        await asyncio.sleep(65)
        r = await client.get(url, params={"status": "SCHEDULED"}, headers=get_fd_headers())
    if r.status_code != 200:
        logger.warning(f"{competition_code}: HTTP {r.status_code}")
        return []
    return r.json().get("matches", [])


async def refresh_league(competition_code: str, league_name: str, supabase):
    logger.info(f"Refreshing fixtures for {league_name}...")
    team_cache: dict[str, str] = {}
    async with httpx.AsyncClient(timeout=30) as client:
        matches = await fetch_matchday(client, competition_code)
        await asyncio.sleep(7)  # respect 10 req/min free tier rate limit

    upserted = 0
    for match in matches:
        row = parse_fd_match(match, league_name, team_cache, supabase)
        if not row:
            continue
        supabase.table("matches").upsert(row, on_conflict="sport,external_id").execute()
        upserted += 1

    logger.info(f"{league_name}: {upserted} fixtures upserted")


async def run():
    logging.basicConfig(level=logging.INFO)
    supabase = get_supabase()
    for code, name in LEAGUE_CODES.items():
        try:
            await refresh_league(code, name, supabase)
        except Exception as e:
            logger.error(f"Failed {name}: {e}")
    logger.info("Fixture refresh complete")


if __name__ == "__main__":
    asyncio.run(run())
