"""The Deepgram relay: audio goes out, text comes back.

Two pipes are in play:

    browser  --audio-->  our server  --audio-->  Deepgram
    browser  <--text---  our server  <--text---  Deepgram

Deepgram sends two kinds of transcript:

    interim (is_final = false)   draft words that will still change
    final   (is_final = true)    locked in for a span of audio

and two "the speaker stopped" signals: `speech_final` right after a final
result, and `UtteranceEnd` after a longer silence even if audio kept flowing.

Only finals are ever processed. Chunking or highlighting on a draft means
anchoring to characters that are about to stop existing.

What we send is **raw 16 kHz mono linear16 PCM**, not WebM or Opus. iOS Safari
does not produce Opus, and the phone is a first-class target here, so a
container we cannot rely on would be a silent failure on the device we most
care about. Raw PCM also skips the container entirely, which is fewer bytes
and less latency.
"""

from __future__ import annotations

import asyncio
import json
import logging
from contextlib import suppress
from typing import Callable
from urllib.parse import urlencode

import websockets
from websockets.asyncio.client import ClientConnection

from . import config

log = logging.getLogger(__name__)

DEEPGRAM_URL = "wss://api.deepgram.com/v1/listen"

# Deepgram closes a socket that goes quiet. A KeepAlive resets its timer
# without pretending there was sound.
KEEPALIVE_EVERY_S = 6.0


def _build_url() -> str:
    params = {
        "model": config.DEEPGRAM_MODEL,
        "language": config.DEEPGRAM_LANGUAGE,
        # The audio contract. Without these three Deepgram tries to sniff a
        # container, finds none, and returns nothing at all -- silently.
        "encoding": "linear16",
        "sample_rate": str(config.AUDIO_SAMPLE_RATE),
        "channels": str(config.AUDIO_CHANNELS),
        "interim_results": "true",
        "smart_format": "true",          # punctuation and capitalisation
        "endpointing": str(config.DEEPGRAM_ENDPOINTING_MS),
        "utterance_end_ms": str(config.DEEPGRAM_UTTERANCE_END_MS),
        "vad_events": "true",
        # One keyterm per repeated parameter, hence doseq.
        "keyterm": config.DEEPGRAM_KEYTERMS,
    }
    return f"{DEEPGRAM_URL}?{urlencode(params, doseq=True)}"


class DeepgramRelay:
    """One relay per session.

    The callbacks are how it talks back to the rest of the server. It knows
    nothing about sessions, claims, or the socket to the browser.
    """

    def __init__(
        self,
        on_interim: Callable[[str], None],
        on_final: Callable[[str, bool], None],
        on_utterance_end: Callable[[], None] | None = None,
        on_dead: Callable[[str], None] | None = None,
    ) -> None:
        self.on_interim = on_interim
        self.on_final = on_final
        self.on_utterance_end = on_utterance_end
        # Called when the read loop ends unexpectedly. Without this the
        # previous build kept forwarding audio into a closed socket and the
        # transcript simply stopped, with nothing on screen explaining why.
        self.on_dead = on_dead

        self.ws: ClientConnection | None = None
        self.alive = False
        self._reader: asyncio.Task | None = None
        self._keepalive: asyncio.Task | None = None
        self.bytes_in = 0

    # --- lifecycle ----------------------------------------------------------

    async def start(self) -> None:
        key = config.require("DEEPGRAM_API_KEY")
        self.ws = await websockets.asyncio.client.connect(
            _build_url(),
            additional_headers={"Authorization": f"Token {key}"},
            max_size=None,
        )
        self.alive = True
        self._reader = asyncio.create_task(self._read_loop())
        self._keepalive = asyncio.create_task(self._keepalive_loop())
        log.info("deepgram: connected (%d Hz linear16)", config.AUDIO_SAMPLE_RATE)

    async def send_audio(self, chunk: bytes) -> None:
        if self.ws is None or not self.alive:
            return
        self.bytes_in += len(chunk)
        await self.ws.send(chunk)

    async def close(self) -> None:
        """Shut the relay down without losing the last words.

        Order matters. CloseStream asks Deepgram to flush whatever it is still
        holding, so the reader has to be alive to receive it -- cancelling
        first, as the previous build did, threw away the tail of every final
        sentence.

        Note the two different suppressions. Around a *socket* operation we
        suppress Exception only, so a real cancellation of this coroutine
        still propagates. Around `await task` for a task **we just cancelled
        ourselves** we must also suppress CancelledError, because awaiting a
        cancelled task re-raises it by design -- that is not an error here,
        it is the acknowledgement we asked for.
        """
        self.alive = False

        if self.ws is not None:
            with suppress(Exception):
                await self.ws.send(json.dumps({"type": "CloseStream"}))
            # Give Deepgram a moment to flush before tearing anything down.
            if self._reader is not None:
                with suppress(Exception, asyncio.CancelledError):
                    await asyncio.wait_for(asyncio.shield(self._reader), timeout=1.5)

        for task in (self._reader, self._keepalive):
            if task is not None:
                task.cancel()
                with suppress(Exception, asyncio.CancelledError):
                    await task

        if self.ws is not None:
            with suppress(Exception):
                await self.ws.close()
            self.ws = None

        log.info("deepgram: closed after %d bytes", self.bytes_in)

    # --- internals ----------------------------------------------------------

    async def _keepalive_loop(self) -> None:
        while True:
            await asyncio.sleep(KEEPALIVE_EVERY_S)
            if self.ws is not None and self.alive:
                try:
                    await self.ws.send(json.dumps({"type": "KeepAlive"}))
                except Exception:  # noqa: BLE001
                    return

    async def _read_loop(self) -> None:
        assert self.ws is not None
        reason = "stream closed"
        try:
            async for raw in self.ws:
                if isinstance(raw, bytes):
                    continue
                msg = json.loads(raw)
                kind = msg.get("type")

                if kind == "Results":
                    self._handle_results(msg)
                elif kind == "UtteranceEnd":
                    if self.on_utterance_end:
                        self.on_utterance_end()
                elif kind == "Metadata":
                    log.info("deepgram metadata: %s", msg.get("request_id"))
        except asyncio.CancelledError:
            raise
        except Exception as exc:  # noqa: BLE001
            reason = str(exc)
            log.warning("deepgram read loop ended: %s", exc)

        # If we get here the socket is done. Say so, rather than letting the
        # transcript quietly stop with no explanation anywhere.
        if self.alive:
            self.alive = False
            if self.on_dead:
                self.on_dead(reason)

    def _handle_results(self, msg: dict) -> None:
        alternatives = msg.get("channel", {}).get("alternatives", [])
        if not alternatives:
            return
        text = (alternatives[0].get("transcript") or "").strip()
        if not text:
            return

        if msg.get("is_final"):
            self.on_final(text, bool(msg.get("speech_final")))
        else:
            self.on_interim(text)
