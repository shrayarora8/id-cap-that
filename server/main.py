"""The front door: serves the page and holds the WebSocket open.

Stage 2: accept a connection, echo typed sentences back as transcript events.
Stage 3: relay microphone audio to Deepgram and stream the transcript back.
"""

from __future__ import annotations

import asyncio
import json
import logging
import re
import time
from contextlib import suppress
from pathlib import Path

from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

from . import config, messages
from .chunker import Chunker, Window
from .judge import judge_claim
from .llm import BudgetExceeded
from .prefilter import worth_checking
from .retrieval import (
    credits_used, deepen, recall, remember, remembered_count, search,
    snippets_as_evidence,
)
from .session import Session
from .sources import Passage
from .sorter import find_claims
from .spans import locate
from .transcribe import DeepgramRelay

logging.basicConfig(
    level=config.LOG_LEVEL,
    format="%(asctime)s %(levelname)s %(name)s: %(message)s",
)
for noisy in ("httpx", "httpcore", "websockets", "anthropic", "multipart"):
    logging.getLogger(noisy).setLevel(config.LIBRARY_LOG_LEVEL)

log = logging.getLogger("cap")

class FreshStaticFiles(StaticFiles):
    """Static files that a browser must revalidate before reusing.

    StaticFiles sends no Cache-Control at all, so browsers fall back to
    heuristic freshness and happily reuse yesterday's app.js. ES modules are
    cached especially hard, and a query string on the HTML does not bust them
    because the module URLs never change.

    The cost of that was not theoretical. Frontend fixes landed in git and
    never reached the phone, so the same complaints came back for hours and
    both of us kept re-checking code that was already correct. The bug was in
    delivery, not in either of the things we were looking at.

    `no-cache` means revalidate, not "never cache": a 304 still costs almost
    nothing, and correctness here is worth far more than a saved round trip on
    a handful of small files.
    """

    def is_not_modified(self, response_headers, request_headers) -> bool:
        return super().is_not_modified(response_headers, request_headers)

    async def get_response(self, path: str, scope):
        response = await super().get_response(path, scope)
        response.headers["Cache-Control"] = "no-cache"
        return response


# A normalised claim that still begins with a pronoun was never given a
# subject, so there is nothing specific to search for.
#
# A described subject is a pronoun wearing a disguise. "The company raised at
# a ten billion dollar valuation" passes any pronoun test and is exactly as
# unsearchable -- it came back COULD BE CAP every time, which reads to a user
# as the tool failing rather than as the tool never having been told who the
# claim was about.
UNRESOLVED_SUBJECT = re.compile(
    r"^(he|she|it|they|we|you|his|her|their|its|this|that|these|those)\b"
    r"|^the (company|speaker|team|organisation|organization|product|platform|"
    r"business|firm|startup|author|person|user|customer)'?s?\b",
    re.IGNORECASE,
)

# How often the chunker checks its two time-based rules. Nothing else would
# ever fire them, because they are about time passing rather than about
# something arriving.
TICK_SECONDS = 0.2

WEB_DIR = Path(__file__).parent.parent / "web"

app = FastAPI(title="i'd cap that")


@app.get("/health")
async def health():
    return {"ok": True, "protocol": messages.PROTOCOL_VERSION}


@app.get("/")
async def index():
    # no-cache here too: a stale index.html keeps pointing at the same module
    # URLs, so the modules stay stale however fresh they are on disk.
    return FileResponse(
        WEB_DIR / "index.html", headers={"Cache-Control": "no-cache"}
    )


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

    # Every session gets a chunker. It groups finished phrases into windows
    # and hands each closed window to on_window_closed below.
    session.chunker = Chunker(on_window=lambda w: on_window_closed(session, w))
    ticker = asyncio.create_task(tick_loop(session))

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
        for task in (sender, ticker):
            task.cancel()
            # Cancelling is not enough on its own: awaiting the cancelled task
            # is what stops asyncio logging "Task exception was never
            # retrieved" on every disconnect.
            with suppress(asyncio.CancelledError):
                await task
        await stop_listening(session)
        await session.shutdown()
        log.info("session %s closed", session.session_id)


async def tick_loop(session: Session) -> None:
    """Nudges the chunker so its silence and duration rules can fire."""
    while True:
        await asyncio.sleep(TICK_SECONDS)
        if session.chunker is not None:
            session.chunker.tick()


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


