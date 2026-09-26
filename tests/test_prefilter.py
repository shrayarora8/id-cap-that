"""The pre-filter's job is to be free and conservative.

Every sentence here is one a real conversation produced. The rule being
tested throughout: a missed claim costs far more than a wasted API call, so
when in doubt it must pass the window through.
"""

from __future__ import annotations

import pytest

from server.prefilter import worth_checking

SKIP = [
    "How's it going?",
    "Yeah.",
    "Wait, what?",
    "I bet.",
    "ok",
    "Hey man",
    "thanks",
    "Cool.",
    "Alright.",
    "Bro.",
    "see you later",
    "testing",
    "um",
    "",
    "   ",
    "...",
]

CHECK = [
    "Messi scored 45 goals last season.",
    "Notion charges about five hundred dollars per user per month.",
    "Our retention was 94 percent last quarter.",
    "Apple sold 240 million iPhones in 2025.",
    "The Eiffel Tower is 330 metres tall.",
    # Buzzwords are NOT skipped here: only Claude can tell buzzwords from a
    # real claim, and WORD SALAD is a verdict we want to show, not silence.
    "This product will revolutionize the market through cross functional synergy.",
    # A question about a fact is still checkable.
    "Didn't Messi win the Ballon d'Or in 2023?",
    # Hedging is about the speaker, not about the world.
    "I think Notion costs about twenty dollars a seat.",
]


@pytest.mark.parametrize("text", SKIP)
def test_obvious_non_claims_are_skipped_for_free(text):
    allowed, reason = worth_checking(text)
    assert allowed is False, f"{text!r} should not cost an API call"
    assert reason


@pytest.mark.parametrize("text", CHECK)
def test_anything_that_could_be_a_claim_goes_through(text):
    allowed, reason = worth_checking(text)
    assert allowed is True, f"{text!r} must not be silently dropped"


def test_one_real_claim_rescues_a_window_full_of_chatter():
    """A window is often several sentences. One claim anywhere in it justifies
    the call, so the whole window goes through."""
    allowed, _ = worth_checking("Yeah. Right. Messi scored 45 goals last season.")
    assert allowed is True


def test_several_pieces_of_small_talk_are_still_small_talk():
    """The bug this guards: judging the window as one string made 'BRO.
    What's going on?' look like an odd claim instead of two bits of chatter."""
    allowed, reason = worth_checking("Bro. What's going on?")
    assert allowed is False
    assert reason == "small talk"


def test_the_reason_is_always_something_the_ui_can_show():
    from server import messages

    for text in SKIP:
        allowed, reason = worth_checking(text)
        assert reason in messages.SKIP_REASONS, f"{reason!r} is not in the contract"


def test_it_is_conservative_about_anything_unusual():
    """Nonsense that is not in any list must still go through. Being wrong in
    this direction costs a fifth of a cent; being wrong the other way loses a
    claim entirely."""
    allowed, _ = worth_checking("The flarn quotient exceeded nine thousand.")
    assert allowed is True


# --- continuations ----------------------------------------------------------


def test_the_tail_of_a_split_sentence_is_never_dropped_as_too_short():
    """'cross functional synergy.' is three words and looks like nothing on
    its own. It is the payload of the sentence before it. Dropping it is how
    a window full of buzzwords goes unflagged."""
    assert worth_checking("cross functional synergy.")[0] is False
    assert worth_checking("cross functional synergy.", continues_previous=True)[0] is True


def test_a_continuation_with_no_content_is_still_dropped():
    """Being permissive about continuations must not mean paying for 'um'."""
    allowed, reason = worth_checking("um, you know", continues_previous=True)
    assert allowed is False
    assert reason == "no content words"


def test_continuation_reasons_are_still_in_the_contract():
    from server import messages

    for text in ("", "um, you know"):
        _, reason = worth_checking(text, continues_previous=True)
        assert reason in messages.SKIP_REASONS


def test_a_two_word_fragment_is_never_checked_even_as_a_continuation():
    """'Fifty seconds.' went through as a claim, the search found a Lisbon
    restaurant of that name, and the verdict was a confident NO CAP about a
    lift. A fragment asserts nothing and must not reach a search engine."""
    assert worth_checking("Fifty seconds.", continues_previous=True)[0] is False
    assert worth_checking("Per user.", continues_previous=True)[0] is False


def test_a_real_continuation_still_goes_through():
    assert worth_checking("cross functional synergy.", continues_previous=True)[0] is True
    assert worth_checking("costs twenty dollars a seat.", continues_previous=True)[0] is True
