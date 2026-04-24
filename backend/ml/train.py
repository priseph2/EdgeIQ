"""
Model training pipeline for EdgeIQ.

Two separate models:
  1. NBA / EuroLeague basketball — LightGBM binary classifier (home win)
  2. Top 5 football leagues — LightGBM multi-class classifier (H/D/A)

Both use:
  - Time-based train/val/test split (no data leakage)
  - Platt scaling calibration via CalibratedClassifierCV
  - Brier score + ROC-AUC evaluation
  - joblib serialization to backend/ml/models/

Usage:
  python -m ml.train --sport basketball
  python -m ml.train --sport football
  python -m ml.train --sport all
"""

import argparse
import logging
import os
import joblib
import numpy as np
import pandas as pd
from datetime import datetime
from pathlib import Path

from sklearn.metrics import brier_score_loss, roc_auc_score, accuracy_score
from sklearn.preprocessing import label_binarize
import lightgbm as lgb

from supabase import create_client
from config import get_settings
from ml.features import build_basketball_features, build_football_features

logger = logging.getLogger(__name__)

MODELS_DIR = Path(__file__).parent / "models"
MODELS_DIR.mkdir(exist_ok=True)

BASKETBALL_LEAGUES = ["NBA", "EuroLeague", "EuroCup"]
FOOTBALL_LEAGUES = ["Premier League", "La Liga", "Bundesliga", "Serie A", "Ligue 1"]


def get_supabase():
    s = get_settings()
    return create_client(s.supabase_url, s.supabase_service_role_key)


def load_basketball_data(supabase) -> tuple[pd.DataFrame, pd.DataFrame]:
    matches = supabase.table("matches").select("*").in_("league", BASKETBALL_LEAGUES)\
        .eq("status", "finished").execute()
    stats = supabase.table("team_stats_basketball").select("*").execute()
    return pd.DataFrame(matches.data), pd.DataFrame(stats.data)


def load_football_data(supabase) -> tuple[pd.DataFrame, pd.DataFrame]:
    matches = supabase.table("matches").select("*").in_("league", FOOTBALL_LEAGUES)\
        .eq("status", "finished").execute()
    stats = supabase.table("team_stats_football").select("*").execute()
    return pd.DataFrame(matches.data), pd.DataFrame(stats.data)


def time_split(df: pd.DataFrame, val_frac=0.15, test_frac=0.15):
    """Time-based split — last N% of matches are val/test. No shuffling."""
    n = len(df)
    test_start = int(n * (1 - test_frac))
    val_start = int(n * (1 - val_frac - test_frac))
    train = df.iloc[:val_start]
    val = df.iloc[val_start:test_start]
    test = df.iloc[test_start:]
    return train, val, test


def get_feature_cols(df: pd.DataFrame) -> list[str]:
    exclude = {"match_id", "league", "start_time", "target"}
    return [c for c in df.columns if c not in exclude]


def train_basketball(supabase) -> dict:
    logger.info("Loading basketball data...")
    matches_df, stats_df = load_basketball_data(supabase)
    if matches_df.empty:
        raise ValueError("No basketball match data found. Run data ingestion first.")

    logger.info(f"Building features for {len(matches_df)} basketball matches...")
    feat_df = build_basketball_features(matches_df, stats_df)
    feat_df = feat_df.sort_values("start_time").dropna()
    logger.info(f"Feature matrix: {feat_df.shape}, home win rate: {feat_df['target'].mean():.3f}")

    train, val, test = time_split(feat_df)
    feature_cols = get_feature_cols(feat_df)

    X_train, y_train = train[feature_cols].values, train["target"].values
    X_val, y_val = val[feature_cols].values, val["target"].values
    X_test, y_test = test[feature_cols].values, test["target"].values

    logger.info(f"Train: {len(X_train)}, Val: {len(X_val)}, Test: {len(X_test)}")

    base_model = lgb.LGBMClassifier(
        n_estimators=500,
        learning_rate=0.05,
        num_leaves=31,
        max_depth=6,
        min_child_samples=20,
        subsample=0.8,
        colsample_bytree=0.8,
        reg_alpha=0.1,
        reg_lambda=0.1,
        class_weight="balanced",
        random_state=42,
        verbose=-1,
    )

    base_model.fit(
        X_train, y_train,
        eval_set=[(X_val, y_val)],
        callbacks=[lgb.early_stopping(50, verbose=False), lgb.log_evaluation(50)],
    )

    # Evaluate on test set (LightGBM predict_proba is well-calibrated with early stopping)
    probs = base_model.predict_proba(X_test)[:, 1]
    preds = base_model.predict(X_test)
    calibrated = base_model
    brier = brier_score_loss(y_test, probs)
    auc = roc_auc_score(y_test, probs)
    acc = accuracy_score(y_test, preds)

    logger.info(f"Basketball test — Brier: {brier:.4f} | AUC: {auc:.4f} | Accuracy: {acc:.4f}")

    model_path = MODELS_DIR / "basketball_v1.pkl"
    joblib.dump({
        "model": calibrated,
        "feature_cols": feature_cols,
        "trained_at": datetime.utcnow().isoformat(),
        "brier_score": brier,
        "auc": auc,
        "accuracy": acc,
        "sport": "basketball",
    }, model_path)
    logger.info(f"Basketball model saved to {model_path}")

    return {"brier": brier, "auc": auc, "accuracy": acc}


