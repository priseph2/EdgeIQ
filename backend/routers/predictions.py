"""
Prediction API router.

GET  /predictions/today          — all today's matches with ML predictions
GET  /predictions/{match_id}     — single match prediction
POST /predictions/{match_id}/analysis  — trigger Claude AI analysis
GET  /predictions/model/stats    — model performance metrics
"""

import json
import logging
from datetime import datetime, timezone, timedelta
from typing import Optional
import pandas as pd
from fastapi import APIRouter, HTTPException, Depends
from pydantic import BaseModel
from supabase import Client

from ml.predict import predict_basketball, predict_football, check_value_bet
from ml.claude_analysis import analyze_match
from db import get_supabase, get_redis

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/predictions", tags=["predictions"])

BASKETBALL_LEAGUES = ["NBA", "EuroLeague", "EuroCup"]
FOOTBALL_LEAGUES = ["Premier League", "La Liga", "Bundesliga", "Serie A", "Ligue 1"]

PREDICTIONS_CACHE_TTL = 6 * 3600  # 6 hours


class PredictionResponse(BaseModel):
    match_id: str
    home_team: str
    away_team: str
    league: str
    sport: str
    start_time: str
    home_prob: float
    draw_prob: Optional[float]
    away_prob: float
    confidence: str
    pick: str
    value_flag: bool
    best_home_odds: Optional[float]
    best_draw_odds: Optional[float]
    best_away_odds: Optional[float]
    model_version: str


def _fetch_all(query) -> list:
    """Paginate through Supabase results (default limit is 1000 rows)."""
    all_data = []
    page = 0
    page_size = 1000
    while True:
        res = query.range(page * page_size, (page + 1) * page_size - 1).execute()
        all_data.extend(res.data or [])
        if len(res.data or []) < page_size:
            break
        page += 1
    return all_data


def _load_data(supabase: Client, sport: str) -> tuple[pd.DataFrame, pd.DataFrame]:
    leagues = BASKETBALL_LEAGUES if sport == "basketball" else FOOTBALL_LEAGUES
    stats_table = "team_stats_basketball" if sport == "basketball" else "team_stats_football"

    matches_data = _fetch_all(
        supabase.table("matches").select(
            "id, home_team_id, away_team_id, sport, league, start_time, status, result, draw_possible, "
            "home_team:teams!home_team_id(id,name), away_team:teams!away_team_id(id,name)"
        ).in_("league", leagues)
    )
    stats_data = _fetch_all(supabase.table(stats_table).select("*"))

    df = pd.DataFrame(matches_data)
    if not df.empty:
        df["start_time"] = pd.to_datetime(df["start_time"], utc=True)
    return df, pd.DataFrame(stats_data)


def _get_best_odds(supabase: Client, match_id: str) -> dict:
    res = supabase.table("odds").select("*").eq("match_id", match_id).execute()
    rows = res.data or []
    best = {"home": None, "draw": None, "away": None, "home_book": None, "away_book": None}
    for row in rows:
        if row["home_odds"] and (best["home"] is None or row["home_odds"] > best["home"]):
            best["home"] = row["home_odds"]
            best["home_book"] = row["bookmaker"]
        if row["away_odds"] and (best["away"] is None or row["away_odds"] > best["away"]):
            best["away"] = row["away_odds"]
            best["away_book"] = row["bookmaker"]
        if row["draw_odds"] and (best["draw"] is None or row["draw_odds"] > best["draw"]):
            best["draw"] = row["draw_odds"]
    return best


def _save_prediction(supabase: Client, match_id: str, sport: str, pred: dict, value_flag: bool):
    row = {
        "match_id": match_id,
        "sport": sport,
        "model_version": pred["model_version"],
        "home_prob": pred["home_prob"],
        "draw_prob": pred.get("draw_prob"),
        "away_prob": pred["away_prob"],
        "confidence": pred["confidence"],
        "value_flag": value_flag,
    }
    supabase.table("predictions").upsert(row, on_conflict="match_id").execute()


