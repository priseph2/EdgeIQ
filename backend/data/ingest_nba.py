"""
NBA data ingestion via BallDontLie API (free, no key required).
Fetches game results + box scores for last 3 seasons.
Stores into Supabase: teams, matches, team_stats_basketball.

Usage:
  python -m data.ingest_nba
"""

import asyncio
import httpx
import logging
from datetime import datetime, date
from typing import Optional
from supabase import create_client
from config import get_settings

logger = logging.getLogger(__name__)

BALLDONTLIE_BASE = "https://api.balldontlie.io/v1"
LEAGUE = "NBA"
SPORT = "basketball"


def _current_nba_seasons() -> list[int]:
    now = datetime.utcnow()
    # NBA season starts in October; season label = start year
    current = now.year if now.month >= 10 else now.year - 1
    return [current - 2, current - 1, current]


def get_supabase():
    s = get_settings()
    return create_client(s.supabase_url, s.supabase_service_role_key)


async def fetch_all_teams(client: httpx.AsyncClient) -> list[dict]:
    teams = []
    cursor = None
    while True:
        params = {"per_page": 100}
        if cursor:
            params["cursor"] = cursor
        r = await client.get(f"{BALLDONTLIE_BASE}/teams", params=params)
        r.raise_for_status()
        data = r.json()
        teams.extend(data.get("data", []))
        cursor = data.get("meta", {}).get("next_cursor")
        if not cursor:
            break
    return teams


async def fetch_games(client: httpx.AsyncClient, season: int, page: int = 1) -> dict:
    params = {"seasons[]": season, "per_page": 100, "page": page}
    r = await client.get(f"{BALLDONTLIE_BASE}/games", params=params)
    r.raise_for_status()
    return r.json()


async def fetch_box_scores(client: httpx.AsyncClient, game_id: int) -> dict:
    r = await client.get(f"{BALLDONTLIE_BASE}/box_scores/live", params={"game_ids[]": game_id})
    if r.status_code == 200:
        return r.json()
    return {}


def upsert_teams(supabase, raw_teams: list[dict]) -> dict[int, str]:
    """Upsert teams and return {external_id: uuid} mapping."""
    rows = [
        {
            "name": t["full_name"],
            "short_name": t["abbreviation"],
            "sport": SPORT,
            "league": LEAGUE,
            "external_id": str(t["id"]),
        }
        for t in raw_teams
    ]
    result = supabase.table("teams").upsert(rows, on_conflict="sport,external_id").execute()
    id_map = {}
    for row in result.data:
        id_map[row["external_id"]] = row["id"]
    return id_map


def upsert_match(supabase, game: dict, team_id_map: dict[str, str]) -> Optional[str]:
    home_ext = str(game["home_team"]["id"])
    away_ext = str(game["visitor_team"]["id"])
    home_uuid = team_id_map.get(home_ext)
    away_uuid = team_id_map.get(away_ext)
    if not home_uuid or not away_uuid:
        return None

    home_score = game.get("home_team_score")
    away_score = game.get("visitor_team_score")
    result = None
    if home_score is not None and away_score is not None and game["status"] == "Final":
        result = "home" if home_score > away_score else "away"

    row = {
        "home_team_id": home_uuid,
        "away_team_id": away_uuid,
        "sport": SPORT,
        "league": LEAGUE,
        "start_time": game["date"] + "T00:00:00Z",
        "status": "finished" if game["status"] == "Final" else "scheduled",
        "home_score": home_score,
        "away_score": away_score,
        "result": result,
        "draw_possible": False,
        "external_id": str(game["id"]),
    }
    res = supabase.table("matches").upsert(row, on_conflict="sport,external_id").execute()
    if res.data:
        return res.data[0]["id"]
    return None


def upsert_stats(supabase, match_uuid: str, game: dict, team_id_map: dict[str, str]):
    home_ext = str(game["home_team"]["id"])
    away_ext = str(game["visitor_team"]["id"])
    if game.get("home_team_score") is None:
        return

    stats = [
        {
            "team_id": team_id_map[home_ext],
            "match_id": match_uuid,
            "is_home": True,
            "points": game.get("home_team_score"),
            "opp_points": game.get("visitor_team_score"),
        },
        {
            "team_id": team_id_map[away_ext],
            "match_id": match_uuid,
            "is_home": False,
            "points": game.get("visitor_team_score"),
            "opp_points": game.get("home_team_score"),
        },
    ]
    supabase.table("team_stats_basketball").upsert(stats).execute()


async def ingest_season(season: int, team_id_map: dict[str, str], supabase):
    logger.info(f"Ingesting NBA season {season}...")
    async with httpx.AsyncClient(timeout=30) as client:
        page = 1
        total_games = 0
        while True:
            data = await fetch_games(client, season, page)
            games = data.get("data", [])
            if not games:
                break

            for game in games:
                match_uuid = upsert_match(supabase, game, team_id_map)
                if match_uuid and game.get("home_team_score"):
                    upsert_stats(supabase, match_uuid, game, team_id_map)
                    total_games += 1

            meta = data.get("meta", {})
            if page >= meta.get("total_pages", 1):
                break
            page += 1

            await asyncio.sleep(0.2)

        logger.info(f"Season {season}: {total_games} games ingested")


async def run():
    logging.basicConfig(level=logging.INFO)
    supabase = get_supabase()

    logger.info("Fetching NBA teams...")
    async with httpx.AsyncClient(timeout=30) as client:
        raw_teams = await fetch_all_teams(client)

    team_id_map = upsert_teams(supabase, raw_teams)
    logger.info(f"Upserted {len(team_id_map)} teams")

    for season in _current_nba_seasons():
        await ingest_season(season, team_id_map, supabase)

    logger.info("NBA ingestion complete")


if __name__ == "__main__":
    asyncio.run(run())
