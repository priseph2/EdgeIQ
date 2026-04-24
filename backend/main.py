"""
EdgeIQ FastAPI backend.
Run: uvicorn main:app --reload --port 8000
"""

import logging
import subprocess
from contextlib import asynccontextmanager
from fastapi import FastAPI, HTTPException, BackgroundTasks
from fastapi.middleware.cors import CORSMiddleware

from routers.predictions import router as predictions_router
from routers.bets import router as bets_router
from routers.odds import router as odds_router

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    logger.info("EdgeIQ backend starting up")
    from scheduler import create_scheduler
    scheduler = create_scheduler()
    scheduler.start()
    logger.info("Scheduler started")
    yield
    scheduler.shutdown(wait=False)
    logger.info("EdgeIQ backend shutting down")


app = FastAPI(
    title="EdgeIQ API",
    description="Sports betting intelligence — predictions, odds, bet tracker",
    version="1.0.0",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:3000", "https://edgeiq.vercel.app", "https://*.vercel.app"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(predictions_router)
app.include_router(bets_router)
app.include_router(odds_router)


@app.get("/health")
async def health():
    return {"status": "ok", "service": "EdgeIQ API"}


# ── Admin endpoints ────────────────────────────────────────────────────────────

import os

def _check(token: str):
    expected = os.environ.get("ADMIN_TOKEN", "")
    if not expected or token != expected:
        raise HTTPException(status_code=403, detail="Invalid token")

def _run_bg(cmd: list[str]):
    logger.info(f"Running: {' '.join(cmd)}")
    result = subprocess.run(cmd, capture_output=True, text=True, timeout=600)
    logger.info(result.stdout[-1000:] if result.stdout else "no output")
    if result.stderr:
        logger.error(result.stderr[-500:])

@app.get("/admin/ingest/nba")
async def admin_ingest_nba(token: str, background_tasks: BackgroundTasks):
    _check(token)
    background_tasks.add_task(_run_bg, ["python", "-m", "data.ingest_nba"])
    return {"status": "NBA ingestion started — watch Railway logs (5-8 mins)"}

@app.get("/admin/ingest/nba/fixtures")
async def admin_ingest_nba_fixtures(token: str, background_tasks: BackgroundTasks):
    """Quick NBA fixture refresh — fetches next 14 days of games (~30s)."""
    _check(token)
    background_tasks.add_task(_run_bg, ["python", "-m", "data.ingest_nba_fixtures"])
    return {"status": "NBA fixture refresh started — watch Railway logs (~30s)"}

@app.get("/admin/ingest/football")
async def admin_ingest_football(token: str, background_tasks: BackgroundTasks):
    _check(token)
    background_tasks.add_task(_run_bg, ["python", "-m", "data.ingest_football"])
    return {"status": "Football ingestion started — watch Railway logs (8-10 mins)"}

@app.get("/admin/ingest/odds")
async def admin_ingest_odds(token: str, background_tasks: BackgroundTasks):
    """Manually trigger odds ingestion (uses ~6 of your 500 monthly requests)."""
    _check(token)
    background_tasks.add_task(_run_bg, ["python", "-m", "data.ingest_odds"])
    return {"status": "Odds ingestion started — watch Railway logs (~30s)"}

@app.get("/admin/ingest/fixtures")
async def admin_ingest_fixtures(token: str, background_tasks: BackgroundTasks):
    """Quick fixture refresh — fetches only the current matchday for all leagues (~30s)."""
    _check(token)
    background_tasks.add_task(_run_bg, ["python", "-m", "data.ingest_fixtures"])
    return {"status": "Fixture refresh started — watch Railway logs (~30s)"}

@app.get("/admin/train/{sport}")
async def admin_train(sport: str, token: str, background_tasks: BackgroundTasks):
    if sport not in ("basketball", "football", "all"):
        raise HTTPException(400, "sport must be basketball, football, or all")
    _check(token)
    if sport == "all":
        background_tasks.add_task(_run_bg, ["python", "-m", "ml.train", "--sport", "basketball"])
        background_tasks.add_task(_run_bg, ["python", "-m", "ml.train", "--sport", "football"])
    else:
        background_tasks.add_task(_run_bg, ["python", "-m", "ml.train", "--sport", sport])
    return {"status": f"Training {sport} started — watch Railway logs (2-3 mins)"}

@app.get("/admin/predict-debug")
async def admin_predict_debug(token: str):
    """Runs prediction logic for today's football matches and shows exactly what fails."""
    _check(token)
    import traceback
    import pandas as pd
    from datetime import datetime, timezone, timedelta
    from supabase import create_client
    from config import get_settings
    from ml.features import build_inference_features_football
    from ml.predict import load_model

    s = get_settings()
    sb = create_client(s.supabase_url, s.supabase_service_role_key)

    now = datetime.now(timezone.utc)
    today_start = now.replace(hour=0, minute=0, second=0, microsecond=0)
    today_end = today_start + timedelta(days=1)

    FOOTBALL_LEAGUES = ["Premier League", "La Liga", "Bundesliga", "Serie A", "Ligue 1"]

    def fetch_all(query):
        data, page, size = [], 0, 1000
        while True:
            res = query.range(page * size, (page + 1) * size - 1).execute()
            data.extend(res.data or [])
            if len(res.data or []) < size:
                break
            page += 1
        return data

    matches_data = fetch_all(sb.table("matches").select(
        "id,home_team_id,away_team_id,league,start_time,status,result,"
        "home_team:teams!home_team_id(name),away_team:teams!away_team_id(name)"
    ).in_("league", FOOTBALL_LEAGUES))
    stats_data = fetch_all(sb.table("team_stats_football").select("*"))

    matches_df = pd.DataFrame(matches_data)
    stats_df = pd.DataFrame(stats_data)
    if not matches_df.empty:
        matches_df["start_time"] = pd.to_datetime(matches_df["start_time"], utc=True)

    today_matches = matches_df[
        (matches_df["start_time"] >= today_start) &
        (matches_df["start_time"] < today_end) &
        (matches_df["status"] == "scheduled")
    ] if not matches_df.empty else pd.DataFrame()

    results = []
    for _, match in today_matches.iterrows():
        home_name = (match.get("home_team") or {}).get("name", "?")
        away_name = (match.get("away_team") or {}).get("name", "?")
        home_id = match["home_team_id"]
        away_id = match["away_team_id"]
        match_time = match["start_time"].to_pydatetime()

        info = {"match": f"{home_name} vs {away_name}", "league": match["league"]}

        # Check historical matches per team
        for label, tid in [("home", home_id), ("away", away_id)]:
            past = matches_df[
                (matches_df["start_time"] < match_time) &
                ((matches_df["home_team_id"] == tid) | (matches_df["away_team_id"] == tid)) &
                (matches_df["result"].isin(["home", "draw", "away"]))
            ]
            team_stats = stats_df[stats_df["team_id"] == tid]
            past_stats = team_stats[team_stats["match_id"].isin(past["id"])]
            info[f"{label}_past_matches"] = len(past)
            info[f"{label}_past_stats"] = len(past_stats)

        try:
            model_artifact = load_model("football")
            feats = build_inference_features_football(home_id, away_id, match["league"], match_time, stats_df, matches_df)
            if feats is None:
                info["result"] = "FAILED: build_inference_features returned None"
            else:
                import numpy as np
                X = np.array([[feats.get(c, 0.0) for c in model_artifact["feature_cols"]]])
                probs = model_artifact["model"].predict_proba(X)[0]
                info["result"] = "OK"
                info["probs"] = {"home": round(float(probs[0]),3), "draw": round(float(probs[1]),3), "away": round(float(probs[2]),3)}
        except Exception as e:
            info["result"] = f"ERROR: {e}"
            info["traceback"] = traceback.format_exc()[-500:]

        results.append(info)

    return {
        "total_matches_in_db": len(matches_df),
        "total_stats_rows": len(stats_df),
        "today_matches_found": len(today_matches),
        "details": results,
    }

@app.get("/admin/status")
async def admin_status(token: str):
    """Shows DB record counts — poll this to track ingestion progress."""
    _check(token)
    from pathlib import Path
    from supabase import create_client
    from config import get_settings

    s = get_settings()
    sb = create_client(s.supabase_url, s.supabase_service_role_key)

    bb_matches = sb.table("matches").select("id", count="exact").eq("sport", "basketball").execute()
    bb_stats   = sb.table("team_stats_basketball").select("id", count="exact").execute()
    fb_matches = sb.table("matches").select("id", count="exact").eq("sport", "football").execute()
    fb_stats   = sb.table("team_stats_football").select("id", count="exact").execute()
    bb_sched   = sb.table("matches").select("id", count="exact").eq("sport", "basketball").eq("status", "scheduled").execute()

    models_dir = Path("/app/ml/models")
    return {
        "basketball": {
            "matches_total": bb_matches.count,
            "matches_scheduled": bb_sched.count,
            "stats_rows": bb_stats.count,
            "model_ready": (models_dir / "basketball_v1.pkl").exists(),
        },
        "football": {
            "matches_total": fb_matches.count,
            "stats_rows": fb_stats.count,
            "model_ready": (models_dir / "football_v1.pkl").exists(),
        },
    }

@app.get("/admin/debug")
async def admin_debug(token: str):
    """Show today's scheduled matches in DB + model file status."""
    _check(token)
    from datetime import datetime, timezone, timedelta
    from pathlib import Path
    from supabase import create_client
    from config import get_settings

    s = get_settings()
    sb = create_client(s.supabase_url, s.supabase_service_role_key)

    now = datetime.now(timezone.utc)
    today_start = now.replace(hour=0, minute=0, second=0, microsecond=0).isoformat()
    today_end = (now.replace(hour=0, minute=0, second=0, microsecond=0) + timedelta(days=1)).isoformat()

    football_today = sb.table("matches").select(
        "id,league,start_time,status,home_team_id,away_team_id,"
        "home_team:teams!home_team_id(name),away_team:teams!away_team_id(name)"
    ).eq("sport", "football").gte("start_time", today_start).lt("start_time", today_end).execute()

    basketball_today = sb.table("matches").select("id,league,start_time,status").eq("sport", "basketball")\
        .gte("start_time", today_start).lt("start_time", today_end).execute()

    football_sched = sb.table("matches").select("id", count="exact").eq("sport", "football")\
        .eq("status", "scheduled").execute()
    basketball_sched = sb.table("matches").select("id", count="exact").eq("sport", "basketball")\
        .eq("status", "scheduled").execute()

    # Check whether today's match teams have historical stats
    team_stats = {}
    for m in football_today.data:
        for col in ("home_team_id", "away_team_id"):
            tid = m.get(col)
            if tid and tid not in team_stats:
                cnt = sb.table("team_stats_football").select("id", count="exact").eq("team_id", tid).execute()
                team_stats[tid] = {"count": cnt.count, "name": (m.get("home_team") or m.get("away_team") or {}).get("name")}

    models_dir = Path("/app/ml/models")
    return {
        "server_time_utc": now.isoformat(),
        "today_football": football_today.data,
        "today_basketball": basketball_today.data,
        "total_scheduled_football": football_sched.count,
        "total_scheduled_basketball": basketball_sched.count,
        "team_stats_counts": team_stats,
        "models_on_disk": {
            "football_v1": (models_dir / "football_v1.pkl").exists(),
            "basketball_v1": (models_dir / "basketball_v1.pkl").exists(),
        },
    }
