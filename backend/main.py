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

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    logger.info("EdgeIQ backend starting up")
    yield
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

@app.get("/admin/ingest/football")
async def admin_ingest_football(token: str, background_tasks: BackgroundTasks):
    _check(token)
    background_tasks.add_task(_run_bg, ["python", "-m", "data.ingest_football"])
    return {"status": "Football ingestion started — watch Railway logs (8-10 mins)"}

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