def on_window_closed(session: Session, window: Window) -> None:
    """A window of speech is complete: show it, then decide what it costs."""
    log.info("window %s closed by %s: %r", window.window_id, window.reason, window.text)
    session.send(
        messages.window_ready(
            window.window_id, window.segment_ids, window.text, window.reason
        )
    )

    # The free check first. Most of a conversation is not claims, and
    # establishing that costs nothing here.
    allowed, reason = worth_checking(window.text, window.continues_previous)
    if not allowed:
        log.info("window %s skipped: %s", window.window_id, reason)
        session.send(messages.window_skipped(window.window_id, reason))
        return

    # Its own background job, so several windows can be in flight while the
    # conversation carries on. Awaiting here would freeze the transcript for
    # a second and a half every time anyone said anything checkable.
    session.spawn(check_window(session, window))


async def check_window(session: Session, window: Window) -> None:
    """Ask Claude what was claimed, then start a job per claim.

    The search is fired speculatively at the same time, on the raw window
    text, rather than waiting for the sorter to write a better query. Both
    calls take roughly two seconds, so running them in sequence spends four
    seconds to do two seconds of work.

    The sorter's query is usually better than the raw text, so when it comes
    back materially different we search again -- but by then the speculative
    results are already in the on-disk cache and, more often than not, the
    sorter's query overlaps enough that the second search is a cache hit or a
    cheap addition. When the window turns out to contain no checkable claim
    the speculative search is wasted: one credit, against nearly two seconds
    off every verdict that does happen.
    """
    try:
        claims = await find_claims(window.text, window.context)
    except BudgetExceeded as exc:
        log.warning("budget: %s", exc)
        session.send(messages.server_note(str(exc), level="warn"))
        return
    except Exception as exc:  # noqa: BLE001
        log.exception("sorter failed")
        session.send(messages.server_note(f"sorter failed: {exc}", level="error"))
        return

    for claim in claims:
        # A claim whose subject is still a pronoun was never decontextualised,
        # and it cannot be searched for: "She dated Tom Holland" matches an
        # article about anyone who dated Tom Holland. That is how a Zendaya
        # page came back NO CAP for a claim about Taylor Swift.
        unresolved = claim.checkable and UNRESOLVED_SUBJECT.match(
            claim.normalized.strip()
        )

        # An opinion or an aside in ordinary conversation is not worth
        # marking. Buzzwords and unfalsifiable superlatives are, because
        # "the best database in the world" sounds like a fact and is not one.
        if not claim.checkable and claim.kind not in ("fluff", "vague"):
            log.info("not surfacing %s claim: %r", claim.kind, claim.quote[:50])
            continue

        claim_id = session.next_claim_id()

        spans = locate(window.segments, claim.quote)
        if not spans:
            # Claude paraphrased instead of copying. Highlight the whole
            # window rather than the wrong words.
            log.info("claim %s: quote not found, highlighting the window", claim_id)
            spans = [
                {"segment_id": seg.segment_id, "start": 0, "end": len(seg.text)}
                for seg in window.segments
            ]

        session.send(
            messages.claim_detected(
                claim_id=claim_id,
                window_id=window.window_id,
                spans=spans,
                quote=claim.quote,
                normalized=claim.normalized,
                kind=claim.kind,
                hedge=claim.hedge,
                shape=claim.shape,
                checkable=claim.checkable,
                search_query=claim.search_query,
                note=claim.note,
            )
        )

        if unresolved:
            # Searching for "they raised at a ten billion valuation" matches
            # any company that ever did, so we will not spend a search on it.
            # But dropping it silently is worse: the words sit there with no
            # mark and no explanation, and it reads as the tool missing
            # things at random. Say what happened instead.
            log.info("no named subject: %r", claim.normalized[:60])
            session.send(
                messages.claim_verdict(
                    claim_id=claim_id,
                    verdict="INSUFFICIENT_EVIDENCE",
                    sticker=messages.STICKERS["INSUFFICIENT_EVIDENCE"],
                    summary="couldn't tell who or what this is about, so there was nothing to look up",
                    depth="snippets",
                )
            )
            continue

        if not claim.checkable:
            # WORD SALAD is for corporate buzzwords -- that is the joke, and
            # it only works when it is rare. Stamping it on every opinion and
            # aside ("taking too long", "this is not working") makes the
            # system look like it is labelling speech at random, which is
            # exactly how it looked in the first long conversation.
            session.send(
                messages.claim_verdict(
                    claim_id=claim_id,
                    verdict="NOT_FACT_CHECKABLE",
                    sticker=messages.STICKERS["NOT_FACT_CHECKABLE"],
                    summary=claim.note or "nothing here that evidence could settle",
                    depth="snippets",
                )
            )
            continue

        if not session.spend_claim():
            session.send(messages.claim_error(claim_id, "budget", "demo budget used up"))
            session.send(
                messages.budget_update(
                    claims_left=0, claims_cap=session.claims_cap, pool=session.pool,
                    exhausted=True, note="add your own keys to keep going",
                )
            )
            continue

        session.send(
            messages.budget_update(
                claims_left=session.claims_left,
                claims_cap=session.claims_cap,
                pool=session.pool,
            )
        )
        # Its own job, so several claims resolve at once while the
        # conversation carries on.
        session.spawn(check_claim(session, claim_id, claim))


