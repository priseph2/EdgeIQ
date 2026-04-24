"""Admin router — data ingestion and model training triggers."""

import logging
import asyncio
from fastapi import APIRouter, HTTPException, BackgroundTasks
from config import get_settings

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/admin", tags=["admin"])


def _get_token():
    return get_settings().admin_token or ""


def _check_token(token: str):
    expected = _get_token()
    if not expected or token != expected:
        raise HTTPException(status_code=403, detail="Invalid or missing admin token")


async def _run(cmd: list[str]) -> str:
    proc = await asyncio.create_subprocess_exec(
        *cmd,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.STDOUT,
    )
    stdout, _ = await proc.communicate()
    return stdout.decode()


def _run_ingest_nba():
    import subprocess
    result = subprocess.run(
        ["python", "-m", "data.ingest_nba"],
        capture_output=True, text=True, timeout=600
    )
    logger.info(f"NBA ingest done: {result.stdout[-500:]} {result.stderr[-200:]}")


def _run_ingest_football():
    import subprocess
    result = subprocess.run(
        ["python", "-m", "data.ingest_football"],
        capture_output=True, text=True, timeout=600
    )
    logger.info(f"Football ingest done: {result.stdout[-500:]} {result.stderr[-200:]}")


def _run_train(sport: str):
    import subprocess
    result = subprocess.run(
        ["python", "-m", "ml.train", "--sport", sport],
        capture_output=True, text=True, timeout=600
    )
    logger.info(f"Train {sport} done: {result.stdout[-500:]} {result.stderr[-200:]}")


@router.get("/ingest/nba")
async def ingest_nba(token: str, background_tasks: BackgroundTasks):
    _check_token(token)
    background_tasks.add_task(_run_ingest_nba)
    return {"status": "NBA ingestion started — check Railway logs for progress (5-8 mins)"}


@router.get("/ingest/football")
async def ingest_football(token: str, background_tasks: BackgroundTasks):
    _check_token(token)
    background_tasks.add_task(_run_ingest_football)
    return {"status": "Football ingestion started — check Railway logs for progress (8-10 mins)"}


@router.get("/train/{sport}")
async def train_model(sport: str, token: str, background_tasks: BackgroundTasks):
    if sport not in ("basketball", "football", "all"):
        raise HTTPException(400, "sport must be basketball, football, or all")
    _check_token(token)
    if sport == "all":
        background_tasks.add_task(_run_train, "basketball")
        background_tasks.add_task(_run_train, "football")
    else:
        background_tasks.add_task(_run_train, sport)
    return {"status": f"Training {sport} model started — check Railway logs (2-3 mins)"}
