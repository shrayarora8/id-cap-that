"""The rate limiter, on a fake clock. No sleeping, nothing spent."""

from __future__ import annotations

import asyncio

import pytest

from server.ratelimit import RateLimiter


def test_it_allows_the_first_n_immediately(monkeypatch):
    limiter = RateLimiter(per_minute=3)
    assert limiter.available == 3
    for _ in range(3):
        limiter._taken.append(0.0)
    monkeypatch.setattr("time.monotonic", lambda: 1.0)
    assert limiter.available == 0


def test_slots_come_back_after_a_minute(monkeypatch):
    limiter = RateLimiter(per_minute=2)
    now = [100.0]
    monkeypatch.setattr("server.ratelimit.time.monotonic", lambda: now[0])

    limiter._taken.extend([100.0, 100.5])
    assert limiter.available == 0

    now[0] = 161.0  # both are now older than 60s
    assert limiter.available == 2


def test_wait_time_is_until_the_oldest_slot_expires(monkeypatch):
    limiter = RateLimiter(per_minute=1)
    now = [100.0]
    monkeypatch.setattr("server.ratelimit.time.monotonic", lambda: now[0])

    limiter._taken.append(100.0)
    now[0] = 110.0
    assert limiter.wait_time() == pytest.approx(50.0)


def test_wait_time_is_zero_when_a_slot_is_free():
    assert RateLimiter(per_minute=5).wait_time() == 0.0


async def test_acquire_returns_immediately_when_under_the_limit():
    limiter = RateLimiter(per_minute=5)
    waited = await limiter.acquire()
    assert waited == 0.0
    assert limiter.available == 4


async def test_concurrent_callers_do_not_all_blow_the_limit_together():
    """The bug the lock prevents: without it every waiting coroutine measures
    the same delay, sleeps the same amount, wakes together, and exceeds the
    limit in one burst."""
    limiter = RateLimiter(per_minute=3)
    await asyncio.gather(*(limiter.acquire() for _ in range(3)))
    assert limiter.available == 0
    assert len(limiter._taken) == 3
