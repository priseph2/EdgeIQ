"""
Football data ingestion:
  - football-data.org (free) → match results + fixtures for Top 5 leagues
  - API-Football via RapidAPI (free tier) → xG + injury context

Leagues covered:
  PL  = Premier League
  PD  = La Liga
  BL1 = Bundesliga
  SA  = Serie A
  FL1 = Ligue 1

Usage:
  python -m data.ingest_football
"""

import asyncio
import httpx
import logging
from datetime import datetime
from typing import Optional
from supabase import create_client
from config import get_settings

logger = logging.getLogger(__name__)

FD_BASE = "https://api.football-data.org/v4"
RAPIDAPI_BASE = "https://api-football-v1.p.rapidapi.com/v3"

LEAGUE_CODES = {
    "PL": "Premier League",
    "PD": "La Liga",
    "BL1": "Bundesliga",
    "SA": "Serie A",
    "FL1": "Ligue 1",
}

# api-football league IDs for xG data
RAPIDAPI_LEAGUE_IDS = {
    "Premier League": 39,
    "La Liga": 140,
    "Bundesliga": 78,
    "Serie A": 135,
    "Ligue 1": 61,
}

SEASONS_TO_FETCH = [2022, 2023, 2024]
SPORT = "football"


def get_supabase():
    s = get_settings()
    return create_client(s.supabase_url, s.supabase_service_role_key)


def get_fd_headers() -> dict:
    return {"X-Auth-Token": get_settings().football_data_api_key}


def get_rapidapi_headers() -> dict:
    return {
        "X-RapidAPI-Key": get_settings().rapidapi_key,
        "X-RapidAPI-Host": "api-football-v1.p.rapidapi.com",
    }


def determine_result(home_score: Optional[int], away_score: Optional[int]) -> Optional[str]:
    if home_score is None or away_score is None:
        return None
    if home_score > away_score:
        return "home"
    if home_score < away_score:
        return "away"
    return "draw"


async def fetch_fd_matches(client: httpx.AsyncClient, competition_code: str, season: int) -> list[dict]:
    url = f"{FD_BASE}/competitions/{competition_code}/matches"
    r = await client.get(url, params={"season": season}, headers=get_fd_headers())
    if r.status_code == 429:
        logger.warning("Rate limited by football-data.org, sleeping 60s...")
        await asyncio.sleep(60)
        r = await client.get(url, params={"season": season}, headers=get_fd_headers())
    r.raise_for_status()
    return r.json().get("matches", [])


async def fetch_xg_data(client: httpx.AsyncClient, league_id: int, season: int) -> dict[str, dict]:
    """Fetch xG data from API-Football. Returns {fixture_id: {home_xg, away_xg}}."""
    xg_map = {}
    page = 1
    while True:
        params = {"league": league_id, "season": season, "page": page}
        r = await client.get(
            f"{RAPIDAPI_BASE}/fixtures/statistics",
            params={"league": league_id, "season": season},
            headers=get_rapidapi_headers(),
        )
        if r.status_code != 200:
            break
        data = r.json().get("response", [])
        if not data:
            break
        for fixture in data:
            fid = str(fixture.get("fixture", {}).get("id", ""))
            stats = fixture.get("statistics", [])
            home_xg = away_xg = None
            for team_stats in stats:
                for stat in team_stats.get("statistics", []):
                    if stat["type"] == "Expected Goals" and stat["value"]:
                        if team_stats.get("team", {}).get("home"):
                            home_xg = float(stat["value"])
                        else:
                            away_xg = float(stat["value"])
            if fid:
                xg_map[fid] = {"home_xg": home_xg, "away_xg": away_xg}
        page += 1
        if page > 30:
            break
        await asyncio.sleep(1)
    return xg_map


def upsert_team(supabase, name: str, short_name: str, league: str) -> Optional[str]:
    row = {
        "name": name,
        "short_name": short_name,
        "sport": SPORT,
        "league": league,
        "external_id": f"{league}:{name}",
    }
    res = supabase.table("teams").upsert(row, on_conflict="sport,external_id").execute()
    if res.data:
        return res.data[0]["id"]
    return None


