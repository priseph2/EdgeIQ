"""
Feature engineering pipeline for both basketball and football models.

Basketball features (binary classifier: home win):
  - Rolling points scored/allowed (last 5, last 10)
  - Home/away form split
  - Rest days + back-to-back flag
  - H2H record (last 5 meetings)
  - Win % this season

Football features (3-way classifier: home/draw/away):
  - Rolling goals scored/conceded (last 5, last 10)
  - xG for/against (last 5) — strongest predictor
  - Home/away form split
  - H2H record
  - Days since last match (fatigue)
  - League position proxy (cumulative points per game)
  - Shots on target per game
"""

import pandas as pd
import numpy as np
from datetime import datetime, timezone
from typing import Literal


SportType = Literal["basketball", "football"]


# ── Basketball Features ────────────────────────────────────────────────────────

def build_basketball_features(matches_df: pd.DataFrame, stats_df: pd.DataFrame) -> pd.DataFrame:
    """
    matches_df: columns: id, home_team_id, away_team_id, start_time, result, league
    stats_df: columns: match_id, team_id, is_home, points, opp_points, fg_pct, fg3_pct

    Returns DataFrame with one row per match + all features + target (1=home win, 0=away win)
    """
    stats_df = stats_df.copy()
    matches_df = matches_df.copy()
    matches_df["start_time"] = pd.to_datetime(matches_df["start_time"], utc=True)
    matches_df = matches_df.sort_values("start_time").reset_index(drop=True)

    rows = []
    for _, match in matches_df.iterrows():
        if match["result"] not in ("home", "away"):
            continue

        home_id = match["home_team_id"]
        away_id = match["away_team_id"]
        match_time = match["start_time"]

        home_feats = _team_bb_features(home_id, match_time, stats_df, matches_df, is_home_split=True)
        away_feats = _team_bb_features(away_id, match_time, stats_df, matches_df, is_home_split=False)
        h2h = _h2h_basketball(home_id, away_id, match_time, matches_df)

        if home_feats is None or away_feats is None:
            continue

        row = {
            "match_id": match["id"],
            "league": match["league"],
            "start_time": match_time,
            # Home team rolling stats
            "home_pts_avg5": home_feats["pts_avg5"],
            "home_pts_avg10": home_feats["pts_avg10"],
            "home_opp_pts_avg5": home_feats["opp_pts_avg5"],
            "home_opp_pts_avg10": home_feats["opp_pts_avg10"],
            "home_win_pct": home_feats["win_pct"],
            "home_win_pct_at_home": home_feats["win_pct_venue"],
            "home_rest_days": home_feats["rest_days"],
            "home_b2b": home_feats["is_b2b"],
            "home_pts_diff_avg5": home_feats["pts_diff_avg5"],
            # Away team rolling stats
            "away_pts_avg5": away_feats["pts_avg5"],
            "away_pts_avg10": away_feats["pts_avg10"],
            "away_opp_pts_avg5": away_feats["opp_pts_avg5"],
            "away_opp_pts_avg10": away_feats["opp_pts_avg10"],
            "away_win_pct": away_feats["win_pct"],
            "away_win_pct_away": away_feats["win_pct_venue"],
            "away_rest_days": away_feats["rest_days"],
            "away_b2b": away_feats["is_b2b"],
            "away_pts_diff_avg5": away_feats["pts_diff_avg5"],
            # Differential features (often most predictive)
            "diff_pts_avg5": home_feats["pts_avg5"] - away_feats["pts_avg5"],
            "diff_opp_pts_avg5": away_feats["opp_pts_avg5"] - home_feats["opp_pts_avg5"],
            "diff_win_pct": home_feats["win_pct"] - away_feats["win_pct"],
            # H2H
            "h2h_home_win_pct": h2h["home_win_pct"],
            "h2h_matches": h2h["matches"],
            # Injury features — default 0 for historical (no data available)
            "home_injured_count": 0.0,
            "away_injured_count": 0.0,
            "injury_diff": 0.0,
            # Target
            "target": 1 if match["result"] == "home" else 0,
        }
        rows.append(row)

    return pd.DataFrame(rows)


