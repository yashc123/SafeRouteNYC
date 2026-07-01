"""SafePath backend — FastAPI application entrypoint.

Phase 0: a single health-check endpoint plus CORS so the Vite frontend
(running on localhost) can call this API during development. Routing,
data, and city endpoints arrive in later phases.
"""

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

app = FastAPI(title="SafePath API", version="0.0.0")

# Allow the local Vite dev server (and common localhost variants) to call the API.
# Tighten / parameterize this for production deployment later.
app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "http://localhost:5173",
        "http://127.0.0.1:5173",
    ],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.get("/health")
def health():
    """Liveness probe. Returns a static payload so uptime checks (and later,
    load balancers / container orchestrators) can confirm the API is up."""
    return {"status": "ok"}
