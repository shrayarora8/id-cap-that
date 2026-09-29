"""The contract is the one file both halves of the system are built against,
so it gets tested even though it is 'just' dictionaries.

These tests are free and instant. They exist to catch the shape drifting,
which is the failure that shows up as a blank screen with no error anywhere.
"""

from __future__ import annotations

import inspect

import pytest

from server import messages as m


def test_every_message_has_a_type_and_a_timestamp():
    msg = m.server_note("hello")
    assert msg["type"] == "server.note"
    assert isinstance(msg["ts"], int) and msg["ts"] > 0


def test_kind_does_not_collide_with_the_builder_parameter():
    """The bug this pins: `def event(type, **fields)` plus a claim whose own
    field is called `kind` raises TypeError inside a background task nobody is
    watching, so claims silently stop appearing and there is no traceback."""
    msg = m.claim_detected(
        claim_id="c1",
        window_id="w1",
        spans=[],
        quote="q",
        normalized="n",
        kind="world_fact",
        hedge="stated",
        shape="count",
        checkable=True,
    )
    assert msg["kind"] == "world_fact"
    assert msg["type"] == "claim.detected"


def test_event_never_loses_a_field_to_its_own_parameter_names():
    """Any field name a message might carry must survive the builder."""
    for risky in ("type", "kind", "message_type", "stage", "text", "fields"):
        msg = m.event("test.message", **{risky: "value"})
        if risky == "type":
            continue  # the message type itself legitimately wins
        assert msg[risky] == "value", f"{risky} was eaten by the builder"


def test_every_verdict_has_a_sticker():
    for verdict in m.VERDICTS:
        assert m.STICKERS[verdict], f"{verdict} has no sticker"


def test_stickers_are_the_agreed_wording():
    assert m.STICKERS["SUPPORTED"] == "NO CAP"
    assert m.STICKERS["CONTRADICTED"] == "ABSOLUTE CAP"
    assert m.STICKERS["NOT_FACT_CHECKABLE"] == "WORD SALAD"


def test_a_verdict_is_provisional_or_confirmed():
    quick = m.claim_verdict("c1", "SUPPORTED", "NO CAP", "s", stage="provisional")
    assert quick["stage"] == "provisional"
    # The default is the safe one: a verdict is final unless it says otherwise.
    assert m.claim_verdict("c1", "SUPPORTED", "NO CAP", "s")["stage"] == "confirmed"


def test_a_verdict_says_how_deep_its_evidence_was():
    """The app is always honest about whether a verdict rests on a search
    snippet or on a page it actually read."""
    msg = m.claim_verdict("c1", "SUPPORTED", "NO CAP", "s", depth="pages")
    assert msg["depth"] == "pages"


def test_claim_status_carries_a_machine_readable_stage():
    """The page draws a progress ladder from `stage`, so a three-second step
    still looks like it is moving. `detail` is only the human line."""
    msg = m.claim_status("c1", "reading", "reading notion.com")
    assert msg["stage"] in m.STAGE_ORDER
    assert msg["detail"] == "reading notion.com"


@pytest.mark.parametrize("stage", m.STAGE_ORDER)
def test_every_stage_is_usable(stage):
    assert m.claim_status("c1", stage)["stage"] == stage


def test_mutable_defaults_are_not_shared_between_messages():
    """citations=[] as a default argument would be one list shared by every
    verdict ever built. Pins that it is not."""
    a = m.claim_verdict("c1", "SUPPORTED", "NO CAP", "s")
    b = m.claim_verdict("c2", "SUPPORTED", "NO CAP", "s")
    a["citations"].append({"evidence_id": "E1", "quote": "x"})
    assert b["citations"] == []
    assert a["timings"] is not b["timings"]


def test_audio_format_is_raw_pcm_not_a_container():
    """iOS Safari will not produce Opus. A container we cannot rely on is a
    silent failure on the one device we most want this to work on."""
    assert m.AUDIO_FORMAT["encoding"] == "linear16"
    assert m.AUDIO_FORMAT["sample_rate"] == 16000
    assert m.AUDIO_FORMAT["channels"] == 1


def test_session_ready_tells_the_page_everything_it_needs_to_start():
    msg = m.session_ready(
        "sess_1", m.PROTOCOL_VERSION, {"claims_left": 12}, m.AUDIO_FORMAT
    )
    assert msg["protocol_version"] == m.PROTOCOL_VERSION
    assert msg["audio"]["sample_rate"] == 16000
    assert msg["budget"]["claims_left"] == 12


