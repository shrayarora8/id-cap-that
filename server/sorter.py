"""The first Claude call: what did they actually claim?

In goes a window of speech, plus the window before it for context. Out comes a
list of claims, each one classified, decontextualised, repaired, and given a
search query.

The naive design is a pipeline -- one call to find claims, another to classify
each, another to write queries. That is three round trips and three chances
for the model to disagree with itself. Instead `Claim` is a single schema with
nine fields and the structured-output API forces all nine to be filled at
once, in about 1.3 seconds.

It never decides whether a claim is true. That is the judge's job, and only
after evidence has been fetched.
"""

from __future__ import annotations

import datetime as dt
import logging
from typing import Literal

from pydantic import BaseModel, Field

from . import config, llm

log = logging.getLogger(__name__)

ClaimKind = Literal["world_fact", "opinion", "prediction", "fluff", "vague"]
Hedge = Literal["stated", "asked", "hedged"]
# What kind of question the claim really asks. It decides what evidence would
# settle it: a count needs a number, a comparison needs a ranking.
Shape = Literal["count", "event", "comparison", "other"]


class Claim(BaseModel):
    quote: str = Field(
        description=(
            "The exact words from the transcript this claim came from, copied "
            "verbatim, character for character. Used to underline them on screen."
        )
    )
    normalized: str = Field(
        description=(
            "The claim rewritten so it stands alone without the conversation: "
            "pronouns resolved, garbled names repaired, relative time made explicit."
        )
    )
    kind: ClaimKind
    hedge: Hedge = Field(
        description="stated = asserted as fact; asked = a question; hedged = 'I think', 'maybe'"
    )
    checkable: bool = Field(
        description="True only if evidence could settle it. Opinions, predictions and buzzwords are false."
    )
    shape: Shape = Field(
        default="other",
        description=(
            "count = asserts a quantity ('45 goals', '$500 a month'). "
            "event = asserts something happened ('won the 2025 title'). "
            "comparison = ranks against others ('the most', 'more than anyone', "
            "'the best', 'the first'). other = anything else."
        ),
    )
    search_query: str = Field(
        default="",
        description="What to type into a search engine. Empty when not checkable.",
    )
    official_domain: str = Field(
        default="",
        description=(
            "If the claim is about a company, product, league, team or "
            "organisation with an official website, the bare domain, e.g. "
            "'notion.com'. Empty when no single organisation owns the fact."
        ),
    )
    note: str = Field(
        default="",
        description="One short phrase explaining an unfalsifiable claim, e.g. 'pure buzzwords'.",
    )


class SorterResult(BaseModel):
    claims: list[Claim]


SYSTEM = """You extract factual claims from a live transcript of people talking.

The transcript comes from speech recognition, so it contains mistakes: garbled \
proper nouns ("Balong d'Or" for "Ballon d'Or", "Fire crawl" for "Firecrawl"), \
missing punctuation, and false starts. Repair names using context and general \
knowledge when writing the normalized claim, but NEVER change the `quote` field.

For each claim you find:

- `quote`: copy the exact words from the transcript, verbatim. This is matched \
character-for-character against the transcript to underline it on screen, so it \
must appear in the window text exactly as written. Copy the smallest span that \
contains the claim.
- `normalized`: rewrite so it stands alone. Resolve pronouns using the previous \
window. Make relative time explicit using today's date. Repair garbled names.
- `kind`:
  - world_fact: about the outside world and checkable against sources
  - opinion: a value judgement ("our UI is beautiful")
  - prediction: about the future ("we'll 10x next year")
  - fluff: corporate buzzwords with no testable content
  - vague: too imprecise to check ("customers love us")
- `hedge`: stated, asked (a question), or hedged ("I think", "maybe")
- `checkable`: true only for world_fact. Questions and hedged claims about facts \
are still checkable; uncertainty about who said it does not make the fact unknowable.
- `shape`: what kind of question this is. This decides what evidence could \
settle it, so get it right.
- `search_query`: what you would type into a search engine to settle it. Include \
entity names and the time period. Empty string when not checkable.
  For a `comparison` claim, search for the RANKING, not for the subject. A page \
about Lewis Hamilton cannot settle "who has the most championships"; a list of \
drivers by championships can. So write "F1 drivers with most world championships \
list", not "Lewis Hamilton championships".
- `note`: for fluff, opinion, prediction and vague, one short phrase saying why.
- `official_domain`: the website of whoever owns this fact. A company's prices \
live on its own site; a league's results live on the league's site. Bare domain \
only, and empty if no single organisation owns the answer.

Rules:
- Split compound sentences into separate claims: "Retention is 94% and NPS is 60" \
is two claims.
- Ignore small talk, filler and incomplete fragments entirely.
- If the window contains no claims of any kind, return an empty list.
- Do not invent claims that were not said.
- Never judge whether a claim is true. Another system does that with evidence."""


def build_prompt(window_text: str, context: str) -> str:
    today = dt.date.today().isoformat()
    previous = context or "(nothing said before this)"
    return (
        f"Today's date: {today}\n\n"
        f"Previous window (context only, do not extract claims from it):\n{previous}\n\n"
        f"Current window (extract claims from this):\n{window_text}"
    )


async def find_claims(window_text: str, context: str = "") -> list[Claim]:
    result = await llm.ask(
        model=config.SORTER_MODEL,
        system=SYSTEM,
        user=build_prompt(window_text, context),
        schema=SorterResult,
        max_tokens=1500,
    )
    log.info("sorter: %d claim(s) in %r", len(result.claims), window_text[:60])
    return result.claims
