"""Everything we have already fetched, remembered across restarts.

Render gives a free service no persistent disk, so `.cache/` is destroyed on
every deploy and every page is bought again. That is money leaking for no
reason, and it gets worse the more often we deploy.

Postgres when `DATABASE_URL` is set, plain JSON files on disk when it is not.
Local development must never need a database, and the demo must never fail
because one is unreachable -- a cache that can take the app down is worse than
no cache at all, so every failure here degrades to "not cached".

Nothing is stored that could not be fetched again. This is a cache, not a
source of truth.
"""

from __future__ import annotations

import json
import logging
import time
from typing import Any

from . import config

log = logging.getLogger(__name__)

CACHE_DIR = config.ROOT / ".cache" / "web"

# How long a fetched thing stays trustworthy, by what kind of thing it is.
#
# This is the only defence against the one failure the guard rails cannot
# catch: a stale page. If Notion changes its price and we hold the old page,
# the verdict is confidently wrong AND the quote still verifies, because the
# sentence really is on the page we stored.
TTL_SECONDS = {
    "volatile": 3 * 86400,     # prices, headcounts, anything "current"
    "news": 3 * 86400,
    "reference": 14 * 86400,   # wikipedia and the like
    "historical": 60 * 86400,  # records, biography, things that happened
    "entity": 180 * 86400,     # an official website effectively never moves
}
DEFAULT_KIND = "reference"


def ttl_for(kind: str, shape: str = "") -> int:
    """Pick a lifetime from what the sorter already told us about the claim.

    No extra model call: `kind` and `shape` come free with every claim.
    """
    if kind in ("prediction",):
        return TTL_SECONDS["news"]
    if shape == "count":
        # A quantity is the thing most likely to have changed since we looked.
        return TTL_SECONDS["volatile"]
    return TTL_SECONDS[DEFAULT_KIND]


# --- postgres, when there is one -------------------------------------------

_pool = None
_pg_ready = False


async def _pg():
    """The connection pool, created once. None means "no database"."""
    global _pool, _pg_ready
    if _pg_ready:
        return _pool
    _pg_ready = True

    url = config.DATABASE_URL
    if not url:
        log.info("store: no DATABASE_URL, using files in %s", CACHE_DIR)
        return None
    try:
        import asyncpg

        _pool = await asyncpg.create_pool(
            pg_url(url), min_size=1, max_size=4, timeout=10
        )
        async with _pool.acquire() as c:
            await c.execute(
                """
                CREATE TABLE IF NOT EXISTS cache (
                    kind       TEXT        NOT NULL,
                    key        TEXT        NOT NULL,
                    value      JSONB       NOT NULL,
                    stored_at  BIGINT      NOT NULL,
                    expires_at BIGINT,
                    PRIMARY KEY (kind, key)
                )
                """
            )
        log.info("store: postgres ready")
    except Exception as exc:  # noqa: BLE001
        # A database we cannot reach must not take the app down with it.
        # But falling back SILENTLY is how you end up believing a cache is
        # working for a week while every claim is bought again, so the reason
        # is kept and /health reports it.
        global _pg_error
        _pg_error = f"{type(exc).__name__}: {exc}"
        log.warning("store: postgres unavailable (%s), using files", _pg_error)
        _pool = None
    return _pool


def pg_url(url: str) -> str:
    """Make a hosted provider's connection string safe for asyncpg.

    Neon hands out `...?sslmode=require&channel_binding=require`. asyncpg has
    never supported `channel_binding` and raises on it, so the pool fails, the
    store quietly falls back to files, and the database that was just set up
    is never touched. Supabase adds `pgbouncer=true`, which asyncpg also does
    not know.

    Unknown parameters are dropped rather than passed through. `sslmode` is
    kept, because asyncpg does understand it and Neon requires TLS.
    """
    from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit

    parts = urlsplit(url.strip())
    keep = [(k, v) for k, v in parse_qsl(parts.query, keep_blank_values=True)
            if k in ASYNCPG_PARAMS]
    dropped = {k for k, _ in parse_qsl(parts.query)} - ASYNCPG_PARAMS
    if dropped:
        log.info("store: dropped unsupported url params %s", sorted(dropped))

    scheme = parts.scheme
    if scheme in ("postgresql+asyncpg", "postgres+asyncpg"):
        scheme = "postgresql"

    return urlunsplit((scheme, parts.netloc, parts.path, urlencode(keep), ""))


