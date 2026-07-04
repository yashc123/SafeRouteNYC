# Production image for the SafeRouteNYC backend (FastAPI) AND the one-time data
# pipeline — both need the same code + dependencies, so we ship one image. The
# build context is the REPO ROOT so we can copy both backend/ and data/.
#
#   build:  docker compose -f docker-compose.prod.yml build backend
#   (context: .  dockerfile: backend/Dockerfile  — see docker-compose.prod.yml)
FROM python:3.12-slim

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PIP_NO_CACHE_DIR=1

WORKDIR /app

# Install Python deps first for a cached layer. All wheels are prebuilt manylinux
# (psycopg2-binary, shapely, pyproj, pyogrio, scipy, numpy...), so no apt build
# tools are needed on slim.
COPY backend/requirements.txt ./backend/requirements.txt
RUN pip install --upgrade pip && pip install -r backend/requirements.txt

# App code: the API (backend/) and the ingestion/scoring pipeline (data/).
COPY backend/ ./backend/
COPY data/ ./data/

WORKDIR /app/backend
EXPOSE 8000

# /health works even before data is loaded, so this reports healthy quickly.
HEALTHCHECK --interval=15s --timeout=5s --start-period=40s --retries=6 \
  CMD python -c "import urllib.request,sys; sys.exit(0 if urllib.request.urlopen('http://127.0.0.1:8000/health').status==200 else 1)"

# Production server: NO --reload. A single worker keeps just one copy of the
# in-memory street graph; add workers only if you also add RAM (each worker loads
# its own graph at startup).
CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8000"]
