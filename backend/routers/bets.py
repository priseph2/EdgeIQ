"""
Bet tracker API router.

POST /bets                — log a new bet
GET  /bets                — list all bets (with filters)
PATCH /bets/{bet_id}      — update bet status/result
GET  /bets/analytics      — P&L analytics summary
GET  /bets/export/csv     — download all bets as CSV
"""

import csv
import io
import logging
from datetime import datetime, timezone
from typing import Optional
from fastapi import APIRouter, HTTPException, Depends
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field
from supabase import Client

from db import get_supabase

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/bets", tags=["bets"])


class BetCreate(BaseModel):
    match_id: Optional[str] = None
    sport: Optional[str] = None
    league: Optional[str] = None
    selection: str
    bookmaker: str
    odds: float = Field(gt=1.0)
    stake: float = Field(gt=0)
    tag: Optional[str] = None
    notes: Optional[str] = None
    confidence_stars: Optional[int] = Field(None, ge=1, le=5)


class BetUpdate(BaseModel):
    status: Optional[str] = None
    pnl: Optional[float] = None


@router.post("/")
async def create_bet(bet: BetCreate, supabase: Client = Depends(get_supabase)):
    # For now use a default user_id — replace with auth when multi-user is added
    default_user = supabase.table("users").select("id").limit(1).execute()
    if not default_user.data:
        raise HTTPException(400, "No user found. Create a user first.")
    user_id = default_user.data[0]["id"]

    row = {
        "user_id": user_id,
        "match_id": bet.match_id,
        "sport": bet.sport,
        "league": bet.league,
        "selection": bet.selection,
        "bookmaker": bet.bookmaker,
        "odds": bet.odds,
        "stake": bet.stake,
        "tag": bet.tag,
        "notes": bet.notes,
        "confidence_stars": bet.confidence_stars,
        "status": "pending",
        "placed_at": datetime.now(timezone.utc).isoformat(),
    }
    res = supabase.table("bets").insert(row).execute()
    return res.data[0]


@router.get("/")
async def list_bets(
    status: Optional[str] = None,
    sport: Optional[str] = None,
    tag: Optional[str] = None,
    limit: int = 100,
    supabase: Client = Depends(get_supabase),
):
    query = supabase.table("bets").select("*").order("placed_at", desc=True).limit(limit)
    if status:
        query = query.eq("status", status)
    if sport:
        query = query.eq("sport", sport)
    if tag:
        query = query.eq("tag", tag)
    res = query.execute()
    return res.data


@router.patch("/{bet_id}")
async def update_bet(bet_id: str, update: BetUpdate, supabase: Client = Depends(get_supabase)):
    updates = update.model_dump(exclude_none=True)
    if "status" in updates and updates["status"] in ("won", "lost", "void", "cashout"):
        updates["settled_at"] = datetime.now(timezone.utc).isoformat()
        if "pnl" not in updates:
            bet = supabase.table("bets").select("odds, stake").eq("id", bet_id).single().execute()
            if bet.data:
                o, s = bet.data["odds"], bet.data["stake"]
                if updates["status"] == "won":
                    updates["pnl"] = round((o - 1) * s, 2)
                elif updates["status"] in ("lost",):
                    updates["pnl"] = round(-s, 2)
                elif updates["status"] == "void":
                    updates["pnl"] = 0.0
    res = supabase.table("bets").update(updates).eq("id", bet_id).execute()
    if not res.data:
        raise HTTPException(404, "Bet not found")
    return res.data[0]