def _team_bb_features(team_id: str, before: datetime, stats_df: pd.DataFrame,
                       matches_df: pd.DataFrame, is_home_split: bool) -> dict | None:
    past = matches_df[
        (matches_df["start_time"] < before) &
        ((matches_df["home_team_id"] == team_id) | (matches_df["away_team_id"] == team_id)) &
        (matches_df["result"].isin(["home", "away"]))
    ].tail(20)

    if len(past) < 3:
        return None

    team_stats = stats_df[stats_df["team_id"] == team_id]
    past_stats = team_stats[team_stats["match_id"].isin(past["id"])].sort_values("recorded_at")

    if len(past_stats) < 3:
        return None

    pts = past_stats["points"].dropna().values
    opp = past_stats["opp_points"].dropna().values

    pts_avg5 = float(np.mean(pts[-5:])) if len(pts) >= 5 else float(np.mean(pts))
    pts_avg10 = float(np.mean(pts[-10:])) if len(pts) >= 10 else float(np.mean(pts))
    opp_avg5 = float(np.mean(opp[-5:])) if len(opp) >= 5 else float(np.mean(opp))
    opp_avg10 = float(np.mean(opp[-10:])) if len(opp) >= 10 else float(np.mean(opp))
    pts_diff5 = pts_avg5 - opp_avg5

    wins = 0
    venue_wins = 0
    venue_games = 0
    for _, m in past.iterrows():
        won = (m["home_team_id"] == team_id and m["result"] == "home") or \
              (m["away_team_id"] == team_id and m["result"] == "away")
        if won:
            wins += 1
        is_venue_match = (m["home_team_id"] == team_id) == is_home_split
        if is_venue_match:
            venue_games += 1
            if won:
                venue_wins += 1

    win_pct = wins / len(past)
    win_pct_venue = venue_wins / venue_games if venue_games > 0 else win_pct

    # Rest days
    last_match_time = past["start_time"].max()
    rest_days = (before - last_match_time).days if pd.notna(last_match_time) else 7
    is_b2b = 1 if rest_days <= 1 else 0

    return {
        "pts_avg5": pts_avg5,
        "pts_avg10": pts_avg10,
        "opp_pts_avg5": opp_avg5,
        "opp_pts_avg10": opp_avg10,
        "pts_diff_avg5": pts_diff5,
        "win_pct": win_pct,
        "win_pct_venue": win_pct_venue,
        "rest_days": min(rest_days, 14),
        "is_b2b": is_b2b,
    }


def _h2h_basketball(home_id: str, away_id: str, before: datetime,
                     matches_df: pd.DataFrame) -> dict:
    h2h = matches_df[
        (matches_df["start_time"] < before) &
        (
            ((matches_df["home_team_id"] == home_id) & (matches_df["away_team_id"] == away_id)) |
            ((matches_df["home_team_id"] == away_id) & (matches_df["away_team_id"] == home_id))
        ) &
        (matches_df["result"].isin(["home", "away"]))
    ].tail(5)

    if len(h2h) == 0:
        return {"home_win_pct": 0.5, "matches": 0}

    home_wins = sum(
        1 for _, m in h2h.iterrows()
        if (m["home_team_id"] == home_id and m["result"] == "home") or
           (m["away_team_id"] == home_id and m["result"] == "away")
    )
    return {"home_win_pct": home_wins / len(h2h), "matches": len(h2h)}


# ── Football Features ──────────────────────────────────────────────────────────

