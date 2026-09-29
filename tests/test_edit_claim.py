"""Correcting a claim the transcription got wrong.

"Sasha Moore works at Adobe" was heard as "Saasha mor works at adobe". That
went to the live web, spent a credit, and came back NO CAP -- confidently
wrong about a person, off a misheard name. The words on screen are the only
place that error is visible, so they are where it has to be fixable.
"""

from server import messages


def test_a_corrected_claim_carries_what_was_heard():
    """The record of what was said is kept, not overwritten.

    A tool that checks what people say must not quietly rewrite the record
    of what they said. The heard text is also the only thing that explains
    WHY a check went wrong.
    """
    m = messages.claim_detected(
        claim_id="c1", window_id="w1",
        spans=[{"segment_id": "s1", "start": 0, "end": 26}],
        quote="Sasha Moore works at Adobe",
        normalized="Sasha Moore works at Adobe",
        kind="world_fact", hedge="stated", shape="other", checkable=True,
        edited=True, heard="Saasha mor works at adobe.",
    )
    assert m["edited"] is True
    assert m["heard"] == "Saasha mor works at adobe."
    assert m["normalized"] == "Sasha Moore works at Adobe"


def test_an_ordinary_claim_is_not_marked_edited():
    m = messages.claim_detected(
        claim_id="c1", window_id="w1", spans=[],
        quote="q", normalized="n", kind="world_fact",
        hedge="stated", shape="other", checkable=True,
    )
    assert m["edited"] is False
    assert m["heard"] == ""


def test_the_edit_keeps_the_claim_id_so_the_verdict_lands_in_place():
    """The page draws the claim from claim.detected. Re-emitting it under
    the same id is what stops the page and the server disagreeing about
    what is being checked once the sorter normalises a correction its own
    way -- which it will."""
    first = messages.claim_detected(
        claim_id="c1", window_id="w1", spans=[{"segment_id": "s1", "start": 0, "end": 5}],
        quote="heard", normalized="heard", kind="world_fact",
        hedge="stated", shape="other", checkable=True,
    )
    after = messages.claim_detected(
        claim_id="c1", window_id="w1", spans=first["spans"],
        quote="fixed", normalized="fixed", kind="world_fact",
        hedge="stated", shape="other", checkable=True,
        edited=True, heard="heard",
    )
    assert after["claim_id"] == first["claim_id"]
    # The transcript characters never change on an edit, so the highlight
    # must not move either.
    assert after["spans"] == first["spans"]
    assert after["type"] == first["type"] == "claim.detected"