def test_budget_update_reports_which_pool_is_paying():
    msg = m.budget_update(claims_left=9, claims_cap=12, pool="public")
    assert msg["pool"] == "public"
    assert msg["exhausted"] is False


def test_every_builder_is_documented():
    """These functions are the spec. An undocumented one is a field whose
    meaning lives only in someone's head."""
    builders = [
        f
        for name, f in inspect.getmembers(m, inspect.isfunction)
        if not name.startswith("_") and f.__module__ == m.__name__
    ]
    undocumented = [f.__name__ for f in builders if not (f.__doc__ or "").strip()]
    assert not undocumented, f"undocumented message builders: {undocumented}"


# --- config guard rails -----------------------------------------------------


def test_utterance_end_ms_is_not_below_deepgrams_floor():
    """Deepgram rejects the handshake with HTTP 400 when utterance_end_ms is
    under 1000. The connection never opens, so no audio is ever sent and the
    transcript stays empty with nothing on screen explaining it. Setting 700
    here to shave 300ms of latency broke the microphone completely."""
    from server import config

    assert config.DEEPGRAM_UTTERANCE_END_MS >= config.DEEPGRAM_UTTERANCE_END_MS_FLOOR


def test_the_deepgram_url_declares_the_audio_format_we_actually_send():
    """Without encoding/sample_rate/channels Deepgram tries to sniff a
    container, finds raw samples, and returns nothing at all -- silently."""
    from server import config
    from server.transcribe import _build_url

    url = _build_url()
    assert "encoding=linear16" in url
    assert f"sample_rate={config.AUDIO_SAMPLE_RATE}" in url
    assert f"channels={config.AUDIO_CHANNELS}" in url


def test_the_wire_format_and_the_deepgram_url_agree():
    """The page is told one format in session.ready and Deepgram is told
    another in the URL. If those two ever disagree, audio is garbage and the
    only symptom is an empty transcript."""
    from server import messages
    from server.transcribe import _build_url

    url = _build_url()
    assert f"sample_rate={messages.AUDIO_FORMAT['sample_rate']}" in url
    assert f"encoding={messages.AUDIO_FORMAT['encoding']}" in url
    assert f"channels={messages.AUDIO_FORMAT['channels']}" in url


# --- the closed sets the page styles against --------------------------------


def test_evidence_item_has_the_keys_the_page_renders():
    item = m.evidence_item("E1", "https://notion.com/pricing", "Pricing", 1, "x" * 900)
    assert set(item) == {"evidence_id", "url", "title", "tier", "text"}
    assert len(item["text"]) == m.EVIDENCE_TEXT_CHARS, "text must be truncated server-side"


def test_a_citation_joins_to_the_evidence_it_came_from():
    """This join is what lets the page show a quote next to its source."""
    items = [m.evidence_item("E1", "u", "t", 1, "some passage text")]
    cite = m.citation("E1", "some passage text")
    assert cite["evidence_id"] == items[0]["evidence_id"]
    assert set(cite) == {"evidence_id", "quote"}


def test_tiers_cover_one_to_four():
    assert sorted(m.TIERS) == [1, 2, 3, 4]


def test_confidence_is_a_closed_set_including_the_default():
    assert "none" in m.CONFIDENCE_LEVELS
    assert m.claim_verdict("c1", "SUPPORTED", "NO CAP", "s")["confidence"] in m.CONFIDENCE_LEVELS


def test_depth_is_a_closed_set():
    assert m.claim_verdict("c1", "SUPPORTED", "NO CAP", "s")["depth"] in m.DEPTHS


def test_claim_detected_fields_come_from_closed_sets():
    msg = m.claim_detected(
        "c1", "w1", [], "q", "n", kind="world_fact", hedge="stated",
        shape="count", checkable=True,
    )
    assert msg["kind"] in m.CLAIM_KINDS
    assert msg["hedge"] in m.HEDGES
    assert msg["shape"] in m.SHAPES


# --- the UI fixture ---------------------------------------------------------


