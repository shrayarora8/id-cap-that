"""Finding where a claim lives in the transcript, so it can be highlighted.

Claude reads a whole window and tells us which exact words it turned into a
claim. To underline those words we need to know which phrase they were in and
at what character offsets, because the page draws one span per phrase.

Window text is the phrases joined with single spaces, so an offset in the
window maps back to a phrase with simple arithmetic.
"""

from __future__ import annotations

import re
from typing import Any, Sequence

from .chunker import Segment


def _normalise(text: str) -> str:
    return re.sub(r"\s+", " ", text).strip()


def locate(segments: Sequence[Segment], claim_text: str) -> list[dict[str, Any]]:
    """Map a claim back to (segment_id, start, end) spans.

    A claim can straddle two phrases, so it contributes one span to each
    phrase it touches. Returns an empty list when the text cannot be found,
    which happens when Claude paraphrased instead of copying; the caller then
    falls back to highlighting the whole window rather than the wrong words.
    """
    needle = _normalise(claim_text)
    if not needle:
        return []

    window_text = " ".join(s.text for s in segments)

    start = window_text.find(needle)
    if start < 0:
        start = window_text.lower().find(needle.lower())
    if start < 0:
        return []

    end = start + len(needle)

    spans: list[dict[str, Any]] = []
    cursor = 0
    for segment in segments:
        seg_start = cursor
        seg_end = cursor + len(segment.text)
        cursor = seg_end + 1  # the joining space

        overlap_start = max(start, seg_start)
        overlap_end = min(end, seg_end)
        if overlap_start < overlap_end:
            spans.append({
                "segment_id": segment.segment_id,
                "start": overlap_start - seg_start,
                "end": overlap_end - seg_start,
            })

    return spans
