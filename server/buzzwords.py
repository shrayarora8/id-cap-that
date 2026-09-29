"""WORD SALAD without asking a model.

Every Groq model tested misses pure corporate buzzwords. The 20b misses them,
and so does the 120b, which is six times larger -- so this is not a question of
model size, and throwing a bigger model at it does not fix it. Haiku catches
them, but paying Anthropic for a closed vocabulary of about forty words is
absurd when a set membership test does the same job in microseconds.

The rule is deliberately narrow, because a false positive here is expensive:
it would stamp WORD SALAD on a real claim and skip checking it entirely.

So this only ever runs when the model returned NOTHING AT ALL. It can promote
silence into a verdict. It can never overrule a claim the model actually found,
which means it cannot cost us a check.

Three conditions, all required:
  * at least two distinct buzzwords, so one stray "leverage" is not enough
  * no digits, because a number is something evidence could settle
  * no long capitalised run, because "Snowflake raised at a $10bn valuation"
    is a checkable claim wearing buzzword clothes

A model that catches these anyway is unaffected -- it never gets here.
"""

from __future__ import annotations

import re

# Phrases first: multi-word ones are checked before single words so that
# "core competencies" counts once, as one idea, rather than twice.
PHRASES = (
    "core competenc", "cross functional", "cross-functional", "value add",
    "value-add", "best in class", "best-in-class", "move the needle",
    "circle back", "step change", "north star", "double down", "at scale",
    "low hanging fruit", "low-hanging fruit", "boil the ocean",
    "thought leader", "paradigm shift", "growth hacking", "deep dive",
    "table stakes", "blue sky", "drink the kool", "open the kimono",
    "run it up the flagpole", "take it offline", "touch base",
)

WORDS = frozenset("""
synergy synergies synergistic synergise synergize leverage leveraging
revolutionize revolutionise revolutionary disrupt disruptive disruption
paradigm ecosystem holistic holistically scalable scalability ideate
ideation actionable alignment strategic proactive proactively empower
empowering optimize optimise streamline streamlining transformative
transformation innovate innovative innovation frictionless seamless
bandwidth pivot pivoting granular robust turnkey bleeding-edge
cutting-edge next-generation world-class mission-critical game-changing
unlock unlocking velocity org orgs stakeholder stakeholders
""".split())

MIN_DISTINCT = 2

_WORD_RE = re.compile(r"[a-z][a-z\-]*")
_CAPS_RUN_RE = re.compile(r"\b[A-Z][a-zA-Z]*(?:\s+[A-Z][a-zA-Z]*)+")


def hits(text: str) -> list[str]:
    """Which buzzwords are in here, each counted once."""
    low = (text or "").lower()
    found: list[str] = []
    for phrase in PHRASES:
        if phrase in low:
            found.append(phrase)
            low = low.replace(phrase, " ")   # so its words do not count again
    found.extend({w for w in _WORD_RE.findall(low) if w in WORDS})
    return found


def is_word_salad(text: str) -> bool:
    """Is this corporate noise that no evidence could ever settle?"""
    text = (text or "").strip()
    if not text:
        return False

    # A number means something measurable was asserted. Check it, do not
    # stamp it: "we cut latency by 40%" is a claim, buzzwords or not.
    if any(ch.isdigit() for ch in text):
        return False

    # A run of capitals is a named thing, and a claim about a named thing is
    # checkable however it is dressed up. "Snowflake is revolutionising the
    # data ecosystem" must still reach the judge.
    if _CAPS_RUN_RE.search(text):
        return False

    return len(set(hits(text))) >= MIN_DISTINCT
