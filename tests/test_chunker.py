"""The chunker's tests are its specification.

A fake clock means every timing rule is exercised instantly, with no sleeping
and nothing spent. Several of these are bugs that shipped in the previous
build, pinned so they cannot come back.
"""

from __future__ import annotations

import pytest

from server import config
from server.chunker import Chunker, Window


class Clock:
    """A clock the test drives by hand."""

    def __init__(self) -> None:
        self.t = 1000.0

    def __call__(self) -> float:
        return self.t

    def advance_ms(self, ms: float) -> None:
        self.t += ms / 1000.0


@pytest.fixture
def setup():
    closed: list[Window] = []
    clock = Clock()
    chunker = Chunker(on_window=closed.append, now=clock)
    return chunker, closed, clock


def test_nothing_closes_an_empty_chunker(setup):
    chunker, closed, clock = setup
    clock.advance_ms(10_000)
    chunker.tick()
    chunker.utterance_end()
    assert closed == []


def test_max_sentences_closes_immediately(setup):
    chunker, closed, _ = setup
    for i in range(config.WINDOW_MAX_SENTENCES):
        chunker.add_segment(f"s{i}", f"This is sentence number {i}.")
    assert len(closed) == 1
    assert closed[0].reason == "max_sentences"


def test_utterance_end_closes_a_finished_sentence(setup):
    chunker, closed, _ = setup
    chunker.add_segment("s1", "Messi scored 45 goals last season.")
    chunker.utterance_end()
    assert len(closed) == 1
    assert closed[0].reason == "utterance_end"
    assert closed[0].text == "Messi scored 45 goals last season."


def test_a_pause_does_not_close_a_sentence_that_is_not_finished(setup):
    """The bug this pins: 'I have good experience, you know, working' closed
    on a pause and the rest of the sentence became a separate window. Neither
    half was a claim, so the buzzwords went unflagged."""
    chunker, closed, clock = setup
    chunker.add_segment("s1", "I have good experience, you know, working")
    clock.advance_ms(config.WINDOW_SILENCE_MS + 50)
    chunker.tick()
    assert closed == [], "a pause mid-sentence must not close the window"

    chunker.add_segment("s2", "across cross functional teams.")
    chunker.utterance_end()
    assert len(closed) == 1
    assert "cross functional teams" in closed[0].text
    assert "good experience" in closed[0].text, "both halves belong to one window"


def test_utterance_end_is_also_gated_on_a_finished_thought(setup):
    """UtteranceEnd is the strongest signal we get, and it is still not enough
    on its own -- Deepgram fires it on a breath."""
    chunker, closed, _ = setup
    chunker.add_segment("s1", "and then the thing about")
    chunker.utterance_end()
    assert closed == []


def test_too_few_words_is_not_a_finished_thought(setup):
    """'Yes.' ends in a full stop and is not a sentence worth checking."""
    chunker, closed, clock = setup
    chunker.add_segment("s1", "Yes.")
    chunker.utterance_end()
    assert closed == []


def test_hard_silence_closes_whatever_is_there(setup):
    """They have genuinely stopped. Take it, however unfinished, or those
    words sit on screen forever."""
    chunker, closed, clock = setup
    chunker.add_segment("s1", "and then the thing about")
    clock.advance_ms(config.WINDOW_HARD_SILENCE_MS + 50)
    chunker.tick()
    assert len(closed) == 1
    assert closed[0].reason == "hard_silence"


def test_unpunctuated_rambling_closes_on_the_word_cap(setup):
    """Escape hatch: some speech never gets punctuated at all, and without
    this we would wait for a full stop that never comes."""
    chunker, closed, clock = setup
    words = " ".join(f"word{i}" for i in range(config.WINDOW_MAX_WORDS_UNPUNCTUATED + 2))
    chunker.add_segment("s1", words)
    clock.advance_ms(config.WINDOW_SILENCE_MS + 50)
    chunker.tick()
    assert len(closed) == 1
    assert closed[0].reason == "silence"


