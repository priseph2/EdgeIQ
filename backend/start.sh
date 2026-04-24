#!/bin/bash
set -e

echo "=== EdgeIQ Backend Startup ==="
mkdir -p models

echo "Python path:"
python -c "import sys; print(sys.path)"

echo "Installing dependencies..."
python -m pip install -r requirements.txt 2>&1 | tail -20

echo "Checking fastapi..."
python -c "import fastapi; print('fastapi OK:', fastapi.__version__)" || echo "fastapi NOT found"

echo "Pip list (fastapi):"
python -m pip list 2>/dev/null | grep -i "fastapi" || echo "fastapi not in pip list"

# Run ingestion + training in background so uvicorn starts immediately
if [ "${RUN_INGESTION_ON_START:-false}" = "true" ]; then
  (
    echo "Starting background ingestion..."
    python -m data.ingest_nba && echo "NBA ingest done" || echo "NBA ingest failed"

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
