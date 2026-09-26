"""Deciding when someone has finished a thought.

Deepgram gives us finished *phrases*. That is too small a unit to check:
"It was 94%" means nothing on its own. So phrases are collected into a window,
and only when a window closes do we pay for anything.

A window closes when any of these happen, whichever comes first:

  1. the speaker stopped talking          (UtteranceEnd from Deepgram)
  2. WINDOW_MAX_SENTENCES phrases         (they are mid-flow, take what we have)
  3. WINDOW_SILENCE_MS of quiet           (a pause, even without UtteranceEnd)
  4. WINDOW_MAX_MS since it began         (someone is monologuing, cut in)

Rules 1 and 3 do the work in normal speech; 2 and 4 stop a fast talker from
delaying every verdict.

The subtlety is that rules 1 and 3 are gated. **The signal that a sound
stopped is not the signal that a thought finished.** People pause inside
sentences constantly. So a pause only closes a window that sounds finished,
which we detect with a free textual proxy: terminal punctuation, which
smart_format gives us at no cost.

No network, no Claude, driven by an injectable clock -- which is why every
rule here is tested without speaking or spending anything.
"""

from __future__ import annotations

import time
from dataclasses import dataclass, field
from typing import Callable

from . import config


@dataclass
class Segment:
    """One finished phrase from Deepgram."""

    segment_id: str
    text: str


@dataclass
class Window:
    """A group of phrases, ready to be examined for claims."""

    window_id: str
    segments: list[Segment]
    reason: str          # which rule closed it; invaluable when tuning
    context: str = ""    # the previous window, for resolving "it" and "they"
    # True when the PREVIOUS window was cut off mid-sentence, so this one is
    # the rest of that thought rather than a new one. Without this, the tail
    # of a split sentence looks like three stray words and gets dropped.
    continues_previous: bool = False

    @property
    def text(self) -> str:
        return " ".join(s.text for s in self.segments).strip()

    @property
    def segment_ids(self) -> list[str]:
        return [s.segment_id for s in self.segments]


@dataclass
class Chunker:
    """Collects segments and calls `on_window` when a window closes.

    `now` is injectable so tests drive time forward instantly rather than
    actually sleeping.
    """

    on_window: Callable[[Window], None]
    now: Callable[[], float] = time.monotonic

    pending: list[Segment] = field(default_factory=list)
    started_at: float | None = None
    last_activity: float = 0.0
    last_window_text: str = ""
    last_was_fragment: bool = False
    _count: int = 0

    # --- inputs -------------------------------------------------------------

    def add_segment(self, segment_id: str, text: str) -> None:
        text = text.strip()
        if not text:
            return

        if not self.pending:
            self.started_at = self.now()

        self.pending.append(Segment(segment_id, text))
        self.last_activity = self.now()

        # Prefer a whole sentence. Closing on a phrase count alone cuts
        # sentences in half, and the orphaned tail is usually too small to be
        # a claim, so the claim is lost rather than merely split.
        if len(self.pending) >= config.WINDOW_HARD_MAX_SENTENCES:
            self.close("max_sentences")
        elif len(self.pending) >= config.WINDOW_MAX_SENTENCES:
            self.maybe_close("max_sentences")

    def utterance_end(self) -> None:
        """Deepgram says the speaker stopped. The strongest signal we get, but
        still not enough on its own."""
        self.maybe_close("utterance_end")

    def tick(self) -> None:
        """Called on a timer. Handles the rules that are about time passing
        rather than about something arriving -- nothing else would ever fire
        them."""
        if not self.pending:
            return

        now = self.now()
        quiet_ms = (now - self.last_activity) * 1000

        if quiet_ms >= config.WINDOW_HARD_SILENCE_MS:
            # They really have stopped. Take whatever we have, however small,
            # or those words sit there forever.
            self.close("hard_silence")
            return

        if quiet_ms >= config.WINDOW_SILENCE_MS:
            self.maybe_close("silence")
            return

        if self.started_at is not None and (now - self.started_at) * 1000 >= config.WINDOW_MAX_MS:
            self.close("max_duration")

    def flush(self) -> None:
        """Close whatever is pending, e.g. when listening stops."""
        if self.pending:
            self.close("flush")

    # --- is it actually a thought yet? --------------------------------------

    @property
    def pending_text(self) -> str:
        return " ".join(s.text for s in self.pending).strip()

    def is_closeable(self) -> bool:
        """Does the thought sound finished, or is the speaker mid-sentence?

        Recorded live from the previous build: "Yeah. I have good experience,
        you know, working" closed on a pause, and "across cross functional
        teams and leading them to success." became the next window. Neither
        half is a claim, so an obvious pile of buzzwords went unflagged.

        So a pause only closes a window whose text ends in . ? or ! and has
        enough words to be a sentence -- with an escape hatch for speech that
        never gets punctuated at all, or we would wait forever.

        The word minimum is waived when this window is the tail of a sentence
        the previous one cut in half. "cross functional synergy." is three
        words, which is under the minimum, but the thought genuinely is
        finished -- the front of it is simply in the window before. Without
        this waiver the tail cannot close on a pause at all and sits on screen
        for another four seconds waiting for hard silence.
        """
        text = self.pending_text
        words = len(text.split())

        if text.endswith((".", "?", "!")):
            if self.last_was_fragment:
                return True
            return words >= config.WINDOW_MIN_SENTENCE_WORDS

        return words >= config.WINDOW_MAX_WORDS_UNPUNCTUATED

    def maybe_close(self, reason: str) -> None:
        """Close on a pause, but only if the thought looks finished."""
        if self.pending and self.is_closeable():
            self.close(reason)

    # --- output -------------------------------------------------------------

    def close(self, reason: str) -> None:
        self._count += 1
        window = Window(
            window_id=f"w{self._count}",
            segments=self.pending,
            reason=reason,
            context=self.last_window_text,
            continues_previous=self.last_was_fragment,
        )
        self.pending = []
        self.started_at = None
        self.last_window_text = window.text
        # Only hard_silence and max_duration can cut a sentence in half, and
        # when they do the next window is the rest of that sentence.
        self.last_was_fragment = not window.text.endswith((".", "?", "!"))
        self.on_window(window)
