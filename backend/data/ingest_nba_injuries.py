"""
NBA injury data from BallDontLie /player_injuries.
Returns a mapping of {supabase_team_uuid: injured_player_count} for use
in the prediction feature pipeline at inference time.

Not stored in DB — fetched fresh on each prediction run (called once per
daily predictions batch, not per match).
"""

import asyncio
import httpx
import logging
from data.ingest_nba import BALLDONTLIE_BASE, _headers, get_supabase

logger = logging.getLogger(__name__)


async def fetch_current_injuries() -> dict[str, int]:
    """
    Hit BallDontLie /player_injuries and return {bdl_team_id_str: player_count}.
    Returns empty dict on any failure (predictions still run without injury data).
    """
    try:
        async with httpx.AsyncClient(timeout=15) as client:
            r = await client.get(f"{BALLDONTLIE_BASE}/player_injuries", headers=_headers())
            if r.status_code != 200:
                logger.warning(f"BallDontLie injuries returned {r.status_code}")
                return {}
            injuries = r.json().get("data", [])

        counts: dict[str, int] = {}
        for inj in injuries:
            team_id = str((inj.get("player") or {}).get("team_id", ""))
            if team_id:
                counts[team_id] = counts.get(team_id, 0) + 1
        logger.info(f"Fetched {len(injuries)} injury records across {len(counts)} teams")
        return counts
    except Exception as e:
        logger.warning(f"Could not fetch NBA injuries: {e}")
        return {}


async def get_team_injury_map(supabase) -> dict[str, int]:
    """
    Returns {supabase_team_uuid: injured_player_count} for basketball teams.
    Used by the predictions router to enrich inference features.
    """
    injury_counts = await fetch_current_injuries()
    if not injury_counts:
        return {}

    res = supabase.table("teams").select("id,external_id").eq("sport", "basketball").execute()
    result: dict[str, int] = {}
    for team in (res.data or []):
        ext_id = team.get("external_id", "")
        uuid = team.get("id")
        if uuid and ext_id in injury_counts:
            result[uuid] = injury_counts[ext_id]

    logger.info(f"Injury map: {len(result)} teams with absences")
    return result


if __name__ == "__main__":
    import logging as _logging
    _logging.basicConfig(level=_logging.INFO)
    sb = get_supabase()
    result = asyncio.run(get_team_injury_map(sb))
    print(result)
