"""
EuroLeague basketball ingestion via api-basketball (RapidAPI free tier).
Fetches last 2 seasons of EuroLeague + EuroCup results.

Usage:
  python -m data.ingest_euro_bb
"""

import asyncio
import httpx
import logging
from supabase import create_client
from config import get_settings

logger = logging.getLogger(__name__)

BASE = "https://api-basketball.p.rapidapi.com"
SPORT = "basketball"
LEAGUES = [
    {"id": 120, "name": "EuroLeague"},
    {"id": 124, "name": "EuroCup"},
]
SEASONS = ["2022-2023", "2023-2024", "2024-2025"]


def get_supabase():
    s = get_settings()
    return create_client(s.supabase_url, s.supabase_service_role_key)


def get_headers() -> dict:
    return {
        "X-RapidAPI-Key": get_settings().rapidapi_key,
        "X-RapidAPI-Host": "api-basketball.p.rapidapi.com",
    }


async def fetch_games(client: httpx.AsyncClient, league_id: int, season: str) -> list[dict]:
    r = await client.get(
        f"{BASE}/games",
        params={"league": league_id, "season": season},
        headers=get_headers(),
    )
    if r.status_code != 200:
        logger.warning(f"api-basketball returned {r.status_code} for league {league_id} {season}")
        return []
    return r.json().get("response", [])


def upsert_team(supabase, name: str, league: str) -> str | None:
    row = {
        "name": name,
        "short_name": name[:4].upper(),
        "sport": SPORT,
        "league": league,
        "external_id": f"{league}:{name}",
    }
    res = supabase.table("teams").upsert(row, on_conflict="sport,external_id").execute()
    if res.data:
        return res.data[0]["id"]
    return None


async def ingest_league_season(league: dict, season: str, supabase):
    logger.info(f"Ingesting {league['name']} {season}...")
    async with httpx.AsyncClient(timeout=30) as client:
        games = await fetch_games(client, league["id"], season)

    team_cache: dict[str, str] = {}
    ingested = 0

    for game in games:
        home_name = game["teams"]["home"]["name"]
        away_name = game["teams"]["away"]["name"]

        for name in [home_name, away_name]:
            if name not in team_cache:
                uid = upsert_team(supabase, name, league["name"])
                if uid:
                    team_cache[name] = uid

        home_id = team_cache.get(home_name)
        away_id = team_cache.get(away_name)
        if not home_id or not away_id:
            continue

        scores = game.get("scores", {})
        home_score = scores.get("home", {}).get("total")
        away_score = scores.get("away", {}).get("total")
        result = None
        if home_score is not None and away_score is not None:
            result = "home" if home_score > away_score else "away"

        status_val = game.get("status", {}).get("short", "NS")
        status = "finished" if status_val == "FT" else "scheduled"

        match_row = {
            "home_team_id": home_id,
            "away_team_id": away_id,
            "sport": SPORT,
            "league": league["name"],
            "start_time": game["date"],
            "status": status,
            "home_score": home_score,
            "away_score": away_score,
            "result": result,
            "draw_possible": False,
            "external_id": f"ebb:{game['id']}",
        }
        res = supabase.table("matches").upsert(match_row, on_conflict="sport,external_id").execute()
        if res.data and home_score is not None:
            match_uuid = res.data[0]["id"]
            stats = [
                {"team_id": home_id, "match_id": match_uuid, "is_home": True,
                 "points": home_score, "opp_points": away_score},
                {"team_id": away_id, "match_id": match_uuid, "is_home": False,
                 "points": away_score, "opp_points": home_score},
            ]
            supabase.table("team_stats_basketball").upsert(stats).execute()
            ingested += 1

    logger.info(f"{league['name']} {season}: {ingested} games ingested")


async def run():
    logging.basicConfig(level=logging.INFO)
    supabase = get_supabase()

    for league in LEAGUES:
        for season in SEASONS:
            try:
                await ingest_league_season(league, season, supabase)
                await asyncio.sleep(2)
            except Exception as e:
                logger.error(f"Failed {league['name']} {season}: {e}")

    logger.info("EuroLeague/EuroCup ingestion complete")


if __name__ == "__main__":
    asyncio.run(run())
