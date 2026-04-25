"""
Inference module — loads trained models and generates predictions for upcoming matches.
Called by the FastAPI prediction router.
"""

import joblib
import logging
import numpy as np
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

from ml.features import (
    build_inference_features_basketball,
    build_inference_features_football,
)

logger = logging.getLogger(__name__)

MODELS_DIR = Path(__file__).parent / "models"

_model_cache: dict = {}


def _download_model(sport: str, path: Path):
    """Try to restore model from Supabase Storage if not on disk."""
    try:
        from supabase import create_client
        from config import get_settings
        s = get_settings()
        sb = create_client(s.supabase_url, s.supabase_service_role_key)
        data = sb.storage.from_("models").download(f"{sport}_v1.pkl")
        path.parent.mkdir(parents=True, exist_ok=True)
        with open(path, "wb") as f:
            f.write(data)
        logger.info(f"Restored {sport} model from Supabase Storage")
    except Exception as e:
        logger.warning(f"Could not restore {sport} model from storage: {e}")


def load_model(sport: str) -> dict:
    if sport not in _model_cache:
        path = MODELS_DIR / f"{sport}_v1.pkl"
        if not path.exists():
            _download_model(sport, path)
        if not path.exists():
            raise FileNotFoundError(f"Model not found: {path}. Run ml.train first.")
        _model_cache[sport] = joblib.load(path)
        logger.info(f"Loaded {sport} model (Brier={_model_cache[sport]['brier_score']:.4f})")
    return _model_cache[sport]


def predict_basketball(
    home_team_id: str,
    away_team_id: str,
    match_time: datetime,
    stats_df,
    matches_df,
) -> Optional[dict]:
    feats = build_inference_features_basketball(
        home_team_id, away_team_id, match_time, stats_df, matches_df
    )
    if feats is None:
        return None

    artifact = load_model("basketball")
    model = artifact["model"]
    feature_cols = artifact["feature_cols"]

    X = np.array([[feats.get(c, 0.0) for c in feature_cols]])
    probs = model.predict_proba(X)[0]
    home_prob = float(probs[1])
    away_prob = float(probs[0])

    confidence = _confidence_label(max(home_prob, away_prob))

    predicted_total = round(feats.get("home_pts_avg5", 0) + feats.get("away_pts_avg5", 0), 1)

    return {
        "home_prob": round(home_prob, 4),
        "draw_prob": None,
        "away_prob": round(away_prob, 4),
        "confidence": confidence,
        "pick": "home" if home_prob > away_prob else "away",
        "model_version": "basketball_v1",
        "predicted_total": predicted_total if predicted_total > 0 else None,
        "home_xg": None,
        "away_xg": None,
    }


def predict_football(
    home_team_id: str,
    away_team_id: str,
    league: str,
    match_time: datetime,
    stats_df,
    matches_df,
) -> Optional[dict]:
    feats = build_inference_features_football(
        home_team_id, away_team_id, league, match_time, stats_df, matches_df
    )
    if feats is None:
        return None

    artifact = load_model("football")
    model = artifact["model"]
    feature_cols = artifact["feature_cols"]

    X = np.array([[feats.get(c, 0.0) for c in feature_cols]])
    probs = model.predict_proba(X)[0]
    # Classes: 0=home, 1=draw, 2=away
    home_prob = float(probs[0])
    draw_prob = float(probs[1])
    away_prob = float(probs[2])

    best_outcome_prob = max(home_prob, draw_prob, away_prob)
    confidence = _confidence_label(best_outcome_prob)
    pick_map = {0: "home", 1: "draw", 2: "away"}
    pick = pick_map[int(np.argmax(probs))]

    home_xg = feats.get("home_xg_avg5", 0.0)
    away_xg = feats.get("away_xg_avg5", 0.0)

    return {
        "home_prob": round(home_prob, 4),
        "draw_prob": round(draw_prob, 4),
        "away_prob": round(away_prob, 4),
        "confidence": confidence,
        "pick": pick,
        "model_version": "football_v1",
        "predicted_total": None,
        "home_xg": round(home_xg, 2) if home_xg > 0 else None,
        "away_xg": round(away_xg, 2) if away_xg > 0 else None,
    }


def _confidence_label(best_prob: float) -> str:
    if best_prob >= 0.60:
        return "high"
    if best_prob >= 0.50:
        return "medium"
    return "low"


def check_value_bet(prediction: dict, best_home_odds: float | None,
                     best_draw_odds: float | None, best_away_odds: float | None,
                     threshold: float = 0.05) -> bool:
    """Returns True if any outcome has model_prob - market_implied_prob > threshold."""
    checks = [
        (prediction["home_prob"], best_home_odds),
        (prediction.get("draw_prob"), best_draw_odds),
        (prediction["away_prob"], best_away_odds),
    ]
    for model_prob, odds in checks:
        if model_prob and odds and odds > 1.0:
            market_implied = 1.0 / odds
            if model_prob - market_implied >= threshold:
                return True
    return False
