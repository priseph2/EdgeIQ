"""
Fetch xG (Expected Goals) from API-Football for recently finished fixtures
in the Top 5 European leagues, and update team_stats_football.xg / opp_xg.

API budget: 5 league calls + up to 50 fixture-stat calls ≈ 55 req/run.
Safe to run once daily (100 req/day free tier).

Usage:
  python -m data.ingest_xg
"""

import asyncio
import httpx
import logging
from collections import defaultdict
from datetime import datetime, timedelta, timezone
from difflib import SequenceMatcher
from supabase import create_client
from config import get_settings
from data.ingest_football import RAPIDAPI_BASE, RAPIDAPI_LEAGUE_IDS, get_rapidapi_headers

logger = logging.getLogger(__name__)


def _get_supabase():
    s = get_settings()
    return create_client(s.supabase_url, s.supabase_service_role_key)


def _normalize(name: str) -> str:
    name = name.lower().strip()
    for suffix in (" fc", " cf", " afc", " fk", " sc", " ac ", " ssd", " calcio", " united", " city"):
        if name.endswith(suffix):
            name = name[: -len(suffix)].strip()
    return name


def _similarity(a: str, b: str) -> float:
    return SequenceMatcher(None, _normalize(a), _normalize(b)).ratio()


async def _fetch_recent_fixtures(client: httpx.AsyncClient, league_id: int, season: int) -> list[dict]:
    r = await client.get(
        f"{RAPIDAPI_BASE}/fixtures",
        params={"league": league_id, "season": season, "last": 10},
        headers=get_rapidapi_headers(),
    )
    if r.status_code != 200:
        logger.warning(f"API-Football /fixtures {league_id}/{season}: HTTP {r.status_code}")
        return []
    return r.json().get("response", [])


async def _fetch_fixture_stats(
    client: httpx.AsyncClient, fixture_id: int, home_api_id: int, away_api_id: int
) -> tuple[float | None, float | None]:
    """Return (home_xg, away_xg) for a single fixture."""
    r = await client.get(
        f"{RAPIDAPI_BASE}/fixtures/statistics",
        params={"fixture": fixture_id, "type": "Expected Goals"},
        headers=get_rapidapi_headers(),
    )
    if r.status_code != 200:
        return None, None
    home_xg = away_xg = None
    for team_block in r.json().get("response", []):
        team_id = team_block.get("team", {}).get("id")
        for stat in team_block.get("statistics", []):
            if stat.get("type") == "Expected Goals" and stat.get("value") is not None:
                try:
                    val = float(stat["value"])
                except (TypeError, ValueError):
                    continue
                if team_id == home_api_id:
                    home_xg = val
                elif team_id == away_api_id:
                    away_xg = val
    return home_xg, away_xg


def _find_db_match(matches_by_date: dict, fixture_date: str, home_name: str, away_name: str):
    """Fuzzy-match an API-Football fixture to a DB match record."""
    target = datetime.strptime(fixture_date, "%Y-%m-%d").date()
    candidates = []
    for delta in (-1, 0, 1):
        d = (target + timedelta(days=delta)).isoformat()
        candidates.extend(matches_by_date.get(d, []))

    best_score = 0.0
    best_match = None
    for m in candidates:
        home_db = (m.get("home_team") or {}).get("name", "")
        away_db = (m.get("away_team") or {}).get("name", "")
        score = _similarity(home_name, home_db) + _similarity(away_name, away_db)
        if score > best_score:
            best_score = score
            best_match = m

    if best_score >= 1.3 and best_match:
        return best_match
    return None


def _update_xg(supabase, db_match: dict, home_xg, away_xg):
    match_id = db_match["id"]
    home_id = db_match["home_team_id"]
    away_id = db_match["away_team_id"]

    if home_xg is not None:
        supabase.table("team_stats_football").update({
            "xg": home_xg,
            "opp_xg": away_xg,
        }).eq("match_id", match_id).eq("team_id", home_id).execute()

    if away_xg is not None:
        supabase.table("team_stats_football").update({
            "xg": away_xg,
            "opp_xg": home_xg,
        }).eq("match_id", match_id).eq("team_id", away_id).execute()


def _current_season() -> int:
    now = datetime.now(timezone.utc)
    return now.year if now.month >= 8 else now.year - 1


async def run():
    supabase = _get_supabase()
    season = _current_season()

    # Load finished football matches from the last 90 days with team names
    cutoff = (datetime.now(timezone.utc) - timedelta(days=90)).isoformat()
    res = supabase.table("matches").select(
        "id, home_team_id, away_team_id, start_time, "
        "home_team:teams!home_team_id(name), away_team:teams!away_team_id(name)"
    ).eq("sport", "football").eq("status", "finished").gte("start_time", cutoff).execute()

    matches_by_date: dict[str, list] = defaultdict(list)
    for m in (res.data or []):
        date_key = (m.get("start_time") or "")[:10]
        if date_key:
            matches_by_date[date_key].append(m)

    logger.info(f"Loaded {sum(len(v) for v in matches_by_date.values())} finished matches from DB")

    total_updated = 0
    async with httpx.AsyncClient(timeout=30) as client:
        for league_name, league_id in RAPIDAPI_LEAGUE_IDS.items():
            fixtures = await _fetch_recent_fixtures(client, league_id, season)
            await asyncio.sleep(1)
            logger.info(f"[{league_name}] {len(fixtures)} recent fixtures from API-Football")

            for fixture in fixtures:
                f = fixture.get("fixture", {})
                if f.get("status", {}).get("short") not in ("FT", "AET", "PEN"):
                    continue

                fixture_id = f["id"]
                fixture_date = (f.get("date") or "")[:10]
                if not fixture_date:
                    continue

                home_api = fixture["teams"]["home"]
                away_api = fixture["teams"]["away"]

                db_match = _find_db_match(
                    matches_by_date, fixture_date, home_api["name"], away_api["name"]
                )
                if not db_match:
                    logger.debug(
                        f"No DB match for {home_api['name']} vs {away_api['name']} on {fixture_date}"
                    )
                    continue

                home_xg, away_xg = await _fetch_fixture_stats(
                    client, fixture_id, home_api["id"], away_api["id"]
                )
                await asyncio.sleep(0.5)

                if home_xg is None and away_xg is None:
                    logger.debug(f"No xG data for fixture {fixture_id}")
                    continue

                _update_xg(supabase, db_match, home_xg, away_xg)
                total_updated += 1
                logger.info(
                    f"Updated xG: {home_api['name']} {home_xg} vs {away_xg} {away_api['name']} "
                    f"(fixture {fixture_id})"
                )

    logger.info(f"xG ingestion complete — {total_updated} matches updated")


if __name__ == "__main__":
    import logging as _logging
    _logging.basicConfig(level=_logging.INFO)
    asyncio.run(run())