def parse_fd_match(match: dict, league: str, team_cache: dict, supabase) -> Optional[dict]:
    home_name = match["homeTeam"]["name"]
    away_name = match["awayTeam"]["name"]
    home_short = match["homeTeam"].get("shortName", home_name[:3].upper())
    away_short = match["awayTeam"].get("shortName", away_name[:3].upper())

    if home_name not in team_cache:
        uid = upsert_team(supabase, home_name, home_short, league)
        if uid:
            team_cache[home_name] = uid
    if away_name not in team_cache:
        uid = upsert_team(supabase, away_name, away_short, league)
        if uid:
            team_cache[away_name] = uid

    home_id = team_cache.get(home_name)
    away_id = team_cache.get(away_name)
    if not home_id or not away_id:
        return None

    score = match.get("score", {})
    ft = score.get("fullTime", {})
    home_score = ft.get("home")
    away_score = ft.get("away")
    result = determine_result(home_score, away_score)

    fd_status = match.get("status", "SCHEDULED")
    status_map = {
        "FINISHED": "finished",
        "IN_PLAY": "live",
        "PAUSED": "live",
        "SCHEDULED": "scheduled",
        "TIMED": "scheduled",
        "CANCELLED": "cancelled",
        "POSTPONED": "cancelled",
    }
    status = status_map.get(fd_status, "scheduled")

    return {
        "home_team_id": home_id,
        "away_team_id": away_id,
        "sport": SPORT,
        "league": league,
        "start_time": match["utcDate"],
        "status": status,
        "home_score": home_score,
        "away_score": away_score,
        "result": result,
        "draw_possible": True,
        "external_id": f"fd:{match['id']}",
    }


def upsert_football_stats(supabase, match_uuid: str, home_id: str, away_id: str,
                           home_goals: Optional[int], away_goals: Optional[int],
                           home_xg: Optional[float] = None, away_xg: Optional[float] = None):
    if home_goals is None:
        return
    stats = [
        {
            "team_id": home_id,
            "match_id": match_uuid,
            "is_home": True,
            "goals": home_goals,
            "opp_goals": away_goals,
            "xg": home_xg,
            "opp_xg": away_xg,
        },
        {
            "team_id": away_id,
            "match_id": match_uuid,
            "is_home": False,
            "goals": away_goals,
            "opp_goals": home_goals,
            "xg": away_xg,
            "opp_xg": home_xg,
        },
    ]
    supabase.table("team_stats_football").upsert(stats).execute()


async def ingest_league_season(
    competition_code: str, league_name: str, season: int, supabase
):
    logger.info(f"Ingesting {league_name} {season}...")
    team_cache: dict[str, str] = {}

    async with httpx.AsyncClient(timeout=30) as client:
        matches = await fetch_fd_matches(client, competition_code, season)
        await asyncio.sleep(6)  # respect 10 req/min rate limit

    ingested = 0
    for match in matches:
        row = parse_fd_match(match, league_name, team_cache, supabase)
        if not row:
            continue
        res = supabase.table("matches").upsert(row, on_conflict="sport,external_id").execute()
        if res.data:
            match_uuid = res.data[0]["id"]
            upsert_football_stats(
                supabase, match_uuid,
                row["home_team_id"], row["away_team_id"],
                row.get("home_score"), row.get("away_score"),
            )
            ingested += 1

    logger.info(f"{league_name} {season}: {ingested} matches ingested")


async def run():
    logging.basicConfig(level=logging.INFO)
    supabase = get_supabase()

    for season in SEASONS_TO_FETCH:
        for code, name in LEAGUE_CODES.items():
            try:
                await ingest_league_season(code, name, season, supabase)
            except Exception as e:
                logger.error(f"Failed {name} {season}: {e}")

    logger.info("Football ingestion complete")


if __name__ == "__main__":
    asyncio.run(run())