def build_football_features(matches_df: pd.DataFrame, stats_df: pd.DataFrame) -> pd.DataFrame:
    """
    Returns DataFrame with one row per match + features + target (0=home, 1=draw, 2=away)
    xG features are the primary accuracy driver — use them when available.
    """
    stats_df = stats_df.copy()
    matches_df = matches_df.copy()
    matches_df["start_time"] = pd.to_datetime(matches_df["start_time"], utc=True)
    matches_df = matches_df.sort_values("start_time").reset_index(drop=True)

    target_map = {"home": 0, "draw": 1, "away": 2}
    rows = []

    for _, match in matches_df.iterrows():
        if match["result"] not in ("home", "draw", "away"):
            continue

        home_id = match["home_team_id"]
        away_id = match["away_team_id"]
        match_time = match["start_time"]
        league = match["league"]

        home_feats = _team_fb_features(home_id, match_time, stats_df, matches_df, is_home_split=True, league=league)
        away_feats = _team_fb_features(away_id, match_time, stats_df, matches_df, is_home_split=False, league=league)
        h2h = _h2h_football(home_id, away_id, match_time, matches_df)

        if home_feats is None or away_feats is None:
            continue

        row = {
            "match_id": match["id"],
            "league": league,
            "start_time": match_time,
            # Home team
            "home_goals_avg5": home_feats["goals_avg5"],
            "home_goals_avg10": home_feats["goals_avg10"],
            "home_conceded_avg5": home_feats["conceded_avg5"],
            "home_conceded_avg10": home_feats["conceded_avg10"],
            "home_xg_avg5": home_feats["xg_avg5"],
            "home_xg_conceded_avg5": home_feats["xg_conceded_avg5"],
            "home_win_pct": home_feats["win_pct"],
            "home_draw_pct": home_feats["draw_pct"],
            "home_win_pct_at_home": home_feats["win_pct_venue"],
            "home_rest_days": home_feats["rest_days"],
            "home_pts_per_game": home_feats["pts_per_game"],
            "home_shots_on_target_avg5": home_feats["sot_avg5"],
            # Away team
            "away_goals_avg5": away_feats["goals_avg5"],
            "away_goals_avg10": away_feats["goals_avg10"],
            "away_conceded_avg5": away_feats["conceded_avg5"],
            "away_conceded_avg10": away_feats["conceded_avg10"],
            "away_xg_avg5": away_feats["xg_avg5"],
            "away_xg_conceded_avg5": away_feats["xg_conceded_avg5"],
            "away_win_pct": away_feats["win_pct"],
            "away_draw_pct": away_feats["draw_pct"],
            "away_win_pct_away": away_feats["win_pct_venue"],
            "away_rest_days": away_feats["rest_days"],
            "away_pts_per_game": away_feats["pts_per_game"],
            "away_shots_on_target_avg5": away_feats["sot_avg5"],
            # Differentials (strong predictors)
            "diff_goals_avg5": home_feats["goals_avg5"] - away_feats["goals_avg5"],
            "diff_conceded_avg5": away_feats["conceded_avg5"] - home_feats["conceded_avg5"],
            "diff_xg_avg5": home_feats["xg_avg5"] - away_feats["xg_avg5"],
            "diff_win_pct": home_feats["win_pct"] - away_feats["win_pct"],
            "diff_pts_per_game": home_feats["pts_per_game"] - away_feats["pts_per_game"],
            # H2H
            "h2h_home_win_pct": h2h["home_win_pct"],
            "h2h_draw_pct": h2h["draw_pct"],
            "h2h_matches": h2h["matches"],
            # Target: 0=home, 1=draw, 2=away
            "target": target_map[match["result"]],
        }
        rows.append(row)

    return pd.DataFrame(rows)


