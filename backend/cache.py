"""SafeRouteNYC tier-3 cache: Redis-backed cache of full /route and /reachable results.

Where this sits in the three-tier caching architecture:
  Tier 1 - PostGIS edge_safety: the expensive per-segment geospatial join +
           scoring, precomputed once offline. Saves re-running a 340k-point
           spatial join on every request.
  Tier 2 - in-memory NetworkX graph (routing.py): loaded once at startup. Saves a
           database round-trip per edge during the A*/Dijkstra search.
  Tier 3 - THIS module: caches the full computed result of a route/reachable
           request. Saves the entire graph search when the same query repeats.

Fail-safe by design: if Redis is unavailable the app must still answer (just
without caching). Every operation is wrapped, connects lazily with short timeouts,
and a small circuit breaker skips Redis for a cooldown after a failure so a down
Redis doesn't stall every request waiting on a timeout.
"""

import json
import os
import time
from pathlib import Path

import redis
from dotenv import load_dotenv

# Load config the same cwd-independent way as database.py.
load_dotenv(Path(__file__).resolve().parent / ".env")

REDIS_URL = os.getenv("REDIS_URL", "redis://localhost:6379/0")
# TTL: safety weights change only when data is re-ingested, so hours is plenty.
# 6h keeps popular routes hot through a day without serving stale data for long.
CACHE_TTL_SECONDS = int(os.getenv("CACHE_TTL_SECONDS", "21600"))

# After a Redis failure, skip Redis entirely for this many seconds (circuit breaker)
# so we don't pay the connect timeout on every request while it's down.
CACHE_CIRCUIT_COOLDOWN_S = 30.0

# Short timeouts so a down Redis fails fast instead of hanging a request.
_CONNECT_TIMEOUT_S = 0.3
_OP_TIMEOUT_S = 0.3


class Cache:
    """Thin, fail-safe wrapper around a Redis client."""

    def __init__(self, url=REDIS_URL, ttl=CACHE_TTL_SECONDS):
        self.ttl = ttl
        self._down_until = 0.0  # circuit-breaker: skip Redis until this monotonic time
        # from_url is lazy (no connection yet), so this never raises if Redis is down.
        self._client = redis.Redis.from_url(
            url,
            socket_connect_timeout=_CONNECT_TIMEOUT_S,
            socket_timeout=_OP_TIMEOUT_S,
            decode_responses=True,
        )

    def _open(self):
        """True if we should attempt Redis (circuit not tripped)."""
        return time.monotonic() >= self._down_until

    def _trip(self):
        self._down_until = time.monotonic() + CACHE_CIRCUIT_COOLDOWN_S

    def get(self, key):
        """Return the cached object for `key`, or None on miss / any Redis problem."""
        if not self._open():
            return None
        try:
            raw = self._client.get(key)
            return json.loads(raw) if raw is not None else None
        except redis.RedisError:
            self._trip()
            return None
        except Exception:
            return None

    def set(self, key, value):
        """Store `value` (JSON-serializable) under `key` with the TTL. No-op on failure."""
        if not self._open():
            return
        try:
            self._client.set(key, json.dumps(value), ex=self.ttl)
        except redis.RedisError:
            self._trip()
        except Exception:
            pass

    def ping(self):
        """Health probe; True if Redis answers, False otherwise."""
        try:
            return bool(self._client.ping())
        except Exception:
            return False


def route_key(src_node, dst_node, alpha, time_of_day):
    """Key routes on the SNAPPED node ids (not raw lat/lng): many nearby input
    coordinates snap to the same graph nodes and therefore share one cache entry,
    which greatly raises the hit rate for real-world (imprecise) clicks/GPS."""
    return f"route:{src_node}:{dst_node}:{alpha:g}:{time_of_day}"


def reachable_key(src_node, alpha, time_of_day, budget_min):
    return f"reach:{src_node}:{alpha:g}:{time_of_day}:{budget_min:g}"


# Module-level singleton.
cache = Cache()
