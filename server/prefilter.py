"""Is this window even worth sending to Claude?

Conversations are mostly not claims. "How's it going", "yeah", "wait, what?",
"I bet." -- none of that can be checked, and each one would otherwise cost an
API call to establish that there was nothing there.

So this runs first, in plain Python, for nothing. It is deliberately
*conservative*: it skips only what is obviously not a claim. Anything it is
unsure about goes to Claude, because a missed claim is worse than a wasted
fifth of a cent.

Nothing here decides whether something is TRUE. It only decides whether a
sentence is the kind of thing that could be checked at all.
"""

from __future__ import annotations

import re

# Words that carry no content on their own. A sentence made only of these
# cannot be a claim about the world.
FILLER = {
    "a", "about", "actually", "after", "ah", "all", "also", "am", "an", "and",
    "any", "anyway", "are", "as", "at", "back", "basically", "be", "because",
    "been", "being", "but", "by", "can", "cool", "could", "did", "do", "does",
    "doing", "done", "dude", "eh", "even", "ever", "for", "from", "get", "go",
    "going", "gonna", "good", "got", "great", "guess", "had", "has", "have",
    "he", "her", "here", "hey", "hi", "him", "his", "hmm", "how", "huh", "i",
    "if", "in", "is", "it", "its", "just", "kind", "know", "let", "like",
    "literally", "lot", "man", "may", "maybe", "me", "mean", "might", "mm",
    "more", "my", "nah", "need", "nice", "no", "not", "now", "of", "off", "oh",
    "ok", "okay", "on", "one", "only", "or", "other", "our", "out", "over",
    "really", "right", "said", "say", "see", "she", "should", "so", "some",
    "something", "sorry", "still", "stuff", "such", "sure", "take", "tell",
    "than", "thanks", "that", "the", "their", "them", "then", "there", "these",
    "they", "thing", "things", "think", "this", "those", "thought", "to",
    "too", "uh", "um", "up", "us", "very", "wait", "want", "was", "way", "we",
    "well", "were", "what", "when", "where", "which", "while", "who", "why",
    "will", "with", "would", "wow", "yeah", "yep", "yes", "yo", "you", "your",
}

# Whole sentences that are pure conversation, matched start to finish against
# the normalised text.
SMALL_TALK = [
    r"(hi|hey|hello|yo|sup|good (morning|afternoon|evening))( \w+)?",
    r"how (are|r) (you|u|things|we)( doing| going)?",
    r"(how('s| is) it going|what('s| is) up|what('s| is) going on)",
    r"(thanks|thank you|cheers|no worries|my bad|never mind)( \w+)?",
    r"(ok|okay|right|sure|cool|nice|great|awesome|damn|wow|really|exactly)",
    r"(yeah|yep|yup|nope|nah|no|yes|true|fair|same)",
    r"(what|huh|sorry|pardon|excuse me)",
    r"(i bet|let('s| us) see|you know what|i mean|hold on|one sec|give me a sec)",
    r"(bye|see (you|ya)|later|good night|take care)",
    r"(this is (yet )?another test|testing|test)( \w+)?",
    r"(bro|dude|man|guys|folks|alright|anyway|whatever)",
]

SMALL_TALK_RE = re.compile(r"^(" + "|".join(SMALL_TALK) + r")[\s\.,!\?]*$", re.IGNORECASE)

# Below this, a window is too thin to contain a checkable statement.
MIN_WORDS = 4


def normalise(text: str) -> str:
    text = text.lower().strip()
    text = re.sub(r"[^\w\s']", " ", text)   # keep apostrophes: "let's", "d'or"
    return re.sub(r"\s+", " ", text).strip()


def worth_checking(text: str, continues_previous: bool = False) -> tuple[bool, str]:
    """Returns (send_it_to_claude, reason).

    The reason is shown on screen and logged, so you can always see why a
    sentence was ignored rather than wondering why nothing happened.

    `continues_previous` means the last window was cut off mid-sentence, so
    this text is the rest of that thought. The length rules must not apply to
    it: "cross functional synergy." is three words and looks like nothing on
    its own, but it is the payload of the sentence before it. Dropping it is
    how a window full of buzzwords goes unflagged.
    """
    cleaned = normalise(text)
    if not cleaned:
        return False, "empty"

    if continues_previous:
        # The sorter is given the previous window as context, so it can see
        # the whole thought even though we only have the tail of it here.
        #
        # But the waiver still needs a floor. With none, "Fifty seconds." went
        # through as a claim, the search found a Lisbon restaurant of that
        # name, and the verdict was a confident NO CAP about a lift. Two
        # content words is the smallest thing that can carry a subject and an
        # assertion between them.
        content = [w for w in cleaned.split() if w not in FILLER]
        if not content:
            return False, "no content words"
        # Three, not two: "Fifty seconds." has two content words and is
        # still a fragment. Three is the smallest thing that reliably carries
        # a subject and something said about it ("cross functional synergy",
        # "costs twenty dollars").
        if len(content) < 3:
            return False, "too short"
        return True, "has content"

    # Judge sentence by sentence: a window is often several of them, and
    # "BRO. What's going on?" is two pieces of small talk rather than one
    # strange claim.
    sentences = [normalise(part) for part in re.split(r"[.!?]+", text)]
    sentences = [s for s in sentences if s]

    def is_chatter(sentence: str) -> bool:
        return bool(SMALL_TALK_RE.match(sentence)) or len(sentence.split()) < MIN_WORDS

    if sentences and all(is_chatter(s) for s in sentences):
        # One real claim anywhere in the window justifies the call, so this
        # only fires when every single sentence is chatter.
        matched = any(SMALL_TALK_RE.match(s) for s in sentences)
        return False, "small talk" if matched else "too short"

    content = [w for w in cleaned.split() if w not in FILLER]
    if not content:
        return False, "no content words"

    return True, "has content"
