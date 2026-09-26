"""The front door: serves the page and holds the WebSocket open.

Stage 2: accept a connection, echo typed sentences back as transcript events.
Stage 3: relay microphone audio to Deepgram and stream the transcript back.
"""

from __future__ import annotations

import asyncio
import json
import logging
from contextlib import suppress
from pathlib import Path

from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

from . import config, messages
from .session import Session
from .transcribe import DeepgramRelay

logging.basicConfig(
    level=config.LOG_LEVEL,
    format="%(asctime)s %(levelname)s %(name)s: %(message)s",
)
for noisy in ("httpx", "httpcore", "websockets", "anthropic", "multipart"):
    logging.getLogger(noisy).setLevel(config.LIBRARY_LOG_LEVEL)

log = logging.getLogger("cap")

WEB_DIR = Path(__file__).parent.parent / "web"

app = FastAPI(title="i'd cap that")


@app.get("/health")
async def health():
    return {"ok": True, "protocol": messages.PROTOCOL_VERSION}


@app.get("/")
async def index():
    return FileResponse(WEB_DIR / "index.html")


def _pool_for(ws: WebSocket) -> str:
    """Which budget pays for this connection.

    The machine running the demo talks to itself over loopback, so it gets the
    reserved pool. Everyone arriving through the tunnel is a visitor and is
    capped, which is what stops a room full of judges draining the credits ten
    minutes before the demo.
    """
    host = (ws.client.host if ws.client else "") or ""
    return "reserved" if host in ("127.0.0.1", "::1", "localhost") else "public"


@app.websocket("/ws")
async def websocket_endpoint(ws: WebSocket) -> None:
    """One connection = one conversation being listened to.

    Down (page to server): typed sentences, control messages, audio frames.
    Up (server to page): transcript, claim and budget events.
    """
    await ws.accept()
    session = Session(ws, pool=_pool_for(ws))
    sender = asyncio.create_task(session.sender_loop())

    log.info("session %s open (%s pool)", session.session_id, session.pool)

    session.send(
        messages.session_ready(
            session_id=session.session_id,
            protocol_version=messages.PROTOCOL_VERSION,
            budget={
                "claims_left": session.claims_left,
                "claims_cap": session.claims_cap,
                "pool": session.pool,
            },
            audio=messages.AUDIO_FORMAT,
        )
    )
    session.send(messages.server_note("connected"))

    try:
        while True:
            packet = await ws.receive()

            if packet["type"] == "websocket.disconnect":
                break
            if packet.get("text") is not None:
                await handle_text(session, packet["text"])
            elif packet.get("bytes") is not None:
                await handle_audio(session, packet["bytes"])

    except WebSocketDisconnect:
        pass
    finally:
        # Cancelling is not enough on its own: awaiting the cancelled task is
        # what stops asyncio logging "Task exception was never retrieved".
        sender.cancel()
        with suppress(asyncio.CancelledError):
            await sender
        await stop_listening(session)
        await session.shutdown()
        log.info("session %s closed", session.session_id)


# --- messages from the page -------------------------------------------------


async def handle_text(session: Session, raw: str) -> None:
    try:
        msg = json.loads(raw)
    except json.JSONDecodeError:
        return

    kind = msg.get("type")

    if kind == "inject_text":
        # Pretend the microphone heard this. The whole pipeline can then be
        # tested without talking, which is how most debugging happens, and it
        # is the backup demo when the room is too loud.
        text = (msg.get("text") or "").strip()
        if text:
            emit_final(session, text)

    elif kind == "start_listening":
        await start_listening(session)

    elif kind == "stop_listening":
        await stop_listening(session)

    elif kind == "set_keys":
        # Their own keys. Memory only, never logged, never written to disk.
        keys = msg.get("keys") or {}
        session.byok = {k: v for k, v in keys.items() if isinstance(v, str) and v}
        if session.byok:
            session.pool = "byok"
            session.send(messages.server_note("using your own keys"))
            session.send(
                messages.budget_update(
                    claims_left=session.claims_left,
                    claims_cap=session.claims_cap,
                    pool="byok",
                    note="your keys, not counted",
                )
            )


async def handle_audio(session: Session, chunk: bytes) -> None:
    # Audio arriving before start_listening has nowhere to go, so it is
    # dropped on purpose. The page always sends start_listening first.
    if session.relay is None:
        return
    try:
        await session.relay.send_audio(chunk)
    except Exception as exc:  # noqa: BLE001
        log.warning("failed to forward audio: %s", exc)
        session.send(messages.server_note(f"audio relay error: {exc}", level="error"))


# --- transcript -------------------------------------------------------------


def emit_final(session: Session, text: str) -> None:
    """One finished phrase: show it, then hand it to the chunker."""
    segment_id = session.next_segment_id()
    session.send(messages.transcript_final(segment_id, text))
    if session.chunker is not None:
        session.chunker.add_segment(segment_id, text)


# --- the microphone ---------------------------------------------------------


async def start_listening(session: Session) -> None:
    if session.relay is not None:
        return

    def on_interim(text: str) -> None:
        session.send(messages.transcript_interim(text))

    def on_final(text: str, speech_final: bool) -> None:
        emit_final(session, text)

    def on_utterance_end() -> None:
        if session.chunker is not None:
            session.chunker.utterance_end()

    relay = DeepgramRelay(on_interim, on_final, on_utterance_end)
    try:
        await relay.start()
    except Exception as exc:  # noqa: BLE001
        log.exception("could not connect to deepgram")
        session.send(
            messages.server_note(f"deepgram connection failed: {exc}", level="error")
        )
        return

    session.relay = relay
    session.send(messages.server_note("listening"))


async def stop_listening(session: Session) -> None:
    relay = session.relay
    if relay is None:
        return
    session.relay = None
    if session.chunker is not None:
        session.chunker.flush()  # do not lose a half-finished window
    await relay.close()
    session.send(messages.server_note("stopped listening"))


# Mounted LAST. A StaticFiles mount at "/" swallows every route declared
# after it, so the page would load unstyled and /health would 404.
app.mount("/", StaticFiles(directory=WEB_DIR), name="web")
