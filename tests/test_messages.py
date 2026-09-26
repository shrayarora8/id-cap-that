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