# Everything asyncpg will actually accept from a DSN query string.
ASYNCPG_PARAMS = {
    "sslmode", "sslcert", "sslkey", "sslrootcert", "sslcrl",
    "host", "port", "user", "password", "database", "dbname",
    "application_name", "server_settings", "target_session_attrs",
    "passfile", "connect_timeout",
}

_pg_error: str = ""


def backend() -> dict[str, str]:
    """What the store is ACTUALLY using, for /health.

    The whole point is that this cannot be guessed from the outside. A
    misconfigured database and no database at all behave identically -- both
    keep serving claims, both just forget everything on restart.
    """
    if _pool is not None:
        return {"store": "postgres"}
    if not config.DATABASE_URL:
        return {"store": "files", "why": "DATABASE_URL is not set"}
    return {"store": "files", "why": _pg_error or "not connected yet"}


# --- the interface the rest of the app uses --------------------------------


def _path(kind: str, key: str):
    import hashlib

    digest = hashlib.sha256(key.encode()).hexdigest()[:24]
    return CACHE_DIR / f"{kind}_{digest}.json"


async def get(kind: str, key: str) -> Any | None:
    """What we stored, or None if we never did or it has expired."""
    now = int(time.time())

    pool = await _pg()
    if pool is not None:
        try:
            async with pool.acquire() as c:
                row = await c.fetchrow(
                    "SELECT value, expires_at FROM cache WHERE kind=$1 AND key=$2",
                    kind, key,
                )
            if row and (row["expires_at"] is None or row["expires_at"] > now):
                return json.loads(row["value"])
            return None
        except Exception as exc:  # noqa: BLE001
            log.warning("store: read failed (%s), falling back to files", exc)

    path = _path(kind, key)
    if not path.exists():
        return None
    try:
        held = json.loads(path.read_text())
    except json.JSONDecodeError:
        return None
    if held.get("expires_at") and held["expires_at"] <= now:
        return None
    return held.get("value")


async def put(kind: str, key: str, value: Any, ttl: int | None = None) -> None:
    """Remember something. Failure here is never fatal -- it just means we
    fetch it again next time, which is exactly where we started."""
    now = int(time.time())
    expires = now + ttl if ttl else None

    pool = await _pg()
    if pool is not None:
        try:
            async with pool.acquire() as c:
                await c.execute(
                    """
                    INSERT INTO cache (kind, key, value, stored_at, expires_at)
                    VALUES ($1, $2, $3, $4, $5)
                    ON CONFLICT (kind, key) DO UPDATE
                      SET value=$3, stored_at=$4, expires_at=$5
                    """,
                    kind, key, json.dumps(value), now, expires,
                )
            return
        except Exception as exc:  # noqa: BLE001
            log.warning("store: write failed (%s), falling back to files", exc)

    CACHE_DIR.mkdir(parents=True, exist_ok=True)
    _path(kind, key).write_text(json.dumps({"value": value, "expires_at": expires}))


async def forget(kind: str, key: str) -> bool:
    """Drop one entry, for when a stale page is spotted during a demo and
    waiting for its TTL is not an option."""
    pool = await _pg()
    if pool is not None:
        try:
            async with pool.acquire() as c:
                await c.execute("DELETE FROM cache WHERE kind=$1 AND key=$2", kind, key)
        except Exception:  # noqa: BLE001
            pass
    path = _path(kind, key)
    if path.exists():
        path.unlink()
        return True
    return False


async def summary() -> dict[str, Any]:
    pool = await _pg()
    if pool is not None:
        try:
            async with pool.acquire() as c:
                rows = await c.fetch("SELECT kind, count(*) n FROM cache GROUP BY kind")
            return {"backend": "postgres", **{r["kind"]: r["n"] for r in rows}}
        except Exception:  # noqa: BLE001
            pass
    counts: dict[str, int] = {}
    if CACHE_DIR.exists():
        for f in CACHE_DIR.glob("*.json"):
            counts[f.name.split("_")[0]] = counts.get(f.name.split("_")[0], 0) + 1
    return {"backend": "files", **counts}
