"""Anchoring a claim to the exact characters it came from.

If this is wrong the highlight lands on the wrong words, which is worse than
no highlight: it makes the system look like it misunderstood.
"""

from __future__ import annotations

from server.chunker import Segment
from server.spans import locate


def seg(i, text):
    return Segment(f"s{i}", text)


def test_a_claim_inside_one_phrase():
    segments = [seg(1, "Messi scored 45 goals last season.")]
    spans = locate(segments, "Messi scored 45 goals")
    assert spans == [{"segment_id": "s1", "start": 0, "end": 21}]


def test_the_offsets_really_select_the_claim():
    """The test that matters: slice the phrase with what we returned and check
    we get the claim back."""
    text = "So I was reading that Notion charges a lot."
    segments = [seg(1, text)]
    spans = locate(segments, "Notion charges a lot")
    span = spans[0]
    assert text[span["start"]:span["end"]] == "Notion charges a lot"


def test_a_claim_straddling_two_phrases_produces_a_span_for_each():
    """A claim can start in one phrase and finish in the next, and the page
    draws one mark per phrase, so it needs both halves."""
    segments = [
        seg(1, "So I was reading that Notion charges"),
        seg(2, "about five hundred dollars per user per month."),
    ]
    spans = locate(segments, "Notion charges about five hundred dollars")
    assert len(spans) == 2
    assert spans[0]["segment_id"] == "s1"
    assert spans[1]["segment_id"] == "s2"
    assert spans[1]["start"] == 0

    rebuilt = (
        segments[0].text[spans[0]["start"]:spans[0]["end"]]
        + " "
        + segments[1].text[spans[1]["start"]:spans[1]["end"]]
    )
    assert rebuilt == "Notion charges about five hundred dollars"


def test_a_paraphrase_returns_nothing_rather_than_guessing():
    """When Claude rewrites instead of copying, we must say so, so the caller
    can highlight the whole window rather than the wrong words."""
    segments = [seg(1, "Messi scored 45 goals last season.")]
    assert locate(segments, "Lionel Messi netted forty five times") == []


def test_matching_ignores_case_when_it_has_to():
    segments = [seg(1, "Notion charges a lot of money.")]
    spans = locate(segments, "notion charges a lot")
    assert spans and spans[0]["start"] == 0


def test_extra_whitespace_in_the_claim_does_not_break_the_match():
    segments = [seg(1, "Messi scored 45 goals last season.")]
    assert locate(segments, "Messi   scored  45 goals")


def test_empty_input_is_handled():
    assert locate([seg(1, "anything at all")], "") == []
    assert locate([], "something") == []


def test_only_the_phrases_the_claim_touches_get_spans():
    segments = [
        seg(1, "First sentence here."),
        seg(2, "Messi scored 45 goals."),
        seg(3, "Third sentence here."),
    ]
    spans = locate(segments, "Messi scored 45 goals")
    assert [s["segment_id"] for s in spans] == ["s2"]
