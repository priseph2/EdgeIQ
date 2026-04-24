"""
Odds API router.

GET /odds/today        — best odds for today's scheduled matches
GET /odds/value-bets   — value bets with model edge > 5%
GET /odds/arb          — arbitrage alerts
"""

import logging
from datetime import datetime, timezone, timedelta
from typing import Optional
from fastapi import APIRouter, Depends
from pydantic import BaseModel
from supabase import Client
from db import get_supabase

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/odds", tags=["odds"])


class OddsRow(BaseModel):
    match_id: str
    home_team: str
    away_team: str
    league: str
    start_time: str
    bookmaker: str
    home_odds: Optional[float]
    draw_odds: Optional[float]
    away_odds: Optional[float]


class ValueBet(BaseModel):
    match_id: str
    home_team: str
    away_team: str
    league: str
    start_time: str
    selection: str
    edge_pct: float
    model_prob: float
    market_prob: float
    best_odds: float
    detected_at: str


class ArbAlert(BaseModel):
    match_id: str
    home_team: str
    away_team: str
    league: str
    profit_pct: float
    stakes_json: dict
    detected_at: str


@router.get("/today", response_model=list[OddsRow])
async def get_today_odds(
    date: Optional[str] = None,
    supabase: Client = Depends(get_supabase),
):
    if date:
        day_start = datetime.strptime(date, "%Y-%m-%d").replace(tzinfo=timezone.utc)
    else:
        now = datetime.now(timezone.utc)
        day_start = now.replace(hour=0, minute=0, second=0, microsecond=0)
    day_end = day_start + timedelta(days=1)

    matches = supabase.table("matches").select(
        "id, league, start_time, "
        "home_team:teams!home_team_id(name), away_team:teams!away_team_id(name)"
    ).eq("status", "scheduled").gte("start_time", day_start.isoformat())\
     .lt("start_time", day_end.isoformat()).execute()

    if not matches.data:
        return []

    match_ids = [m["id"] for m in matches.data]
    match_map = {m["id"]: m for m in matches.data}

    odds = supabase.table("odds").select("*").in_("match_id", match_ids).execute()

    results = []
    for row in (odds.data or []):
        m = match_map.get(row["match_id"], {})
        results.append(OddsRow(
            match_id=row["match_id"],
            home_team=(m.get("home_team") or {}).get("name", "?"),
            away_team=(m.get("away_team") or {}).get("name", "?"),
            league=m.get("league", "?"),
            start_time=str(m.get("start_time", "")),
            bookmaker=row["bookmaker"],
            home_odds=row.get("home_odds"),
            draw_odds=row.get("draw_odds"),
            away_odds=row.get("away_odds"),
        ))
    return results


@router.get("/value-bets", response_model=list[ValueBet])
async def get_value_bets(
    supabase: Client = Depends(get_supabase),
):
    now = datetime.now(timezone.utc)
    cutoff = now.replace(hour=0, minute=0, second=0, microsecond=0).isoformat()

    vbs = supabase.table("value_bets").select("*").gte("detected_at", cutoff)\
        .order("edge_pct", desc=True).execute()

    results = []
    for vb in (vbs.data or []):
        match = supabase.table("matches").select(
            "league, start_time, "
            "home_team:teams!home_team_id(name), away_team:teams!away_team_id(name)"
        ).eq("id", vb["match_id"]).single().execute()
        m = match.data or {}
        results.append(ValueBet(
            match_id=vb["match_id"],
            home_team=(m.get("home_team") or {}).get("name", "?"),
            away_team=(m.get("away_team") or {}).get("name", "?"),
            league=m.get("league", "?"),
            start_time=str(m.get("start_time", "")),
            selection=vb["selection"],
            edge_pct=vb["edge_pct"],
            model_prob=vb["model_prob"],
            market_prob=vb["market_prob"],
            best_odds=vb["best_odds"],
            detected_at=str(vb.get("detected_at", "")),
        ))
    return results


@router.get("/arb", response_model=list[ArbAlert])
async def get_arb_alerts(supabase: Client = Depends(get_supabase)):
    now = datetime.now(timezone.utc)
    cutoff = now.replace(hour=0, minute=0, second=0, microsecond=0).isoformat()

    arbs = supabase.table("arb_alerts").select("*").gte("detected_at", cutoff)\
        .order("profit_pct", desc=True).execute()

    results = []
    for arb in (arbs.data or []):
        match = supabase.table("matches").select(
            "league, start_time, "
            "home_team:teams!home_team_id(name), away_team:teams!away_team_id(name)"
        ).eq("id", arb["match_id"]).single().execute()
        m = match.data or {}
        results.append(ArbAlert(
            match_id=arb["match_id"],
            home_team=(m.get("home_team") or {}).get("name", "?"),
            away_team=(m.get("away_team") or {}).get("name", "?"),
            league=m.get("league", "?"),
            profit_pct=arb["profit_pct"],
            stakes_json=arb.get("stakes_json", {}),
            detected_at=str(arb.get("detected_at", "")),
        ))
    return results
