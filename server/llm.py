"""Every Claude call goes through here, so four things are always true:

  1. An identical repeat call is free and instant (on-disk cache).
  2. Prompt caching is NOT used, and the reason is written down below so
     nobody adds it again expecting a saving.
  3. A session cannot exceed its call budget.
  4. Every call logs its tokens, its cost, and a running total.

The on-disk cache matters more than it sounds during development: the server
reloads on every file save and you will run the same test sentence twenty
times in an afternoon. With the cache that is one call, not twenty. Because
the prompt is part of the cache key, editing a prompt invalidates it
automatically -- there is never a stale answer from a prompt you changed.
"""

from __future__ import annotations

import hashlib
import json
import logging
import time
from pathlib import Path
from typing import Any, TypeVar

import httpx
from anthropic import AsyncAnthropic
from pydantic import BaseModel

from . import config

log = logging.getLogger(__name__)

CACHE_DIR = config.ROOT / ".cache" / "llm"
CACHE_DIR.mkdir(parents=True, exist_ok=True)

# Dollars per million tokens, for the running total in the logs only.
PRICES = {
    "claude-haiku-4-5": (1.0, 5.0),
    "claude-sonnet-5": (2.0, 10.0),
    "claude-opus-5": (5.0, 25.0),
}

# Anthropic's prompt cache has a per-model minimum PREFIX length, and below it
# a cache_control block is accepted, does nothing, and reports
# cache_read_input_tokens: 0 forever. There is no error and no warning.
#
#   Opus 5, Fable 5/5.1            512 tokens
#   Opus 4.8, Sonnet 5, Sonnet 4.6 1024 tokens
#   Opus 4.7                       2048 tokens
#   Opus 4.6, Opus 4.5, HAIKU 4.5  4096 tokens   <- what we use
#
# The minimum is not monotonic across generations: Haiku 4.5 has the highest
# of any current model. Our system prompts are roughly 640 (sorter) and 1100
# (judge) tokens, so on Haiku 4.5 caching cannot fire at all. It was added
# here as a "free win", measured at 0 cached tokens across every call, and
# removed once the actual minimum was looked up rather than assumed.
#
# If the judge ever moves to Sonnet 5 the minimum drops to 1024 and this
# becomes worth revisiting -- but only with the prompt measured against it,
# not assumed.
CACHE_MINIMUM_TOKENS = {
    "claude-opus-5": 512,
    "claude-sonnet-5": 1024,
    "claude-haiku-4-5": 4096,
}

GROQ_URL = "https://api.groq.com/openai/v1/chat/completions"

_client: AsyncAnthropic | None = None
_groq: "httpx.AsyncClient | None" = None
_spent_usd = 0.0
_calls = 0
_cache_hits = 0

T = TypeVar("T", bound=BaseModel)


def groq() -> httpx.AsyncClient:
    """One client for the process, so the second call skips the handshake."""
    global _groq
    if _groq is None:
        _groq = httpx.AsyncClient(
            base_url="https://api.groq.com",
            headers={"Authorization": f"Bearer {config.require('GROQ_API_KEY')}"},
            # Deliberately short. A rate-limit rejection comes back in about
            # 60ms, so the fallback is invisible; a HANG is the only way this
            # could cost the user anything, and this is the ceiling on that.
            timeout=config.GROQ_TIMEOUT_S,
        )
    return _groq


async def _ask_groq(model: str, system: str, user: str, schema: type[T]) -> T:
    """One structured call to an open model on Groq.

    Same prompt, same Pydantic schema as the Anthropic path. Anything that
    goes wrong -- rate limit, malformed JSON, a field the schema rejects --
    raises, and the caller falls back to Claude. There is no half-working
    state: either we get an object of the right shape or we do not.
    """
    resp = await groq().post(
        "/openai/v1/chat/completions",
        json={
            "model": model,
            "temperature": 0,
            "messages": [
                {"role": "system", "content": system},
                {"role": "user", "content": user},
            ],
            "response_format": {
                "type": "json_schema",
                "json_schema": {
                    "name": schema.__name__,
                    "schema": schema.model_json_schema(),
                    "strict": False,
                },
            },
        },
    )
    resp.raise_for_status()
    body = resp.json()
    # Validation is the point. A model that returns the wrong shape must fail
    # loudly here rather than quietly degrade the claim downstream.
    parsed = schema.model_validate_json(body["choices"][0]["message"]["content"])
    usage = body.get("usage", {})
    log.info(
        "llm %s: %d in / %d out (groq)",
        model, usage.get("prompt_tokens", 0), usage.get("completion_tokens", 0),
    )
    return parsed


def client() -> AsyncAnthropic:
    global _client
    if _client is None:
        config.require("ANTHROPIC_API_KEY")
        _client = AsyncAnthropic()
    return _client


class BudgetExceeded(RuntimeError):
    pass


def _cache_key(model: str, system: str, user: str, schema_name: str) -> str:
    blob = json.dumps([model, system, user, schema_name], sort_keys=True)
    return hashlib.sha256(blob.encode()).hexdigest()[:24]