def _team_fb_features(team_id: str, before: datetime, stats_df: pd.DataFrame,
                       matches_df: pd.DataFrame, is_home_split: bool, league: str) -> dict | None:
    past = matches_df[
        (matches_df["start_time"] < before) &
        ((matches_df["home_team_id"] == team_id) | (matches_df["away_team_id"] == team_id)) &
        (matches_df["result"].isin(["home", "draw", "away"]))
    ].tail(20)

    if len(past) < 3:
        return None

    team_stats = stats_df[stats_df["team_id"] == team_id]
    past_stats = team_stats[team_stats["match_id"].isin(past["id"])]

    if len(past_stats) < 3:
        return None

    goals = past_stats["goals"].fillna(0).values
    conceded = past_stats["opp_goals"].fillna(0).values
    xg = past_stats["xg"].dropna().values
    xg_conc = past_stats["opp_xg"].dropna().values
    sot = past_stats["shots_on_target"].dropna().values

    def safe_mean(arr, n):
        if len(arr) == 0:
            return 0.0
        return float(np.mean(arr[-n:]))

    goals_avg5 = safe_mean(goals, 5)
    goals_avg10 = safe_mean(goals, 10)
    conceded_avg5 = safe_mean(conceded, 5)
    conceded_avg10 = safe_mean(conceded, 10)
    xg_avg5 = safe_mean(xg, 5)
    xg_conc_avg5 = safe_mean(xg_conc, 5)
    sot_avg5 = safe_mean(sot, 5)

    wins = draws = 0
    venue_wins = venue_games = 0
    pts = 0
    for _, m in past.iterrows():
        is_home = m["home_team_id"] == team_id
        result = m["result"]
        won = (is_home and result == "home") or (not is_home and result == "away")
        drew = result == "draw"
        if won:
            wins += 1
            pts += 3
        if drew:
            draws += 1
            pts += 1
        if is_home == is_home_split:
            venue_games += 1
            if won:
                venue_wins += 1

    n = len(past)
    win_pct = wins / n
    draw_pct = draws / n
    win_pct_venue = venue_wins / venue_games if venue_games > 0 else win_pct
    pts_per_game = pts / n

    last_match_time = past["start_time"].max()
    rest_days = (before - last_match_time).days if pd.notna(last_match_time) else 7

    return {
        "goals_avg5": goals_avg5,
        "goals_avg10": goals_avg10,
        "conceded_avg5": conceded_avg5,
        "conceded_avg10": conceded_avg10,
        "xg_avg5": xg_avg5,
        "xg_conceded_avg5": xg_conc_avg5,
        "sot_avg5": sot_avg5,
        "win_pct": win_pct,
        "draw_pct": draw_pct,
        "win_pct_venue": win_pct_venue,
        "pts_per_game": pts_per_game,
        "rest_days": min(rest_days, 21),
    }


def _h2h_football(home_id: str, away_id: str, before: datetime,
                   matches_df: pd.DataFrame) -> dict:
    h2h = matches_df[
        (matches_df["start_time"] < before) &
        (
            ((matches_df["home_team_id"] == home_id) & (matches_df["away_team_id"] == away_id)) |
            ((matches_df["home_team_id"] == away_id) & (matches_df["away_team_id"] == home_id))
        ) &
        (matches_df["result"].isin(["home", "draw", "away"]))
    ].tail(5)

    if len(h2h) == 0:
        return {"home_win_pct": 0.45, "draw_pct": 0.27, "matches": 0}

    home_wins = draws = 0
    for _, m in h2h.iterrows():
        if (m["home_team_id"] == home_id and m["result"] == "home") or \
           (m["away_team_id"] == home_id and m["result"] == "away"):
            home_wins += 1
        if m["result"] == "draw":
            draws += 1

    return {
        "home_win_pct": home_wins / len(h2h),
        "draw_pct": draws / len(h2h),
        "matches": len(h2h),
    }


# ── Prediction Feature Vector (for inference, not training) ───────────────────

