"""A token bucket, so we never discover a rate limit in front of an audience.

Firecrawl allows ten requests a minute. One claim on the escalation path costs
four, so three claims in quick succession exhausts a minute in about twenty
seconds. The previous build handled this by retrying after a 429, which works
but means the claim takes fourteen seconds instead of four.

Waiting for a slot *before* asking is strictly better: the same total
throughput, no wasted round trips, and the delay lands in a place the UI can
narrate ("waiting for a search slot") rather than as an unexplained stall.
"""

from __future__ import annotations

import asyncio
import time
from collections import deque


class RateLimiter:
    """Allow `per_minute` acquisitions in any rolling 60 seconds."""

    def __init__(self, per_minute: int) -> None:
        self.per_minute = per_minute
        self._taken: deque[float] = deque()
        self._lock = asyncio.Lock()

    def _drop_expired(self, now: float) -> None:
        while self._taken and now - self._taken[0] >= 60.0:
            self._taken.popleft()

    @property
    def available(self) -> int:
        self._drop_expired(time.monotonic())
        return max(0, self.per_minute - len(self._taken))

    def wait_time(self) -> float:
        """Seconds until a slot frees up. 0 when one is free now."""
        now = time.monotonic()
        self._drop_expired(now)
        if len(self._taken) < self.per_minute:
            return 0.0
        return max(0.0, 60.0 - (now - self._taken[0]))

    async def acquire(self) -> float:
        """Wait for a slot. Returns how long it waited, so the caller can say so.

        The lock is held across the sleep on purpose: without it, ten
        coroutines all measure the same wait, all sleep the same amount, and
        all wake together to blow the limit at once.
        """
        async with self._lock:
            waited = 0.0
            while True:
                delay = self.wait_time()
                if delay <= 0:
                    break
                await asyncio.sleep(delay)
                waited += delay
            self._taken.append(time.monotonic())
            return waited