def test_the_synthetic_fixture_matches_the_contract():
    """The fixture is what the frontend builds against, so it must not drift.
    It is generated by the real builders; this proves the file on disk still
    agrees with them."""
    import json
    from pathlib import Path

    path = Path(__file__).parent / "fixtures" / "synthetic_session.jsonl"
    rows = [json.loads(line) for line in path.read_text().splitlines() if line.strip()]

    assert rows, "fixture is empty"
    assert [r["_t"] for r in rows] == sorted(r["_t"] for r in rows), "not in time order"

    for row in rows:
        assert "type" in row and "ts" in row and "seq" in row
        if row["type"] == "claim.verdict":
            assert row["stage"] in ("provisional", "confirmed")
            assert row["depth"] in m.DEPTHS
            assert row["confidence"] in m.CONFIDENCE_LEVELS
            assert row["verdict"] in m.VERDICTS
            assert row["sticker"] == m.STICKERS[row["verdict"]]
        if row["type"] == "claim.detected":
            assert row["kind"] in m.CLAIM_KINDS
            assert row["hedge"] in m.HEDGES
            assert row["shape"] in m.SHAPES
        if row["type"] == "window.skipped":
            assert row["reason"] in m.SKIP_REASONS
        if row["type"] == "claim.evidence":
            for item in row["items"]:
                assert set(item) == {"evidence_id", "url", "title", "tier", "text"}
                assert item["tier"] in m.TIERS


def test_the_fixture_covers_the_three_branches_the_ui_cannot_otherwise_reach():
    import json
    from pathlib import Path

    path = Path(__file__).parent / "fixtures" / "synthetic_session.jsonl"
    rows = [json.loads(line) for line in path.read_text().splitlines() if line.strip()]

    verdicts = [r for r in rows if r["type"] == "claim.verdict"]
    assert any(v["stage"] == "provisional" for v in verdicts)
    # The same claim must appear twice: once provisional, once confirmed, so
    # the upgrade-in-place transition can be built and seen.
    upgraded = {v["claim_id"] for v in verdicts if v["stage"] == "provisional"} & {
        v["claim_id"] for v in verdicts if v["stage"] == "confirmed"
    }
    assert upgraded, "no claim is upgraded from provisional to confirmed"

    assert any(r["type"] == "claim.error" for r in rows)
    assert any(r["type"] == "budget.update" and r["exhausted"] for r in rows)


def test_we_do_not_claim_a_prompt_cache_that_cannot_fire():
    """Haiku 4.5 needs a 4096-token prefix before Anthropic will cache it, and
    both our system prompts are far shorter. A cache_control block below the
    minimum is accepted, does nothing, and reports zero cached tokens forever
    -- with no error. Measured at 0 across every call before it was removed."""
    from server import config, llm, sorter

    minimum = llm.CACHE_MINIMUM_TOKENS[config.SORTER_MODEL]
    # ~4 characters per token is the usual rough conversion.
    estimated_tokens = len(sorter.SYSTEM) / 4
    assert estimated_tokens < minimum, (
        "the sorter prompt now exceeds the cache minimum -- prompt caching "
        "has become worth adding, with measurement this time"
    )


# --- every detected claim must reach a settled state ------------------------


def test_every_exit_from_check_claim_sends_a_terminal_message():
    """A claim.detected that is never answered leaves the elapsed counter
    ticking upward forever beside the words. That counter is the honesty of
    the whole product, so a counter that can run forever is not a cosmetic
    problem.

    This reads the source rather than running the pipeline: every `return`
    inside check_claim must be preceded by something that sends a verdict or
    an error.
    """
    import inspect
    import re as _re

    from server import main

    source = inspect.getsource(main.check_claim)
    body = source[source.index("try:"):]

    # Split at each return and check something terminal was sent before it.
    segments = body.split("return")[:-1]
    for i, segment in enumerate(segments):
        tail = segment[-700:]
        assert _re.search(r"send_verdict\(|claim_error\(", tail), (
            f"return #{i + 1} in check_claim exits without a verdict or an error"
        )


# --- Moss recall ------------------------------------------------------------


def test_moss_recall_is_gated_on_the_subject_not_just_similarity():
    """The bug this pins, measured live. Asked whether the Danube flows
    through Vienna, Moss confidently returned five passages about the Amazon,
    every one above the similarity threshold, and the claim was answered from
    them without searching at all.

    A similarity score is not a subject check. A wrong shortcut costs a wrong
    verdict; a right one only saves about a second. So a remembered passage
    must also NAME what the claim is about.
    """
    from server import config
    from server.judge import claim_names

    amazon = "the amazon river flows through brazil into the atlantic ocean."

    danube = claim_names("The Danube flows through Vienna.")
    assert danube and not any(n in amazon for n in danube), "must not reuse"

    same = claim_names("The Amazon River is 6400 kilometres long.")
    assert any(n in amazon for n in same), "the same subject must still be reused"

    assert config.MOSS_TIMEOUT_S <= 2.0, "recall must never become the slow part"


# --- the fast-provider fallback ---------------------------------------------