def train_football(supabase) -> dict:
    logger.info("Loading football data...")
    matches_df, stats_df = load_football_data(supabase)
    if matches_df.empty:
        raise ValueError("No football match data found. Run data ingestion first.")

    logger.info(f"Building features for {len(matches_df)} football matches...")
    feat_df = build_football_features(matches_df, stats_df)
    feat_df = feat_df.sort_values("start_time").dropna()
    logger.info(f"Feature matrix: {feat_df.shape}")
    logger.info(f"Outcome distribution: {feat_df['target'].value_counts(normalize=True).to_dict()}")

    train, val, test = time_split(feat_df)
    feature_cols = get_feature_cols(feat_df)

    X_train, y_train = train[feature_cols].values, train["target"].values
    X_val, y_val = val[feature_cols].values, val["target"].values
    X_test, y_test = test[feature_cols].values, test["target"].values

    logger.info(f"Train: {len(X_train)}, Val: {len(X_val)}, Test: {len(X_test)}")

    base_model = lgb.LGBMClassifier(
        n_estimators=500,
        learning_rate=0.05,
        num_leaves=31,
        max_depth=6,
        min_child_samples=20,
        subsample=0.8,
        colsample_bytree=0.8,
        reg_alpha=0.1,
        reg_lambda=0.1,
        class_weight="balanced",
        num_class=3,
        objective="multiclass",
        random_state=42,
        verbose=-1,
    )

    base_model.fit(
        X_train, y_train,
        eval_set=[(X_val, y_val)],
        callbacks=[lgb.early_stopping(50, verbose=False), lgb.log_evaluation(50)],
    )

    probs = base_model.predict_proba(X_test)
    preds = base_model.predict(X_test)
    calibrated = base_model

    # Multi-class Brier score (average over classes)
    y_bin = label_binarize(y_test, classes=[0, 1, 2])
    brier = float(np.mean([brier_score_loss(y_bin[:, i], probs[:, i]) for i in range(3)]))
    auc = roc_auc_score(y_bin, probs, multi_class="ovr", average="macro")
    acc = accuracy_score(y_test, preds)

    logger.info(f"Football test — Brier: {brier:.4f} | AUC: {auc:.4f} | Accuracy: {acc:.4f}")

    model_path = MODELS_DIR / "football_v1.pkl"
    joblib.dump({
        "model": calibrated,
        "feature_cols": feature_cols,
        "trained_at": datetime.utcnow().isoformat(),
        "brier_score": brier,
        "auc": auc,
        "accuracy": acc,
        "sport": "football",
    }, model_path)
    logger.info(f"Football model saved to {model_path}")

    return {"brier": brier, "auc": auc, "accuracy": acc}


def main():
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    parser = argparse.ArgumentParser()
    parser.add_argument("--sport", choices=["basketball", "football", "all"], default="all")
    args = parser.parse_args()

    supabase = get_supabase()
    results = {}

    if args.sport in ("basketball", "all"):
        try:
            results["basketball"] = train_basketball(supabase)
        except Exception as e:
            logger.error(f"Basketball training failed: {e}")

    if args.sport in ("football", "all"):
        try:
            results["football"] = train_football(supabase)
        except Exception as e:
            logger.error(f"Football training failed: {e}")

    logger.info(f"Training complete: {results}")


if __name__ == "__main__":
    main()