async def check_claim(session: Session, claim_id: str, claim) -> None:
    """Find evidence for one claim and judge it against that evidence.

    Two depths. Search snippets first: free, already relevant, one round trip,
    and enough for most claims -- that is what makes a verdict land in about
    four seconds. If the judge says its evidence was too thin, and only then,
    fetch the pages and judge again.

    The escalation decision is the judge's, returned in a field of a response
    we were already paying for. That is the agentic part: the system decides
    for itself whether it has enough, but the control flow stays ours, so the
    latency and the spend are both bounded.
    """
    started = time.monotonic()
    timings: dict[str, int] = {}

    def mark(name: str, since: float) -> float:
        timings[name] = int((time.monotonic() - since) * 1000)
        return time.monotonic()

    def status(stage: str, detail: str = "") -> None:
        session.send(messages.claim_status(claim_id, stage, detail))

    try:
        leg = time.monotonic()
        status("searching", f"searching {claim.official_domain or 'the web'}")

        # Ask what we have already read before paying to read more. A Moss
        # query is in-process and takes milliseconds; a Firecrawl search takes
        # well over a second and a credit. A hit saves both; a miss costs a
        # few hundred milliseconds, and is hard-timed so it can never become
        # the slow part.
        hits = []
        evidence = await recall(claim.normalized)
        from_memory = bool(evidence)

        if evidence:
            status("searching", "recognised this from what it has already read")
            leg = mark("recall", leg)
        else:
            hits = await search(
                claim.search_query or claim.normalized,
                claim.normalized,
                claim.official_domain,
                lambda msg: status("searching", msg),
            )
            leg = mark("search", leg)
            evidence = snippets_as_evidence(hits)

            # Keep what we just read, so the next related claim can skip all
            # of this. Spawned rather than awaited: it must not delay a
            # verdict that is already decided.
            session.spawn(remember([
                Passage(text=e.text, url=e.url, title=e.title, tier=e.tier)
                for e in evidence
            ]))
        # Sent the moment we have it, thin or not: sources appearing before
        # the verdict is what makes the wait feel like work happening.
        send_evidence(session, claim_id, evidence, "snippets")

        status("judging", f"weighing {len(evidence)} snippet(s)")
        judgement, checks = await judge_claim(claim.normalized, evidence, claim.shape)
        leg = mark("judge", leg)

        # Memory is allowed to be fast, never allowed to be worse.
        #
        # Recall reuses passages that name the claim's subject -- but the same
        # subject is not the same question. Passages about where the Amazon is
        # cannot say how long it is, so a remembered answer can come back
        # "insufficient" where a real search would have settled it. That is a
        # regression, and the whole condition this feature was built under is
        # that it must not make anything worse.
        #
        # So an unsatisfying remembered answer is not the final word: fall
        # through to the search we skipped and judge again. The only cost is
        # on the path that was going to disappoint anyway.
        if from_memory and judgement.verdict == "INSUFFICIENT_EVIDENCE":
            log.info("claim %s: memory could not settle it, searching after all", claim_id)
            status("searching", "not enough in memory, looking it up")
            hits = await search(
                claim.search_query or claim.normalized,
                claim.normalized,
                claim.official_domain,
                lambda msg: status("searching", msg),
            )
            leg = mark("search", leg)
            evidence = snippets_as_evidence(hits)
            if evidence:
                send_evidence(session, claim_id, evidence, "snippets")
                status("judging", f"weighing {len(evidence)} snippet(s)")
                judgement, checks = await judge_claim(
                    claim.normalized, evidence, claim.shape
                )
                leg = mark("rejudge", leg)
                session.spawn(remember([
                    Passage(text=e.text, url=e.url, title=e.title, tier=e.tier)
                    for e in evidence
                ]))

        deep_enough = not judgement.needs_full_pages or not hits
        send_verdict(
            session, claim_id, judgement, checks=checks,
            stage="confirmed" if deep_enough else "provisional",
            depth="snippets", started=started, timings=timings,
        )

        if deep_enough:
            log_result(claim_id, judgement, checks, timings)
            return

        # The judge asked to read further. This is the only path that costs
        # more than one Firecrawl credit.
        status("escalating", "snippets were thin, reading the pages")
        if claim.official_domain:
            # Ask the site directly, now that it is worth the extra request.
            hits = await search(
                claim.search_query or claim.normalized,
                claim.normalized,
                claim.official_domain,
                lambda msg: status("reading", msg),
                deep=True,
            ) or hits
        evidence = await deepen(
            claim.normalized, hits, lambda msg: status("reading", msg)
        )
        leg = mark("escalate", leg)

        if not evidence:
            # The pages would not load. The snippet verdict is the best we
            # have, so promote it to confirmed rather than leaving it
            # provisional forever: a claim that never reaches a settled state
            # is a claim whose elapsed counter ticks upward with no end, and
            # that counter is the honesty of the whole product.
            checks.append(messages.check("verdict_unsupported", "the pages would not load, so the snippet verdict stands"))
            send_verdict(
                session, claim_id, judgement, checks=checks, stage="confirmed", depth="snippets",
                started=started, timings=timings,
            )
            log_result(claim_id, judgement, checks, timings)
            return

        send_evidence(session, claim_id, evidence, "pages")
        session.spawn(remember([
            Passage(text=e.text, url=e.url, title=e.title, tier=e.tier)
            for e in evidence
        ]))
        status("judging", f"weighing {len(evidence)} passage(s)")
        judgement, checks = await judge_claim(claim.normalized, evidence, claim.shape)
        mark("rejudge", leg)

        send_verdict(
            session, claim_id, judgement, checks=checks, stage="confirmed", depth="pages",
            started=started, timings=timings,
        )
        log_result(claim_id, judgement, checks, timings)

    except BudgetExceeded as exc:
        session.send(messages.claim_error(claim_id, "budget", str(exc)))
    except Exception as exc:  # noqa: BLE001
        log.exception("checking claim %s failed", claim_id)
        session.send(messages.claim_error(claim_id, "check", str(exc)))