def test_max_duration_cuts_into_a_monologue(setup, monkeypatch):
    """The 12-second cap.

    Worth being honest about: at the default config this rule is unreachable.
    Reaching 12s needs segments still arriving (or hard_silence fires at 2.5s)
    but fewer than WINDOW_MAX_SENTENCES of them (or max_sentences fires first),
    and with a cap of 3 those two conditions cannot both hold. It is kept as
    cheap insurance for anyone who raises the sentence cap, which is exactly
    the config this test uses.
    """
    monkeypatch.setattr(config, "WINDOW_MAX_SENTENCES", 100)
    monkeypatch.setattr(config, "WINDOW_HARD_MAX_SENTENCES", 100)
    chunker, closed, clock = setup

    # Sub-second gaps so the silence rule never fires, one short unpunctuated
    # word each so neither the punctuation branch nor the 25-word escape hatch
    # makes the window closeable. All that is left is the duration cap.
    elapsed = 0.0
    n = 0
    while elapsed < config.WINDOW_MAX_MS + 2000 and not closed:
        chunker.add_segment(f"s{n}", "and")
        n += 1
        clock.advance_ms(900)
        elapsed += 900
        chunker.tick()

    assert len(closed) == 1
    assert closed[0].reason == "max_duration"


def test_hard_silence_beats_max_duration_at_the_default_config(setup):
    """Documents the consequence of the above: with the shipped settings, a
    speaker who stops is always caught by hard_silence long before the 12s
    cap could matter."""
    chunker, closed, clock = setup
    chunker.add_segment("s1", "starting a long thought")
    clock.advance_ms(config.WINDOW_MAX_MS + 1000)
    chunker.tick()
    assert closed[0].reason == "hard_silence"


def test_a_window_carries_the_previous_one_as_context(setup):
    """'It was 78%' is only a claim if you know what 'it' was."""
    chunker, closed, _ = setup
    chunker.add_segment("s1", "Our retention last year was strong.")
    chunker.utterance_end()
    chunker.add_segment("s2", "It was 78 percent actually.")
    chunker.utterance_end()

    assert len(closed) == 2
    assert closed[0].context == ""
    assert closed[1].context == "Our retention last year was strong."


def test_window_ids_are_sequential_and_stable(setup):
    chunker, closed, _ = setup
    for i in range(3):
        chunker.add_segment(f"s{i}", f"This is a real sentence number {i}.")
        chunker.utterance_end()
    assert [w.window_id for w in closed] == ["w1", "w2", "w3"]


def test_a_window_reports_every_segment_it_contains(setup):
    """The page moves exactly these ids out of pending, so a missing one
    leaves a phrase stranded in the transcript forever."""
    chunker, closed, _ = setup
    chunker.add_segment("s1", "Messi scored 45 goals")
    chunker.add_segment("s2", "in the last season.")
    chunker.utterance_end()
    assert closed[0].segment_ids == ["s1", "s2"]


def test_flush_closes_a_half_finished_window(setup):
    chunker, closed, _ = setup
    chunker.add_segment("s1", "something unfinished")
    chunker.flush()
    assert len(closed) == 1
    assert closed[0].reason == "flush"


def test_flush_on_an_empty_chunker_does_nothing(setup):
    chunker, closed, _ = setup
    chunker.flush()
    assert closed == []


def test_empty_and_whitespace_segments_are_ignored(setup):
    chunker, closed, _ = setup
    chunker.add_segment("s1", "   ")
    chunker.add_segment("s2", "")
    assert chunker.pending == []
    assert closed == []


def test_the_clock_starts_when_the_first_segment_arrives(setup):
    """max_duration must measure from the first word of this window, not from
    the start of the session."""
    chunker, closed, clock = setup
    clock.advance_ms(60_000)  # a minute of silence before anyone speaks
    chunker.add_segment("s1", "Now someone finally says something.")
    chunker.tick()
    assert closed == [], "the window is one tick old, not a minute old"


