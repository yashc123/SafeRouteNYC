#!/usr/bin/env bash
# One-time (or refresh) data load for a running PRODUCTION stack. Runs the three
# pipeline steps INSIDE the backend container (which has the data/ scripts + deps
# and reaches the DB as db:5432), then restarts the backend so it loads the newly
# populated graph into memory.
#
# Run from the repo root, after `docker compose ... up -d`, with .env.prod present:
#   bash deploy/load-data.sh
#
# Takes ~10-15 min total (downloads the Manhattan graph from OSM + ~340k NYC crime
# rows). Safe to re-run; every step is idempotent (truncate-and-reload).
set -euo pipefail

COMPOSE="docker compose --env-file .env.prod -f docker-compose.prod.yml"

echo "==> 1/3  Ingesting Manhattan street graph (downloads from OpenStreetMap)..."
$COMPOSE exec -T backend python /app/data/ingest_street_graph.py

echo "==> 2/3  Ingesting NYC crime / streetlight / 311 data..."
$COMPOSE exec -T backend python /app/data/ingest_nyc_data.py

echo "==> 3/3  Computing per-segment safety scores..."
$COMPOSE exec -T backend python /app/data/compute_safety_scores.py

echo "==> Restarting backend so it loads the populated graph into memory..."
$COMPOSE restart backend

echo "Done. Verify with:  curl http://localhost/api/graph/stats"
