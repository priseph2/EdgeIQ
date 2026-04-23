"""
EdgeIQ FastAPI backend.
Run: uvicorn main:app --reload --port 8000
"""

import logging
from contextlib import asynccontextmanager
from fastapi import FastAPI
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
    allow_origins=["http://localhost:3000", "https://edgeiq.vercel.app"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(predictions_router)
app.include_router(bets_router)


@app.get("/health")
async def health():
    return {"status": "ok", "service": "EdgeIQ API"}