def test_closing_resets_everything_for_the_next_window(setup):
    chunker, closed, _ = setup
    chunker.add_segment("s1", "A perfectly ordinary first sentence.")
    chunker.utterance_end()
    assert chunker.pending == []
    assert chunker.started_at is None
    chunker.add_segment("s2", "And a second one after it.")
    assert len(chunker.pending) == 1


# --- fragments: the sentence that got cut in half ---------------------------


def test_a_window_cut_mid_sentence_marks_the_next_one_as_its_continuation():
    """The bug this pins, seen live: a 2.5s pause mid-sentence closed
    'This product will revolutionize the market through' on hard_silence,
    and 'cross functional synergy.' became a three-word window that the
    pre-filter dropped as too short. The buzzwords went unflagged, which is
    the whole feature.

    hard_silence is the only rule allowed to split a sentence, so when it
    does, the next window must be told it is the rest of a thought.
    """
    closed = []
    clock = Clock()
    chunker = Chunker(on_window=closed.append, now=clock)

    chunker.add_segment("s1", "This product will revolutionize the market through")
    clock.advance_ms(config.WINDOW_HARD_SILENCE_MS + 100)
    chunker.tick()

    assert closed[0].reason == "hard_silence"
    assert closed[0].continues_previous is False

    chunker.add_segment("s2", "cross functional synergy.")
    chunker.utterance_end()

    assert len(closed) == 2
    assert closed[1].continues_previous is True, "the tail must know it is a tail"
    assert closed[1].context == "This product will revolutionize the market through"


def test_a_window_after_a_finished_sentence_is_not_a_continuation():
    closed = []
    clock = Clock()
    chunker = Chunker(on_window=closed.append, now=clock)

    chunker.add_segment("s1", "Messi scored 45 goals last season.")
    chunker.utterance_end()
    chunker.add_segment("s2", "Notion charges twenty dollars a seat.")
    chunker.utterance_end()

    assert closed[0].continues_previous is False
    assert closed[1].continues_previous is False, "a full stop ends the thought"


def test_hard_silence_is_long_enough_for_a_real_pause():
    """People pause mid-sentence while talking to a demo. 2.5s was too short
    and split sentences in half."""
    assert config.WINDOW_HARD_SILENCE_MS >= 3500


def test_a_phrase_count_never_cuts_a_sentence_in_half():
    """The bug this pins, seen on a phone mid-demo.

    Deepgram emitted "Taylor Swift has won 28" and "Grammys." as separate
    phrases. The third phrase arriving force-closed the window regardless of
    punctuation, so "Grammys." became a window of one word, the pre-filter
    dropped it as too short, and the claim disappeared with no mark and no
    explanation. Same for "Did you know Python was released first in" /
    "1995?".

    A phrase count is a guard against a monologue, not a sentence boundary.
    """
    closed = []
    chunker = Chunker(on_window=closed.append)

    chunker.add_segment("s1", "Taylor Swift has won 28")
    chunker.add_segment("s2", "Grammys.")
    chunker.add_segment("s3", "Honestly Snowflake is")

    assert not closed or "Grammys." in closed[0].text, (
        "a sentence must not be split by the phrase count"
    )
    for window in closed:
        assert window.text.strip() != "Grammys.", "the tail was orphaned again"


def test_a_speaker_who_never_finishes_a_sentence_is_still_checked():
    """The escape hatch: the hard cap has to fire eventually, or someone who
    never pauses is never checked at all."""
    closed = []
    chunker = Chunker(on_window=closed.append)
    for i in range(config.WINDOW_HARD_MAX_SENTENCES):
        chunker.add_segment(f"s{i}", "and then another thing")
    assert len(closed) == 1
    assert closed[0].reason == "max_sentences"