def _price(model: str, usage: Any) -> float:
    per_in, per_out = PRICES.get(model, (0.0, 0.0))
    return (usage.input_tokens * per_in + usage.output_tokens * per_out) / 1_000_000


async def ask(
    *,
    model: str,
    system: str,
    user: str,
    schema: type[T],
    max_tokens: int = 2000,
    use_cache: bool = True,
) -> T:
    """Ask Claude for an answer shaped exactly like `schema`.

    The structured-output API enforces the shape at Anthropic's end, so there
    is no regex parsing and no "sometimes it wraps the JSON in prose".
    """
    global _spent_usd, _calls, _cache_hits

    key = _cache_key(model, system, user, schema.__name__)
    cached_at = CACHE_DIR / f"{key}.json"

    if use_cache and cached_at.exists():
        _cache_hits += 1
        log.info("llm cache hit (%s)", key)
        return schema.model_validate_json(cached_at.read_text())

    if _calls >= config.MAX_LLM_CALLS_PER_SESSION:
        raise BudgetExceeded(
            f"stopped after {_calls} Claude calls this run "
            f"(limit in config.MAX_LLM_CALLS_PER_SESSION)"
        )

    started = time.monotonic()
    response = await client().messages.parse(
        model=model,
        max_tokens=max_tokens,
        system=system,
        messages=[{"role": "user", "content": user}],
        output_format=schema,
    )
    took = time.monotonic() - started

    _calls += 1
    cost = _price(model, response.usage)
    _spent_usd += cost

    log.info(
        "llm %s: %.2fs, %d in / %d out, $%.4f (session $%.3f over %d calls)",
        model, took, response.usage.input_tokens,
        response.usage.output_tokens, cost, _spent_usd, _calls,
    )

    parsed: T = response.parsed_output
    if use_cache:
        # The directory can vanish between import and here, e.g. when a script
        # clears the cache to force fresh calls.
        CACHE_DIR.mkdir(parents=True, exist_ok=True)
        cached_at.write_text(parsed.model_dump_json())
    return parsed


async def ask_fast(
    *, system: str, user: str, schema: type[T], max_tokens: int = 2000,
    provider: str | None = None, fast_model: str | None = None,
    fallback_model: str | None = None,
) -> T:
    """Ask the fastest thing that works, and never fail because of it.

    Groq's open model runs the sorter in about 470ms against Haiku's 1700ms,
    on the identical prompt and the identical schema. But its free tier allows
    three of our calls a minute, and a conversation produces more, so it WILL
    refuse -- routinely, not exceptionally.

    A refusal returns in roughly 60ms, so falling back costs the user nothing
    they could perceive. A hang is the only real risk, and `GROQ_TIMEOUT_S`
    bounds it.

    Both caches are checked before either provider is called, so a claim
    Claude already answered is never re-offered to Groq just to be refused.
    """
    # Defaults are the sorter's, so the original call site is unchanged.
    # The judge passes its own, because the two legs are worth switching
    # independently: the sorter is a cheap easy job, the judge is neither.
    provider = provider or config.SORTER_PROVIDER
    fallback = fallback_model or config.SORTER_MODEL

    if provider != "groq":
        return await ask(model=fallback, system=system, user=user,
                         schema=schema, max_tokens=max_tokens)

    fast = fast_model or config.SORTER_GROQ_MODEL

    # Either provider's remembered answer beats calling anything.
    for model in (fast, fallback):
        hit = _cached(model, system, user, schema)
        if hit is not None:
            return hit

    try:
        parsed = await _ask_groq(fast, system, user, schema)
        _remember(fast, system, user, schema, parsed)
        return parsed
    except Exception as exc:  # noqa: BLE001
        # Rate limited, malformed, unreachable -- it does not matter which.
        # Claude answers it and the user sees a normal claim.
        log.info("groq unavailable (%s), using %s", _why(exc), fallback)

    return await ask(model=fallback, system=system, user=user,
                     schema=schema, max_tokens=max_tokens)


def _why(exc: Exception) -> str:
    """A short reason, so the logs say WHICH failure without a traceback."""
    if isinstance(exc, httpx.HTTPStatusError):
        return f"HTTP {exc.response.status_code}"
    return type(exc).__name__


def _cached(model: str, system: str, user: str, schema: type[T]) -> T | None:
    path = CACHE_DIR / f"{_cache_key(model, system, user, schema.__name__)}.json"
    if not path.exists():
        return None
    global _cache_hits
    _cache_hits += 1
    return schema.model_validate_json(path.read_text())


def _remember(model: str, system: str, user: str, schema: type[T], value: T) -> None:
    CACHE_DIR.mkdir(parents=True, exist_ok=True)
    (CACHE_DIR / f"{_cache_key(model, system, user, schema.__name__)}.json").write_text(
        value.model_dump_json()
    )


def stats() -> dict[str, Any]:
    return {
        "calls": _calls,
        "cache_hits": _cache_hits,
        "spent_usd": round(_spent_usd, 4),
    }
