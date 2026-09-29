"""The contract. Every message that crosses the WebSocket is defined here.

The page is a dumb renderer. It holds a little state, applies each message to
that state, and redraws. Nothing is computed in the browser. That is what lets
you watch the entire system behave as a stream of text, with no browser open,
and it is what lets the two halves be built independently.

Everything is named by an id, and ids are stable forever:

    s7   a phrase      (one final result from Deepgram)
    w3   a window      (a group of phrases big enough to be a thought)
    c2   a claim       (something checkable, found inside a window)
    E1   a passage     (one piece of evidence the judge is allowed to read)

Stability is the whole point. A verdict that arrives eight seconds late still
finds the exact characters it belongs to, in a transcript that has scrolled on
without it.
"""

from __future__ import annotations

import time
from typing import Any, Literal

# Bumped whenever a message shape changes incompatibly. The page checks it on
# connect and tells you to hard-refresh instead of failing in a confusing way
# three messages later.
PROTOCOL_VERSION = 1


def _now_ms() -> int:
    return int(time.time() * 1000)


def event(message_type: str, /, **fields: Any) -> dict[str, Any]:
    """Build one outgoing message. `seq` is stamped by the session on send.

    The first parameter is `message_type` and not `kind` or `type` because
    both of those are field names we actually send (a claim has a `kind`), and
    **fields would collide with the parameter name. That collision raises
    TypeError inside a background task where nobody retrieves the exception,
    so claims silently stop appearing and there is no traceback anywhere.
    It cost an afternoon once. Do not "tidy" this name.

    The `/` makes it positional-only, which closes the hole completely: even a
    message that genuinely carries a field called `message_type` now lands in
    **fields instead of colliding with the parameter.
    """
    return {"type": message_type, "ts": _now_ms(), **fields}


# --- session ----------------------------------------------------------------


def session_ready(
    session_id: str,
    protocol_version: int,
    budget: dict[str, Any],
    audio: dict[str, Any],
) -> dict[str, Any]:
    """First message on every connection. Tells the page who it is, what the
    audio format must be, and how much demo budget it has to spend."""
    return event(
        "session.ready",
        session_id=session_id,
        protocol_version=protocol_version,
        budget=budget,
        audio=audio,
    )


def budget_update(
    claims_left: int,
    claims_cap: int,
    pool: str,
    exhausted: bool = False,
    note: str = "",
) -> dict[str, Any]:
    """The live 'demo credits: 9 left' counter.

    `pool` is 'reserved' (the demo device), 'public' (a visitor) or 'byok'
    (their own keys, unlimited and not counted).
    """
    return event(
        "budget.update",
        claims_left=claims_left,
        claims_cap=claims_cap,
        pool=pool,
        exhausted=exhausted,
        note=note,
    )


# --- transcript -------------------------------------------------------------


def transcript_interim(text: str) -> dict[str, Any]:
    """Draft words. Deepgram will revise them. Display only, never processed:
    chunking or highlighting on text that is about to change means anchoring
    to characters that will not exist in a second."""
    return event("transcript.interim", text=text)


def transcript_final(segment_id: str, text: str) -> dict[str, Any]:
    """Locked-in words. Every offset in the system is relative to one of these."""
    return event("transcript.final", segment_id=segment_id, text=text)


def window_ready(
    window_id: str, segment_ids: list[str], text: str, reason: str
) -> dict[str, Any]:
    """A group of phrases, closed by one of the chunker's rules. `reason` says
    which rule, which is how you tune the chunker without guessing."""
    return event(
        "window.ready",
        window_id=window_id,
        segment_ids=segment_ids,
        text=text,
        reason=reason,
    )


def window_skipped(window_id: str, reason: str) -> dict[str, Any]:
    """The free pre-filter decided this could not contain a claim. Shown to
    the user, because explaining the silence is better than silence."""
    return event("window.skipped", window_id=window_id, reason=reason)


# --- claims -----------------------------------------------------------------


