#!/bin/bash
set -e

export PATH="/opt/venv/bin:$PATH"

echo "=== EdgeIQ Backend Startup ==="
mkdir -p models

echo "Python: $(python --version), FastAPI: $(python -c 'import fastapi; print(fastapi.__version__)' 2>/dev/null || echo NOT FOUND)"

if [ "${RUN_INGESTION_ON_START:-false}" = "true" ]; then
  (
    echo "Starting background ingestion..."

    if [ -n "$FOOTBALL_DATA_API_KEY" ]; then
      python -m data.ingest_football && echo "Football ingest done" || echo "Football ingest failed"
    fi

    if [ -n "$RAPIDAPI_KEY" ]; then
      python -m data.ingest_euro_bb && echo "EuroLeague ingest done" || echo "EuroLeague ingest failed"
    fi

    if [ "${RUN_TRAINING_ON_START:-false}" = "true" ]; then
      python -m ml.train --sport all && echo "Training done" || echo "Training failed"
    fi

    echo "Background pipeline complete"
  ) &
fi

echo "Starting FastAPI server..."
exec python -m uvicorn main:app --host 0.0.0.0 --port "${PORT:-8000}"
