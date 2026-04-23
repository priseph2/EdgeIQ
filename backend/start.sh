#!/bin/bash
set -e

echo "=== EdgeIQ Backend Startup ==="

# Create models directory
mkdir -p models

# Run NBA ingestion if no data exists yet (first deploy)
if [ "${RUN_INGESTION_ON_START:-false}" = "true" ]; then
  echo "Running NBA data ingestion..."
  python -m data.ingest_nba || echo "NBA ingestion failed — continuing"

  if [ -n "$FOOTBALL_DATA_API_KEY" ]; then
    echo "Running football data ingestion..."
    python -m data.ingest_football || echo "Football ingestion failed — continuing"
  fi

  if [ -n "$RAPIDAPI_KEY" ]; then
    echo "Running EuroLeague data ingestion..."
    python -m data.ingest_euro_bb || echo "EuroLeague ingestion failed — continuing"
  fi
fi

# Train models if not already trained
if [ "${RUN_TRAINING_ON_START:-false}" = "true" ]; then
  echo "Training models..."
  python -m ml.train --sport all || echo "Model training failed — continuing"
fi

echo "Starting FastAPI server..."
exec uvicorn main:app --host 0.0.0.0 --port "${PORT:-8000}"