@router.get("/today", response_model=list[PredictionResponse])
async def get_today_predictions(
    sport: Optional[str] = None,
    supabase: Client = Depends(get_supabase),
    redis=Depends(get_redis),
):
    cache_key = f"predictions:today:{sport or 'all'}"
    if redis:
        try:
            cached = redis.get(cache_key)
            if cached:
                return json.loads(cached)
        except Exception:
            redis = None

    now = datetime.now(timezone.utc)
    today_start = now.replace(hour=0, minute=0, second=0, microsecond=0)
    today_end = today_start + timedelta(days=1)

    sports = [sport] if sport else ["basketball", "football"]
    results = []

    for s in sports:
        matches_df, stats_df = _load_data(supabase, s)
        if matches_df.empty or stats_df.empty:
            continue

        today_matches = matches_df[
            (matches_df["start_time"] >= today_start) &
            (matches_df["start_time"] < today_end) &
            (matches_df["status"] == "scheduled")
        ]

        logger.info(f"[{s}] today_matches={len(today_matches)}, total_matches={len(matches_df)}, stats={len(stats_df)}")

        for _, match in today_matches.iterrows():
            match_id = match["id"]
            home_id = match["home_team_id"]
            away_id = match["away_team_id"]
            home_name = match["home_team"]["name"] if isinstance(match.get("home_team"), dict) else "Home"
            away_name = match["away_team"]["name"] if isinstance(match.get("away_team"), dict) else "Away"
            match_time = match["start_time"].to_pydatetime()

            try:
                if s == "basketball":
                    pred = predict_basketball(home_id, away_id, match_time, stats_df, matches_df)
                else:
                    pred = predict_football(home_id, away_id, match["league"], match_time, stats_df, matches_df)
            except FileNotFoundError:
                logger.warning(f"Model not trained yet for {s}")
                continue
            except Exception as e:
                logger.error(f"[{s}] Prediction error for {home_name} vs {away_name}: {e}", exc_info=True)
                continue

            if pred is None:
                logger.warning(f"[{s}] Features returned None for {home_name} vs {away_name} (home_id={home_id})")
                continue

            best_odds = _get_best_odds(supabase, match_id)
            value_flag = check_value_bet(
                pred, best_odds["home"], best_odds.get("draw"), best_odds["away"]
            )
            _save_prediction(supabase, match_id, s, pred, value_flag)

            results.append(PredictionResponse(
                match_id=match_id,
                home_team=home_name,
                away_team=away_name,
                league=match["league"],
                sport=s,
                start_time=str(match["start_time"]),
                home_prob=pred["home_prob"],
                draw_prob=pred.get("draw_prob"),
                away_prob=pred["away_prob"],
                confidence=pred["confidence"],
                pick=pred["pick"],
                value_flag=value_flag,
                best_home_odds=best_odds["home"],
                best_draw_odds=best_odds.get("draw"),
                best_away_odds=best_odds["away"],
                model_version=pred["model_version"],
            ))

    if redis and results:
        try:
            redis.setex(cache_key, 3600, json.dumps([r.model_dump() for r in results]))
        except Exception:
            pass

    return results


@router.post("/{match_id}/analysis")
async def get_ai_analysis(
    match_id: str,
    supabase: Client = Depends(get_supabase),
    redis=Depends(get_redis),
):
    cache_key = f"analysis:{match_id}"
    if redis:
        try:
            cached = redis.get(cache_key)
            if cached:
                return json.loads(cached)
        except Exception:
            redis = None

    # Get match details
    match_res = supabase.table("matches").select(
        "*, home_team:teams!home_team_id(name), away_team:teams!away_team_id(name)"
    ).eq("id", match_id).single().execute()
    if not match_res.data:
        raise HTTPException(404, "Match not found")

    match = match_res.data
    home_name = match["home_team"]["name"]
    away_name = match["away_team"]["name"]
    sport = match["sport"]

    # Get existing prediction
    pred_res = supabase.table("predictions").select("*").eq("match_id", match_id)\
        .order("created_at", desc=True).limit(1).execute()
    if not pred_res.data:
        raise HTTPException(404, "No prediction found for this match. Check predictions/today first.")

    pred = pred_res.data[0]

    # Get best odds
    best_odds = _get_best_odds(supabase, match_id)

    # Get recent form (last 5 results for each team)
    stats_table = "team_stats_basketball" if sport == "basketball" else "team_stats_football"
    home_stats = supabase.table(stats_table).select("match_id, points, opp_points, goals, opp_goals")\
        .eq("team_id", match["home_team_id"]).order("recorded_at", desc=True).limit(5).execute()
    away_stats = supabase.table(stats_table).select("match_id, points, opp_points, goals, opp_goals")\
        .eq("team_id", match["away_team_id"]).order("recorded_at", desc=True).limit(5).execute()

    def to_form(stats_data):
        form = []
        for s in stats_data:
            pts = s.get("points") or s.get("goals", 0)
            opp = s.get("opp_points") or s.get("opp_goals", 0)
            if pts is not None and opp is not None:
                form.append("W" if pts > opp else ("D" if pts == opp else "L"))
        return form

    home_form = to_form(home_stats.data or [])
    away_form = to_form(away_stats.data or [])

    prediction_dict = {
        "home_prob": pred["home_prob"],
        "draw_prob": pred.get("draw_prob"),
        "away_prob": pred["away_prob"],
        "confidence": pred["confidence"],
        "pick": "home" if pred["home_prob"] > pred["away_prob"] else "away",
    }

    analysis = await analyze_match(
        home_team=home_name,
        away_team=away_name,
        league=match["league"],
        sport=sport,
        start_time=str(match["start_time"]),
        prediction=prediction_dict,
        home_form=home_form,
        away_form=away_form,
        best_home_odds=best_odds["home"],
        best_draw_odds=best_odds.get("draw"),
        best_away_odds=best_odds["away"],
    )

    # Persist analysis into predictions table
    supabase.table("predictions").update({"claude_analysis": analysis})\
        .eq("id", pred["id"]).execute()

    if redis:
        try:
            redis.setex(cache_key, PREDICTIONS_CACHE_TTL, json.dumps(analysis))
        except Exception:
            pass

    return analysis


@router.get("/model/stats")
async def get_model_stats(supabase: Client = Depends(get_supabase)):
    """Return model performance metrics and recent calibration stats."""
    from pathlib import Path
    import joblib

    stats = {}
    for sport in ["basketball", "football"]:
        path = Path(__file__).parent.parent / "ml" / "models" / f"{sport}_v1.pkl"
        if path.exists():
            artifact = joblib.load(path)
            stats[sport] = {
                "trained_at": artifact.get("trained_at"),
                "brier_score": artifact.get("brier_score"),
                "auc": artifact.get("auc"),
                "accuracy": artifact.get("accuracy"),
                "model_version": f"{sport}_v1",
            }

    return stats