def test_the_sorter_falls_back_rather_than_failing():
    """Groq's free tier allows roughly three sorter calls a minute and a
    conversation produces more, so refusal is the normal case, not the
    exception. It must never surface as a failed claim.

    Reads the source rather than calling the network: `ask_fast` must have a
    path that ends in the Anthropic model no matter what the fast provider
    does."""
    import inspect

    from server import config, llm

    src = inspect.getsource(llm.ask_fast)
    assert "except Exception" in src, "a refusal must not propagate"
    assert "config.SORTER_MODEL" in src, "there must be a Claude fallback"
    # A hang is the only failure that could cost the user real time.
    assert config.GROQ_TIMEOUT_S <= 6.0, "an unbounded wait defeats the point"


def test_turning_the_fast_provider_off_restores_claude_only():
    """One config line must return the system to known behaviour.

    Asserted by calling it rather than by reading its source: the point is
    that Groq is never touched, which is a fact about behaviour, and a test
    that greps for a string breaks on any honest refactor while still
    passing on a broken one.
    """
    import asyncio

    from server import config, llm

    called = {}

    async def fake_ask(*, model, system, user, schema, max_tokens=2000):
        called["model"] = model
        return "claude answered"

    async def fake_groq(*a, **k):
        called["groq"] = True
        raise AssertionError("groq must not be called with the provider off")

    old_ask, old_groq = llm.ask, llm._ask_groq
    old_provider = config.SORTER_PROVIDER
    try:
        llm.ask, llm._ask_groq = fake_ask, fake_groq
        config.SORTER_PROVIDER = "anthropic"
        out = asyncio.run(llm.ask_fast(system="s", user="u", schema=str))
    finally:
        llm.ask, llm._ask_groq = old_ask, old_groq
        config.SORTER_PROVIDER = old_provider

    assert out == "claude answered"
    assert "groq" not in called
    assert called["model"] == config.SORTER_MODEL


def test_the_judge_can_switch_provider_independently_of_the_sorter():
    """The two legs are worth different decisions.

    The sorter is a cheap easy job and moved to Groq happily. The judge must
    return a quote our code verifies word for word, so it may need to stay on
    Claude even when the sorter does not -- which is only possible if the
    caller can choose.
    """
    import asyncio

    from server import config, llm

    seen = {}

    async def fake_ask(*, model, system, user, schema, max_tokens=2000):
        seen["model"] = model
        return "fallback"

    old_ask, old_provider = llm.ask, config.SORTER_PROVIDER
    try:
        llm.ask = fake_ask
        config.SORTER_PROVIDER = "groq"          # sorter on Groq...
        asyncio.run(llm.ask_fast(                # ...judge explicitly not
            system="s", user="u", schema=str,
            provider="anthropic", fallback_model="judge-model",
        ))
    finally:
        llm.ask, config.SORTER_PROVIDER = old_ask, old_provider

    assert seen["model"] == "judge-model"


def test_both_providers_are_checked_in_the_cache_before_either_is_called():
    """Otherwise a claim Claude already answered gets re-offered to Groq on
    every repeat, purely to be refused."""
    import inspect

    from server import llm

    src = inspect.getsource(llm.ask_fast)
    body = src[src.index("for model in"):]
    assert "_cached" in body


def test_a_hosted_postgres_url_is_made_safe_for_asyncpg():
    """Neon hands out channel_binding, Supabase hands out pgbouncer.

    asyncpg understands neither and raises. The pool then fails, the store
    falls back to files, and the database someone just set up is never
    touched -- while everything keeps working, so nothing says so.
    """
    from server.store import pg_url

    neon = pg_url(
        "postgresql://u:p@ep-x.aws.neon.tech/neondb"
        "?sslmode=require&channel_binding=require"
    )
    assert "channel_binding" not in neon
    assert "sslmode=require" in neon, "Neon requires TLS -- do not strip this"

    supa = pg_url("postgresql://u:p@db.supabase.co:5432/postgres?pgbouncer=true")
    assert "pgbouncer" not in supa

    # A SQLAlchemy-style scheme is accepted and normalised rather than
    # rejected, because it is what most docs paste.
    assert pg_url("postgresql+asyncpg://u:p@h/db").startswith("postgresql://")

    # Nothing to fix is not an error.
    assert pg_url("postgresql://u:p@h/db") == "postgresql://u:p@h/db"


def test_health_says_which_store_is_actually_in_use():
    """A broken DATABASE_URL and no DATABASE_URL behave identically from
    outside. Both keep answering, both forget on restart."""
    from server import store

    b = store.backend()
    assert b["store"] in ("postgres", "files")
    if b["store"] == "files":
        assert b.get("why"), "a fallback must say why, or it is invisible"