@router.get("/analytics")
async def get_analytics(supabase: Client = Depends(get_supabase)):
    res = supabase.table("bets").select("*").in_("status", ["won", "lost", "void"]).execute()
    bets = res.data or []

    if not bets:
        return {"message": "No settled bets yet. Start logging!"}

    total_staked = sum(b["stake"] for b in bets)
    total_pnl = sum(b.get("pnl") or 0 for b in bets)
    wins = [b for b in bets if b["status"] == "won"]
    losses = [b for b in bets if b["status"] == "lost"]

    roi = (total_pnl / total_staked * 100) if total_staked else 0
    win_rate = (len(wins) / len(bets) * 100) if bets else 0
    avg_odds = sum(b["odds"] for b in bets) / len(bets) if bets else 0

    # Breakdown by sport
    by_sport = {}
    for b in bets:
        s = b.get("sport") or "unknown"
        if s not in by_sport:
            by_sport[s] = {"staked": 0, "pnl": 0, "bets": 0, "wins": 0}
        by_sport[s]["staked"] += b["stake"]
        by_sport[s]["pnl"] += b.get("pnl") or 0
        by_sport[s]["bets"] += 1
        if b["status"] == "won":
            by_sport[s]["wins"] += 1
    for s in by_sport:
        by_sport[s]["roi"] = round(by_sport[s]["pnl"] / by_sport[s]["staked"] * 100, 2) if by_sport[s]["staked"] else 0

    # Breakdown by bookmaker
    by_book = {}
    for b in bets:
        bk = b.get("bookmaker") or "unknown"
        if bk not in by_book:
            by_book[bk] = {"staked": 0, "pnl": 0, "bets": 0}
        by_book[bk]["staked"] += b["stake"]
        by_book[bk]["pnl"] += b.get("pnl") or 0
        by_book[bk]["bets"] += 1
    for bk in by_book:
        by_book[bk]["roi"] = round(by_book[bk]["pnl"] / by_book[bk]["staked"] * 100, 2) if by_book[bk]["staked"] else 0

    # Breakdown by tag
    by_tag = {}
    for b in bets:
        t = b.get("tag") or "untagged"
        if t not in by_tag:
            by_tag[t] = {"staked": 0, "pnl": 0, "bets": 0}
        by_tag[t]["staked"] += b["stake"]
        by_tag[t]["pnl"] += b.get("pnl") or 0
        by_tag[t]["bets"] += 1

    # Kelly calculation helper
    def kelly_stake(bankroll: float, odds: float, win_prob: float, fraction: float = 0.5) -> dict:
        b = odds - 1
        q = 1 - win_prob
        k = (b * win_prob - q) / b
        if k <= 0:
            return {"stake": 0, "kelly_pct": 0, "note": "No edge"}
        actual_pct = k * fraction
        return {
            "kelly_pct": round(k * 100, 2),
            "recommended_pct": round(actual_pct * 100, 2),
            "stake": round(bankroll * actual_pct, 2),
        }

    return {
        "summary": {
            "total_bets": len(bets),
            "total_staked": round(total_staked, 2),
            "total_pnl": round(total_pnl, 2),
            "roi_pct": round(roi, 2),
            "win_rate_pct": round(win_rate, 2),
            "avg_odds": round(avg_odds, 3),
            "wins": len(wins),
            "losses": len(losses),
        },
        "by_sport": by_sport,
        "by_bookmaker": by_book,
        "by_tag": by_tag,
        "kelly_helper": kelly_stake,
    }


@router.get("/export/csv")
async def export_csv(supabase: Client = Depends(get_supabase)):
    res = supabase.table("bets").select("*").order("placed_at", desc=True).execute()
    bets = res.data or []

    output = io.StringIO()
    fieldnames = [
        "id", "sport", "league", "selection", "bookmaker", "odds", "stake",
        "status", "pnl", "tag", "notes", "confidence_stars", "placed_at", "settled_at"
    ]
    writer = csv.DictWriter(output, fieldnames=fieldnames, extrasaction="ignore")
    writer.writeheader()
    writer.writerows(bets)

    output.seek(0)
    return StreamingResponse(
        io.BytesIO(output.getvalue().encode()),
        media_type="text/csv",
        headers={"Content-Disposition": "attachment; filename=edgeiq_bets.csv"},
    )