def send_evidence(session: Session, claim_id: str, evidence, depth: str) -> None:
    session.send(
        messages.claim_evidence(
            claim_id,
            [
                messages.evidence_item(e.evidence_id, e.url, e.title, e.tier, e.text)
                for e in evidence
            ],
            depth=depth,
        )
    )


def send_verdict(
    session: Session, claim_id: str, judgement, stage: str, depth: str,
    started: float, timings: dict, checks: list | None = None,
) -> None:
    session.send(
        messages.claim_verdict(
            claim_id=claim_id,
            verdict=judgement.verdict,
            sticker=messages.STICKERS.get(judgement.verdict, judgement.verdict),
            summary=judgement.summary,
            stage=stage,
            citations=[messages.citation(c.evidence_id, c.quote) for c in judgement.citations],
            checks=checks or [],
            depth=depth,
            took_ms=int((time.monotonic() - started) * 1000),
            timings=timings,
            correction=judgement.correction,
            confidence=judgement.confidence,
        )
    )


def log_result(claim_id: str, judgement, checks: list[dict], timings: dict) -> None:
    log.info(
        "claim %s -> %s | %s | %s | %d firecrawl credits so far",
        claim_id, judgement.verdict,
        " ".join(f"{k}={v}ms" for k, v in timings.items()),
        "; ".join(c["code"] for c in checks) or "clean",
        credits_used(),
    )
    log.debug("moss holds %d passage(s)", remembered_count()
    )


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
app.mount("/", FreshStaticFiles(directory=WEB_DIR), name="web")