def claim_detected(
    claim_id: str,
    window_id: str,
    spans: list[dict[str, Any]],
    quote: str,
    normalized: str,
    kind: str,
    hedge: str,
    shape: str,
    checkable: bool,
    search_query: str = "",
    note: str = "",
    edited: bool = False,
    heard: str = "",
) -> dict[str, Any]:
    """A claim was found. `spans` say which characters of which phrases to
    underline: [{segment_id, start, end}, ...]. A claim can straddle two
    phrases, so it contributes a span to each one it touches.

    Re-emitted with the SAME claim_id when the user corrects a claim, so the
    page never has to guess what is being checked. Without that, the page
    would keep showing the text it patched in optimistically while the server
    checked whatever its sorter made of the correction -- and the two would
    diverge silently.

    `edited` marks a corrected claim. `heard` carries the original
    transcription, which is kept rather than discarded: a tool that checks
    what people say should not quietly rewrite the record of what they said.
    Showing the mis-hearing is also the only thing that explains WHY a check
    went wrong -- it is the difference between "this is broken" and "it
    mis-heard the name".
    """
    return event(
        "claim.detected",
        claim_id=claim_id,
        window_id=window_id,
        spans=spans,
        quote=quote,
        normalized=normalized,
        kind=kind,
        hedge=hedge,
        shape=shape,
        checkable=checkable,
        search_query=search_query,
        note=note,
        edited=edited,
        heard=heard,
    )


# The stages a claim passes through, in order. The page renders these as a
# progress ladder rather than a line of changing text, so something is always
# visibly moving even when a single stage takes three seconds.
Stage = Literal[
    "queued",
    "extracting",
    "searching",
    "reading",
    "sifting",
    "judging",
    "escalating",
    "done",
]

STAGE_ORDER: tuple[str, ...] = (
    "queued",
    "extracting",
    "searching",
    "reading",
    "sifting",
    "judging",
    "escalating",
    "done",
)


def claim_status(claim_id: str, stage: str, detail: str = "") -> dict[str, Any]:
    """Progress. `stage` is machine-readable and drives the progress ladder;
    `detail` is the human line next to it ('reading notion.com')."""
    return event("claim.status", claim_id=claim_id, stage=stage, detail=detail)


# One item in claim.evidence. Pinned here because the page renders these
# BEFORE a verdict exists, so they are on the hot path and their shape cannot
# be discovered by waiting to see what turns up.
def evidence_item(
    evidence_id: str, url: str, title: str, tier: int, text: str
) -> dict[str, Any]:
    """One passage, as the page receives it.

    `evidence_id` is `E1`, `E2`... and is what a citation's `evidence_id`
    joins against, so a quote can be traced to the source it came from.
    `tier` is 1-4, see TIERS. `text` is truncated server-side.
    """
    return {
        "evidence_id": evidence_id,
        "url": url,
        "title": title,
        "tier": tier,
        "text": text[:EVIDENCE_TEXT_CHARS],
    }


def citation(evidence_id: str, quote: str) -> dict[str, Any]:
    """One verbatim quote, and which passage it came from.

    `evidence_id` matches an item in the claim's `claim.evidence`, so the page
    can show the quote next to its source. The quote has already been verified
    to appear in that passage; anything unverifiable was dropped before this
    message was built.
    """
    return {"evidence_id": evidence_id, "quote": quote}


EVIDENCE_TEXT_CHARS = 400


# What our own code did to the model's answer, one entry per rail that fired.
#
# This exists because the product was hiding its best argument. The judge
# invents a quote roughly once in four claims; the code catches it and goes
# and finds the real sentence. A viewer saw no difference between a quote
# taken on the model's word and one checked against the page, so the single
# strongest reason to trust any of this was invisible.
#
# `code` is what the page styles on. `note` is the human sentence. The page
# must never pattern-match the note: the wording changes, the codes do not.
CHECK_CODES = (
    "quote_verified",      # found word for word in the passage, nothing to fix
    "quote_trimmed",       # partly real; cut down to the part genuinely there
    "quote_recovered",     # the model retyped it; we found the real sentence
    "quote_dropped",       # not in the passage at all, thrown away
    "verdict_unsupported", # downgraded: nothing citable survived
    "evidence_off_topic",  # the passage was not about this claim
    "entities_missing",    # a named subject of the claim is absent from it
    "numbers_mismatch",    # arithmetic disagreed, so the verdict was forced
    "numbers_match",       # arithmetic agreed (reported, never an upgrade)
)


def check(code: str, note: str) -> dict[str, Any]:
    """One guard rail that fired, and what it did."""
    return {"code": code, "note": note}


def claim_evidence(claim_id: str, items: list[dict[str, Any]], depth: str) -> dict[str, Any]:
    """The passages the judge is about to read, shown before the verdict so
    the user watches it work rather than waiting at a spinner.

    `depth` is 'snippets' or 'pages' -- the app is always honest about how
    thin or deep the evidence under a verdict actually is.
    """
    return event("claim.evidence", claim_id=claim_id, items=items, depth=depth)