def build_inference_features_basketball(
    home_team_id: str, away_team_id: str,
    match_time: datetime,
    stats_df: pd.DataFrame, matches_df: pd.DataFrame,
    injury_map: dict | None = None,
) -> dict | None:
    home_feats = _team_bb_features(home_team_id, match_time, stats_df, matches_df, True)
    away_feats = _team_bb_features(away_team_id, match_time, stats_df, matches_df, False)
    h2h = _h2h_basketball(home_team_id, away_team_id, match_time, matches_df)
    if not home_feats or not away_feats:
        return None
    home_inj = float((injury_map or {}).get(home_team_id, 0))
    away_inj = float((injury_map or {}).get(away_team_id, 0))
    return {
        "home_pts_avg5": home_feats["pts_avg5"],
        "home_pts_avg10": home_feats["pts_avg10"],
        "home_opp_pts_avg5": home_feats["opp_pts_avg5"],
        "home_opp_pts_avg10": home_feats["opp_pts_avg10"],
        "home_win_pct": home_feats["win_pct"],
        "home_win_pct_at_home": home_feats["win_pct_venue"],
        "home_rest_days": home_feats["rest_days"],
        "home_b2b": home_feats["is_b2b"],
        "home_pts_diff_avg5": home_feats["pts_diff_avg5"],
        "away_pts_avg5": away_feats["pts_avg5"],
        "away_pts_avg10": away_feats["pts_avg10"],
        "away_opp_pts_avg5": away_feats["opp_pts_avg5"],
        "away_opp_pts_avg10": away_feats["opp_pts_avg10"],
        "away_win_pct": away_feats["win_pct"],
        "away_win_pct_away": away_feats["win_pct_venue"],
        "away_rest_days": away_feats["rest_days"],
        "away_b2b": away_feats["is_b2b"],
        "away_pts_diff_avg5": away_feats["pts_diff_avg5"],
        "diff_pts_avg5": home_feats["pts_avg5"] - away_feats["pts_avg5"],
        "diff_opp_pts_avg5": away_feats["opp_pts_avg5"] - home_feats["opp_pts_avg5"],
        "diff_win_pct": home_feats["win_pct"] - away_feats["win_pct"],
        "h2h_home_win_pct": h2h["home_win_pct"],
        "h2h_matches": h2h["matches"],
        "home_injured_count": home_inj,
        "away_injured_count": away_inj,
        "injury_diff": home_inj - away_inj,
    }


def build_inference_features_football(
    home_team_id: str, away_team_id: str, league: str,
    match_time: datetime,
    stats_df: pd.DataFrame, matches_df: pd.DataFrame
) -> dict | None:
    home_feats = _team_fb_features(home_team_id, match_time, stats_df, matches_df, True, league)
    away_feats = _team_fb_features(away_team_id, match_time, stats_df, matches_df, False, league)
    h2h = _h2h_football(home_team_id, away_team_id, match_time, matches_df)
    if not home_feats or not away_feats:
        return None
    return {
        "home_goals_avg5": home_feats["goals_avg5"],
        "home_goals_avg10": home_feats["goals_avg10"],
        "home_conceded_avg5": home_feats["conceded_avg5"],
        "home_conceded_avg10": home_feats["conceded_avg10"],
        "home_xg_avg5": home_feats["xg_avg5"],
        "home_xg_conceded_avg5": home_feats["xg_conceded_avg5"],
        "home_win_pct": home_feats["win_pct"],
        "home_draw_pct": home_feats["draw_pct"],
        "home_win_pct_at_home": home_feats["win_pct_venue"],
        "home_rest_days": home_feats["rest_days"],
        "home_pts_per_game": home_feats["pts_per_game"],
        "home_shots_on_target_avg5": home_feats["sot_avg5"],
        "away_goals_avg5": away_feats["goals_avg5"],
        "away_goals_avg10": away_feats["goals_avg10"],
        "away_conceded_avg5": away_feats["conceded_avg5"],
        "away_conceded_avg10": away_feats["conceded_avg10"],
        "away_xg_avg5": away_feats["xg_avg5"],
        "away_xg_conceded_avg5": away_feats["xg_conceded_avg5"],
        "away_win_pct": away_feats["win_pct"],
        "away_draw_pct": away_feats["draw_pct"],
        "away_win_pct_away": away_feats["win_pct_venue"],
        "away_rest_days": away_feats["rest_days"],
        "away_pts_per_game": away_feats["pts_per_game"],
        "away_shots_on_target_avg5": away_feats["sot_avg5"],
        "diff_goals_avg5": home_feats["goals_avg5"] - away_feats["goals_avg5"],
        "diff_conceded_avg5": away_feats["conceded_avg5"] - home_feats["conceded_avg5"],
        "diff_xg_avg5": home_feats["xg_avg5"] - away_feats["xg_avg5"],
        "diff_win_pct": home_feats["win_pct"] - away_feats["win_pct"],
        "diff_pts_per_game": home_feats["pts_per_game"] - away_feats["pts_per_game"],
        "h2h_home_win_pct": h2h["home_win_pct"],
        "h2h_draw_pct": h2h["draw_pct"],
        "h2h_matches": h2h["matches"],
    }
