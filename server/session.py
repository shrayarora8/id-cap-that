"""One Session per open WebSocket.

The rule that matters: **only one piece of code ever writes to the socket.**
Everything else drops a message into `out` and a single sender task takes them
out and sends them. Without that, two claims finishing in the same millisecond
interleave their writes and the connection breaks in a way that is very
annoying to debug at 2am.
"""

from __future__ import annotations

import asyncio
import itertools
import json
import logging
import time
import uuid
from typing import TYPE_CHECKING, Any, Optional

from fastapi import WebSocket

from . import config

if TYPE_CHECKING:  # imported for type checkers only, never at runtime
    from .chunker import Chunker
    from .transcribe import DeepgramRelay

log = logging.getLogger(__name__)


class Session:
    def __init__(self, ws: WebSocket, pool: str = "public") -> None:
        self.ws = ws
        self.session_id = f"sess_{uuid.uuid4().hex[:8]}"
        self.pool = pool

        # Set by main.py once the connection is up. Declared here so all the
        # per-connection state is visible in one place.
        self.chunker: Optional["Chunker"] = None
        self.relay: Optional["DeepgramRelay"] = None

        self.out: asyncio.Queue[dict[str, Any]] = asyncio.Queue()
        self.tasks: set[asyncio.Task] = set()

        self._seq = itertools.count(1)
        self._segment_ids = itertools.count(1)
        self._claim_ids = itertools.count(1)

        # Keys a visitor supplied themselves. In memory only, never logged,
        # never written to disk, gone when the socket closes.
        self.byok: dict[str, str] = {}

        # What each claim on screen was built from, so a correction can be
        # re-run against the same words. Holds the original spans, the heard
        # text, and the window -- the transcript characters never change when
        # a claim is edited, so the spans stay valid and the highlight stays
        # where it was.
        self.claims: dict[str, dict[str, Any]] = {}

        cap = (
            config.CLAIMS_PER_RESERVED_SESSION
            if pool == "reserved"
            else config.CLAIMS_PER_PUBLIC_SESSION
        )
        self.claims_cap = cap
        self.claims_used = 0

        self._recording = None
        if config.RECORD_SESSIONS:
            config.RECORDINGS_DIR.mkdir(parents=True, exist_ok=True)
            path = config.RECORDINGS_DIR / f"{int(time.time())}_{self.session_id}.jsonl"
            self._recording = path.open("a")
            self._started_at = time.monotonic()

    # --- ids ----------------------------------------------------------------

    def next_segment_id(self) -> str:
        return f"s{next(self._segment_ids)}"

    def next_claim_id(self) -> str:
        # Scoped to THIS session's own counter, so a reconnect -- a network
        # blip, a laptop waking up, a backgrounded tab -- starts a fresh
        # Session with its own counter restarting at c1. A claim from the
        # old session and a claim from the new one then share an id.
        #
        # The page already lived through this exact bug once, for transcript
        # segments, and fixed it there: every segment is keyed by its own
        # epoch plus its id, specifically so a reused id after a reconnect
        # can never collide. Claims never got the same treatment, and the
        # result was measured directly: a verdict about the Nobel Prizes,
        # correctly judged with the right evidence, rendered on top of an
        # unrelated Tesla claim because both happened to be "c1" from two
        # different sessions -- the right answer, glued to the wrong words.
        #
        # Folding the session's own id into the claim id makes collision
        # impossible regardless of what happens on the reconnect, rather
        # than relying on the page to notice and defend against it.
        return f"c{next(self._claim_ids)}_{self.session_id[5:13]}"

    # --- budget -------------------------------------------------------------

    @property
    def claims_left(self) -> int:
        if self.pool == "byok":
            return 9999
        return max(0, self.claims_cap - self.claims_used)

    def spend_claim(self) -> bool:
        """Take one from the budget. False means there is nothing left."""
        if self.pool == "byok":
            return True
        if self.claims_left <= 0:
            return False
        self.claims_used += 1
        return True

    # --- sending ------------------------------------------------------------

    def send(self, message: dict[str, Any]) -> None:
        """Queue a message for the page. Never awaits, so it is safe to call
        from anywhere, including deep inside a claim-checking job."""
        message["seq"] = next(self._seq)
        if self._recording is not None:
            # Offset from the start, so a replay can reproduce the real
            # rhythm rather than dumping everything at once.
            record = dict(message)
            record["_t"] = round(time.monotonic() - self._started_at, 3)
            self._recording.write(json.dumps(record) + "\n")
            self._recording.flush()
        self.out.put_nowait(message)

    async def sender_loop(self) -> None:
        """The only writer to the socket."""
        while True:
            message = await self.out.get()
            await self.ws.send_json(message)

    # --- background jobs ----------------------------------------------------

    def spawn(self, coro) -> asyncio.Task:
        """Run something in the background, keeping a reference so it is not
        garbage collected mid-flight and can be cancelled on hangup."""
        task = asyncio.create_task(coro)
        self.tasks.add(task)
        task.add_done_callback(self.tasks.discard)
        return task

    async def shutdown(self) -> None:
        for task in list(self.tasks):
            task.cancel()
        if self.tasks:
            await asyncio.gather(*self.tasks, return_exceptions=True)
        if self._recording is not None:
            self._recording.close()
            self._recording = None