def claim_verdict(
    claim_id: str,
    verdict: str,
    sticker: str,
    summary: str,
    stage: str = "confirmed",
    citations: list[dict[str, Any]] | None = None,
    checks: list[dict[str, Any]] | None = None,
    depth: str = "snippets",
    took_ms: int | None = None,
    timings: dict[str, int] | None = None,
    correction: str = "",
    confidence: str = "none",
) -> dict[str, Any]:
    """A verdict.

    `stage` is 'provisional' or 'confirmed'. A provisional verdict is a fast
    read of search snippets, on screen in about three and a half seconds and
    labelled as a quick read. If the judge reports its evidence was too thin,
    the claim escalates -- fetch the pages, rank the passages, judge again --
    and a confirmed verdict replaces it in place.

    `timings` is the per-stage breakdown, which is what scripts/latency.py
    turns into a waterfall. Latency is the feature, so it is measured.

    `checks` is what our own code did to the model's answer: every guard rail
    that fired, with a machine-readable code. It is the difference between
    "an AI said so" and "here is the sentence on the page that says so", and
    without it that difference is invisible to anyone looking at the screen.
    """
    return event(
        "claim.verdict",
        claim_id=claim_id,
        verdict=verdict,
        sticker=sticker,
        summary=summary,
        stage=stage,
        citations=citations or [],
        checks=checks or [],
        depth=depth,
        took_ms=took_ms,
        timings=timings or {},
        correction=correction,
        confidence=confidence,
    )


def claim_error(claim_id: str, stage: str, message: str) -> dict[str, Any]:
    """A claim could not be checked: the budget ran out, a service was down,
    or something threw. `stage` says how far it got before it failed, so the
    user is told which part gave up rather than just seeing nothing."""
    return event("claim.error", claim_id=claim_id, stage=stage, message=message)


def server_note(message: str, level: str = "info") -> dict[str, Any]:
    """The status line. `level` is 'info', 'warn' or 'error'."""
    return event("server.note", message=message, level=level)


# --- the vocabulary, in one place so the server and the page agree ----------

# Closed sets. The page may style per value and may assume nothing else
# appears. Adding a value here is a protocol change.

CLAIM_KINDS = ("world_fact", "opinion", "prediction", "fluff", "vague")
HEDGES = ("stated", "asked", "hedged")
SHAPES = ("count", "event", "comparison", "other")

# Why a window was never sent to Claude. Free, decided in plain Python.
SKIP_REASONS = ("empty", "small talk", "too short", "no content words")

# How good the cited SOURCES are. Deliberately a separate axis from the
# verdict: what the evidence says and how trustworthy it is are two different
# questions, and folding them together once turned a correct contradiction
# into a weaker verdict purely because of which domain it sat on.
CONFIDENCE_LEVELS = ("none", "low", "medium", "high")

# Source trust. 1 is a primary or reference source, 2 serious reporting,
# 3 unknown, 4 a forum or social post.
TIERS = {1: "primary", 2: "reputable", 3: "unknown", 4: "low trust"}

# How deep the evidence under a verdict goes.
DEPTHS = ("snippets", "pages")

# Which rule in the chunker closed a window. Dev information.
WINDOW_REASONS = (
    "utterance_end", "max_sentences", "silence", "hard_silence",
    "max_duration", "flush",
)

STICKERS = {
    "SUPPORTED": "NO CAP",
    "CONTRADICTED": "ABSOLUTE CAP",
    "PARTIALLY_SUPPORTED": "SOME CAP",
    "DISPUTED": "SOURCES ARE FIGHTING",
    "INSUFFICIENT_EVIDENCE": "COULD BE CAP",
    "NOT_FACT_CHECKABLE": "WORD SALAD",
}

VERDICTS = tuple(STICKERS)


# --- what the page is allowed to send up ------------------------------------
#
#   {"type": "inject_text",    "text": "..."}   pretend the mic heard this
#   {"type": "start_listening"}
#   {"type": "stop_listening"}
#   {"type": "set_keys",       "keys": {...}}   BYOK; held in memory only
#
# plus raw binary frames of audio: 16-bit signed PCM, 16 kHz, mono,
# little-endian. Not WebM and not Opus, because iOS Safari will not produce
# Opus and a container we cannot rely on is a silent failure on the one
# device we most want this to work on.

CLIENT_MESSAGES = ("inject_text", "start_listening", "stop_listening", "set_keys")

AUDIO_FORMAT = {
    "encoding": "linear16",
    "sample_rate": 16000,
    "channels": 1,
}
