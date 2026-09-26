"""The verdict, and the checks that keep it honest.

Claude reads the claim and the passages and returns a verdict plus the exact
quotes it relied on. Then our own code verifies those quotes really appear.

That check is the whole difference between "an AI said so" and "here is the
sentence on the page that says so". A model can produce a confident verdict
supported by a quote it invented; a substring test cannot be fooled by
confidence. A prompt is a request. A substring test and a subtraction are not
negotiable.

The system never claims to know the truth. Every verdict means: according to
the evidence we retrieved.
"""

from __future__ import annotations

import datetime as dt
import logging
import re
from typing import Literal

from pydantic import BaseModel, Field

from . import config, llm
from .retrieval import Evidence

log = logging.getLogger(__name__)

Verdict = Literal[
    "SUPPORTED", "CONTRADICTED", "PARTIALLY_SUPPORTED", "DISPUTED",
    "INSUFFICIENT_EVIDENCE",
]


class Citation(BaseModel):
    evidence_id: str = Field(description="Which passage, e.g. E2")
    quote: str = Field(
        description=(
            "A sentence or fragment copied VERBATIM from that passage. It is "
            "checked character by character against the passage text."
        )
    )


class Judgement(BaseModel):
    verdict: Verdict
    claimed_value: str = Field(
        default="",
        description=(
            "The quantity the claim asserts, if any, as a plain number with its "
            "unit: '500 dollars per user per month', '45 goals'. Empty when the "
            "claim is not about a quantity."
        ),
    )
    evidence_value: str = Field(
        default="",
        description=(
            "The corresponding quantity the passages state, same format. Empty "
            "unless a passage states it outright."
        ),
    )
    summary: str = Field(
        description="One sentence, starting from what the evidence says, not from what you know."
    )
    citations: list[Citation] = Field(default_factory=list)
    correction: str = Field(
        default="",
        description=(
            "If the evidence states a different value than the claim, the correct "
            "value as the evidence gives it, e.g. '38 goals, not 45'. Empty unless "
            "a passage states it outright. Never inferred or remembered."
        ),
    )
    needs_full_pages: bool = Field(
        default=False,
        description=(
            "True if these passages are too thin to settle the claim and reading "
            "the full pages would plausibly help. Set this instead of guessing. "
            "False when the passages settle it, and also false when no amount of "
            "reading would help because the claim is not about these sources."
        ),
    )
    # Filled in by our code afterwards, never by the model.
    confidence: str = "none"


SYSTEM = """You decide what retrieved evidence says about a claim. You are not \
deciding what is true in the world; you are reporting what these passages say.

Rules:
- Use ONLY the passages provided. Ignore anything you know from training.
- Every verdict except INSUFFICIENT_EVIDENCE must cite at least one passage, \
with a quote copied VERBATIM from it. Find the sentence in the passage that \
settles the claim and copy it exactly, word for word, including its wording and \
punctuation. Do NOT rewrite it, summarise it, or compose a sentence that says \
the same thing in better words -- that is the single most common way this fails. \
Quote one sentence or less. Quotes are checked character by character against \
the passage, and a quote that is not found invalidates the verdict.
- Prefer higher-trust passages. Tier 1 is a primary or reference source, tier 2 \
is serious reporting, tier 3 is unknown, tier 4 is a forum or social post.
- Watch the dates. A claim about "last season" must be judged against the right \
season, not any season.
- You MAY read what a passage plainly means. Final standings showing a driver \
first with the most points means he won that championship. A table row \
"Business - $20 per seat/month" means the Business plan costs $20. That is \
reading, not guessing.
- You may NOT compute a quantity out of other quantities. Minutes played divided \
by minutes per goal is not a goal total. If the number you would report exists \
nowhere in the passages, the answer is INSUFFICIENT_EVIDENCE.
- You may NOT stitch two passages together into a conclusion neither of them \
states. "Hamilton has 7 titles" plus "Norris was crowned champion in 2025" does \
NOT tell you who has the most titles: one is a count, the other is an event, and \
nothing ranks them. One passage must contain the answer. If your reasoning \
contains the word "so" or "which means" across two different passages, the \
answer is INSUFFICIENT_EVIDENCE.
- Hedging is about the speaker, not the world. "Approximately five", "I think \
five" and "about five" are all the claim FIVE. If the evidence says four, that \
is CONTRADICTED, not partially supported.

WHEN A NUMBER IS CLOSE ENOUGH. This matters as much as catching a wrong one: a \
verdict that calls someone a liar over a decimal place makes every other \
verdict less believable.
- Stating a number to fewer decimal places is NOT a disagreement. "Mount \
Everest is 8,848 metres" against evidence saying 8,848.86 metres is SUPPORTED. \
Put the exact figure in `correction` if it is worth knowing; do not downgrade \
the verdict for it.
- A figure that WAS official and has since been revised is not a lie. 8,848 \
metres was the accepted height from 1954 until the 2020 survey and is still \
printed everywhere. Someone repeating it is right in every sense that matters: \
SUPPORTED, with the revision noted in `correction`.
- Rounding is normal speech. "About four hundred employees" against 412 is \
SUPPORTED; "a ten billion dollar valuation" against $10.2bn is SUPPORTED.
- The test is whether the difference would change what a listener understood. \
8,848 against 8,848.86 would not. 8,848 against 9,000 would, and that is \
CONTRADICTED.

What counts as enough, by claim shape (given to you with the claim):
- count: a passage must state the quantity.
- event: a passage must state that the thing happened.
- comparison ("the most", "more than anyone", "the best", "the first"): a \
passage must actually RANK them, or say outright that this one holds the record. \
A page about one subject, however detailed, cannot settle who leads. If no \
ranking is present, say INSUFFICIENT_EVIDENCE, even when you are confident you \
know the answer.
- Ties: if the evidence shows the subject is JOINT top, a claim of "the most" is \
PARTIALLY_SUPPORTED. Not CONTRADICTED, because they do lead; not SUPPORTED, \
because they do not lead alone. Say so in the summary.

Verdicts:
- SUPPORTED: the passages state the claim, or state something that plainly \
entails it.
- CONTRADICTED: the passages state something incompatible with the claim.
- PARTIALLY_SUPPORTED: right in part. Correct number but wrong scope, correct \
event but wrong year, one half of a compound claim right and the other wrong.
- DISPUTED: credible passages disagree with EACH OTHER. Not for when you are \
unsure.
- INSUFFICIENT_EVIDENCE: the passages do not address the claim, are too vague, \
or only touch it from low-trust sources. This is the honest default.

`needs_full_pages`: these passages may be short search-result descriptions. If \
they are too thin to settle the claim but the pages behind them would plausibly \
contain the answer, set it true and answer INSUFFICIENT_EVIDENCE for now. Set it \
false when the passages settle the claim, and false when reading further would \
not help because these sources are simply not about the claim.

`correction`: when the evidence states a different value than the claim, give \
that value as the passage words it. Only when a passage says it outright.

`summary`: one sentence, phrased as what the evidence says. Never "I know that"."""


def build_prompt(claim: str, evidence: list[Evidence], shape: str = "other") -> str:
    today = dt.date.today().isoformat()
    blocks = [
        f"[{item.evidence_id}] tier {item.tier} | {item.title or item.url}\n{item.text}"
        for item in evidence
    ]
    passages = "\n\n".join(blocks) if blocks else "(no passages were retrieved)"
    return (
        f"Today's date: {today}\n\n"
        f"Claim shape: {shape}\n"
        f"Claim:\n{claim}\n\n"
        f"Passages:\n{passages}"
    )


# --- the guard rails --------------------------------------------------------

# Typographic characters that mean the same as their plain equivalent. A page
# writes Drivers' Championship with a curly apostrophe; the model retypes it
# straight; a character-by-character check then rejects a quote that is
# genuinely on the page. "Verbatim" is a decision, not a fact: decide which
# differences are meaningless, normalise both sides, stay strict about the rest.
PUNCTUATION_EQUIVALENTS = {
    "‘": "'", "’": "'", "‛": "'", "´": "'", "`": "'",
    "“": '"', "”": '"', "„": '"',
    "–": "-", "—": "-", "−": "-", "‐": "-", "‑": "-",
    " ": " ", "…": "...",
}


def _normalise(text: str) -> str:
    for fancy, plain in PUNCTUATION_EQUIVALENTS.items():
        text = text.replace(fancy, plain)
    return re.sub(r"\s+", " ", text).strip().lower()


MIN_QUOTE_CHARS = 40


def longest_verbatim_prefix(quote: str, passage: str) -> str | None:
    """The longest opening slice of `quote` that is word-for-word in the passage.

    A model that mistypes the last word of an otherwise real sentence has not
    invented anything, so we cite exactly the part that is genuinely there.
    """
    words = quote.split()
    for count in range(len(words), 2, -1):
        candidate = " ".join(words[:count])
        if _normalise(candidate) in passage:
            return candidate if len(candidate) >= MIN_QUOTE_CHARS else None
    return None


def find_sentence_by_overlap(text: str, evidence: list[Evidence]) -> Citation | None:
    """Find the passage sentence that best matches what the model told us.

    The numeric rescue only helps when the disagreement is about a quantity.
    "Norris won it, not Verstappen" has no number in it, so instead look for
    the sentence sharing the most distinctive words, and accept it only when
    the overlap is strong enough to be the same statement.
    """
    from .sources import keywords

    wanted = keywords(text)
    if len(wanted) < 3:
        return None

    best: tuple[float, Citation] | None = None
    for item in evidence:
        for sentence in re.split(r"(?<=[.!?])\s+", item.text):
            if len(sentence.strip()) < MIN_QUOTE_CHARS:
                continue
            overlap = len(wanted & keywords(sentence)) / len(wanted)
            if overlap >= 0.5 and (best is None or overlap > best[0]):
                best = (overlap, Citation(evidence_id=item.evidence_id, quote=sentence.strip()))
    return best[1] if best else None


def find_supporting_sentence(value: str, evidence: list[Evidence]) -> Citation | None:
    """Locate a sentence stating `value` and cite it.

    Deterministic: it searches for the number, in digits or words, and returns
    the real sentence around it, so the citation is still something a person
    can go and check on the page.
    """
    number = first_number(value)
    if number is None:
        return None

    as_digits = f"{number:g}"
    as_word = next((w for w, v in WORD_NUMBERS.items() if v == number), None)

    for item in evidence:
        for sentence in re.split(r"(?<=[.!?])\s+", item.text):
            hay = _normalise(sentence)
            hit = re.search(rf"\b{re.escape(as_digits)}\b", hay)
            if not hit and as_word:
                hit = re.search(rf"\b{as_word}\b", hay)
            if hit and len(sentence.strip()) >= MIN_QUOTE_CHARS:
                return Citation(evidence_id=item.evidence_id, quote=sentence.strip())
    return None


def verify_citations(
    judgement: Judgement, evidence: list[Evidence]
) -> tuple[list[Citation], list[Citation]]:
    """Split citations into those really on the page and those that are not.

    A partial match is trimmed to the part genuinely there, so whatever is
    displayed is always verbatim.
    """
    by_id = {item.evidence_id: _normalise(item.text) for item in evidence}
    good, bad = [], []

    for citation in judgement.citations:
        passage = by_id.get(citation.evidence_id)
        if not passage:
            bad.append(citation)
            continue
        if _normalise(citation.quote) in passage:
            good.append(citation)
            continue
        trimmed = longest_verbatim_prefix(citation.quote, passage)
        if trimmed:
            good.append(Citation(evidence_id=citation.evidence_id, quote=trimmed))
        else:
            bad.append(citation)

    return good, bad


# How much of the claim's own vocabulary must appear in the passage that is
# supposed to settle it.
#
# The bug this exists for: someone said "Fifty seconds." as a fragment. The
# sorter treated it as a claim, the search found a Lisbon restaurant called
# Fifty Seconds, a passage said "a lift takes exactly 50 seconds", and the
# judge returned NO CAP. Every individual step behaved correctly and the
# result was nonsense, because nothing ever asked whether the evidence was
# about the same subject as the claim.
#
# A verdict may only stand on a passage that shares the claim's distinctive
# words. This is cheap, it is in code rather than in the prompt, and it fails
# in the safe direction: the verdict drops to INSUFFICIENT_EVIDENCE.
MIN_SUBJECT_OVERLAP = 0.34

# Multi-word proper nouns: "Taylor Swift", "Inter Miami", "Tom Holland".
NAMED_ENTITY = re.compile(r"\b[A-Z][a-z0-9\u2019']+(?:\s+[A-Z][a-z0-9\u2019']+)+")


def named_entities(text: str) -> set[str]:
    """The multi-word proper nouns a claim is about."""
    return {m.group().strip().lower() for m in NAMED_ENTITY.finditer(text)}


def evidence_names_everyone_in_the_claim(
    claim: str, citations: list[Citation], evidence: list[Evidence]
) -> bool:
    """Does a cited passage mention EVERY named person or thing in the claim?

    The bug this exists for: the claim was "Taylor Swift dated Tom Holland".
    The search found articles about Zendaya dating Tom Holland. Those passages
    genuinely discuss Tom Holland, so the word-overlap check passed -- half
    the claim's vocabulary was present. Nothing ever asked whether Taylor
    Swift appeared anywhere, and the verdict came back NO CAP for a claim
    about a relationship the sources never mention.

    Overlap is not enough when a claim is about a RELATIONSHIP between two
    named things. Both ends have to be on the page.
    """
    wanted = named_entities(claim)
    if len(wanted) < 2:
        # One name or none: the overlap check already covers this, and being
        # stricter would reject a table row that answers without repeating
        # the subject.
        return True

    by_id = {item.evidence_id: item for item in evidence}
    for citation in citations:
        item = by_id.get(citation.evidence_id)
        if not item:
            continue
        haystack = f"{item.title} {item.text}".lower()
        if all(name in haystack for name in wanted):
            return True
    return False


_NOT_A_NAME = {
    "the", "this", "that", "these", "those", "and", "but", "so", "which",
    "they", "it", "we", "you", "he", "she", "there", "here", "what", "when",
    "why", "how", "oh", "yeah", "anyway", "honestly", "sorry", "okay", "hey",
    "did", "right", "also", "now", "just", "actually", "well", "about", "a",
    "an", "in", "on", "at", "of", "for", "is", "was", "are", "his", "her",
    "their", "its", "my", "our", "your",
}


def claim_names(claim: str) -> set[str]:
    """The capitalised words a claim is about, one by one.

    Single words rather than phrases: a page about Mount Everest very often
    says only "Everest", and the name of the thing is a far stronger signal
    than how much vocabulary a claim happens to share with a page.
    """
    return {
        w.lower()
        for w in re.findall(r"\b[A-Z][A-Za-z0-9\u2019']+", claim)
        if w.lower() not in _NOT_A_NAME
    }


def evidence_is_about_the_claim(
    claim: str, citations: list[Citation], evidence: list[Evidence]
) -> bool:
    """Is a cited passage actually about the same thing as the claim?

    The bug this exists for: someone said the fragment "Fifty seconds." The
    search found a Lisbon restaurant of that name, a passage genuinely said
    "a lift takes exactly 50 seconds", the quote verified, and the verdict
    was NO CAP. Every step behaved correctly and the answer was nonsense.

    Two tests, in order of how much they tell us:

      1. If the claim names something, that name must appear in the passage
         or its title. One hit is enough -- a page about Everest does not
         repeat "Mount Everest" in every sentence, and requiring a ratio of
         shared words rejected a perfectly good Wikipedia passage because it
         wrote "metres" and never repeated the mountain's name.
      2. Only when the claim names nothing do we fall back to shared
         vocabulary, which is then all there is.

    Numbers never count. A passage that CONTRADICTS a claim cannot contain
    the claim's number -- that is precisely what makes it a contradiction --
    so counting it punished the case we care most about. "Python was invented
    in 1995" scored 0.333 against a passage saying 1991 and was discarded as
    off-topic, one thousandth below the threshold.
    """
    from .sources import keywords

    by_id = {item.evidence_id: item for item in evidence}
    cited = [by_id[c.evidence_id] for c in citations if c.evidence_id in by_id]
    if not cited:
        return False

    names = claim_names(claim)
    if names:
        return any(
            any(name in f"{item.title} {item.text}".lower() for name in names)
            for item in cited
        )

    wanted = {w for w in keywords(claim) if not any(c.isdigit() for c in w)}
    if len(wanted) < 2:
        return False

    for item in cited:
        # Title deliberately excluded here. A title is a good place to find a
        # NAME and a bad place to match generic words: the Lisbon restaurant
        # is called "Fifty Seconds", so matching a nameless claim against
        # titles lets the exact failure this guard exists for straight back in.
        found = {w for w in keywords(item.text) if not any(c.isdigit() for c in w)}
        if len(wanted & found) / len(wanted) >= MIN_SUBJECT_OVERLAP:
            return True
    return False


NEEDS_CITATION = {"SUPPORTED", "CONTRADICTED", "PARTIALLY_SUPPORTED", "DISPUTED"}

WORD_NUMBERS = {
    "zero": 0, "one": 1, "two": 2, "three": 3, "four": 4, "five": 5, "six": 6,
    "seven": 7, "eight": 8, "nine": 9, "ten": 10, "eleven": 11, "twelve": 12,
    "thirteen": 13, "fourteen": 14, "fifteen": 15, "sixteen": 16,
    "seventeen": 17, "eighteen": 18, "nineteen": 19, "twenty": 20,
}

# How far apart two quantities can be and still be the same claim. Three per
# cent: enough that 8,848 and 8,848.86 metres are the same mountain, tight
# enough that 45 and 47 goals are not the same season.
NUMBER_TOLERANCE = 0.03


def looks_like_a_year(value: float) -> bool:
    """A four-digit whole number in a plausible calendar range.

    Years must be compared exactly, never proportionally. 1995 and 1991 are
    0.2% apart, so any percentage tolerance calls a four-year error a
    rounding error -- which is how "Python was invented in 1995" was reported
    as agreeing with a passage that said 1991. Percentage tolerance is
    meaningful for a measurement and meaningless for a date.
    """
    return value.is_integer() and 1000 <= value <= 2999
# A word qualifier needs a space after it, or "over" would eat the start of
# "overall". The "~" symbol is written flush against its number, so it gets its
# own branch rather than a looser rule that would let word qualifiers match
# inside longer words.
QUALIFIER_PREFIX = (
    r"(?:(?:about|approximately|approx|nearly|roughly|around|almost|over|under|some)\s+|~\s*)"
)


def first_number(text: str) -> float | None:
    """The quantity a value is ABOUT, or None when it is not about a quantity.

    Only the LEADING number counts. Scanning the whole string found the "One"
    in "most Formula One championships", compared 1 against 7, and turned a
    tie into a confident contradiction. A guard rail that fires on a false
    positive is worse than no guard rail, because it overrides a correct
    answer with a wrong one. So parse the grammar of a quantity -- an optional
    qualifier, an optional currency symbol, the number, its unit -- rather
    than scanning for a pattern anywhere in the string.
    """
    if not text:
        return None

    cleaned = re.sub(rf"^\s*{QUALIFIER_PREFIX}", "", text.strip(), flags=re.IGNORECASE)
    cleaned = cleaned.lstrip("$£€")

    digits = re.match(r"-?\d[\d,]*\.?\d*", cleaned)
    if digits:
        try:
            return float(digits.group().replace(",", ""))
        except ValueError:
            return None

    first_word = re.match(r"[a-z]+", cleaned, re.IGNORECASE)
    if first_word:
        value = WORD_NUMBERS.get(first_word.group().lower())
        if value is not None:
            return float(value)
    return None


def compare_values(claimed: str, stated: str) -> str | None:
    """'match', 'mismatch', or None when there is nothing to compare.

    Arithmetic belongs in code. A model has been watched being too lenient
    ("approximately five" against four) and too clever (deriving a goal total
    from minutes played), so the comparison is not left to prompting.
    """
    a, b = first_number(claimed), first_number(stated)
    if a is None or b is None:
        return None
    if a == b:
        return "match"
    if looks_like_a_year(a) and looks_like_a_year(b):
        return "mismatch"
    scale = max(abs(a), abs(b))
    return "match" if abs(a - b) / scale <= NUMBER_TOLERANCE else "mismatch"


def confidence_from(tiers: list[int]) -> str:
    """How much the sources are worth, kept SEPARATE from the verdict.

    Mixing the two produced a real inconsistency: a contradiction became a
    weaker verdict purely because the citation happened to sit on a domain
    that was not in one of our lists. What the evidence says and how good the
    source is are two different questions.
    """
    if not tiers:
        return "none"
    return {1: "high", 2: "high", 3: "medium"}.get(min(tiers), "low")


def apply_guard_rails(
    judgement: Judgement, evidence: list[Evidence], claim_text: str = "",
    shape: str = "other",
) -> tuple[Judgement, list[dict]]:
    """Downgrade anything the evidence does not actually support.

    Returns the judgement and a list of checks: one entry per rail that
    fired, each with a machine-readable code and a human note. They are sent
    to the page as well as logged, because the strongest reason to trust any
    of this -- that a model DID invent a quote and our code caught it -- was
    otherwise invisible to anyone looking at the screen.
    """
    from . import messages

    checks: list[dict] = []

    def note(code: str, text: str) -> None:
        checks.append(messages.check(code, text))

    good, bad = verify_citations(judgement, evidence)

    if bad:
        note("quote_dropped",
             f"{len(bad)} quote(s) were not in the passages and were dropped")
        log.warning("judge invented quotes: %s", [c.quote[:60] for c in bad])

    # A citation that came back shorter than the model wrote it was trimmed
    # to the part genuinely on the page.
    original = {c.evidence_id: c.quote for c in judgement.citations}
    for citation in good:
        was = original.get(citation.evidence_id)
        if was and len(citation.quote) < len(was):
            note("quote_trimmed",
                 "the quote was partly real and was cut down to the part on the page")
            break

    judgement.citations = good

    # Last chance before throwing away a correct verdict: the model often gets
    # the fact right and the transcription wrong. If it told us what value the
    # evidence states, go and find the sentence that states it ourselves.
    if judgement.verdict in NEEDS_CITATION and not good:
        rescued = find_supporting_sentence(
            judgement.evidence_value, evidence
        ) or find_sentence_by_overlap(
            judgement.correction or judgement.summary, evidence
        )
        if rescued:
            note("quote_recovered",
                 "the model retyped its quote, so the real sentence was found in the passage")
            good = [rescued]
            judgement.citations = good

    if judgement.verdict in NEEDS_CITATION and not good:
        note("verdict_unsupported",
             "nothing citable survived, so the verdict could not stand")
        judgement.verdict = "INSUFFICIENT_EVIDENCE"

    # A real quote from a page about something else is not evidence.
    # Skipped when the caller did not say what the claim was: we cannot judge
    # relevance against nothing, and guessing would fail in the unsafe
    # direction. Production always passes it.
    if claim_text and judgement.verdict in NEEDS_CITATION and not evidence_is_about_the_claim(
        claim_text, judgement.citations, evidence
    ):
        note("evidence_off_topic", "the cited passage was not about this claim")
        judgement.verdict = "INSUFFICIENT_EVIDENCE"
        judgement.citations = []

    # A claim about two named things needs both of them on the page.
    if claim_text and judgement.verdict in NEEDS_CITATION and not evidence_names_everyone_in_the_claim(
        claim_text, judgement.citations, evidence
    ):
        missing = ", ".join(sorted(named_entities(claim_text)))
        note("entities_missing", f"no passage mentioned all of: {missing}")
        judgement.verdict = "INSUFFICIENT_EVIDENCE"
        judgement.citations = []

    comparison = compare_values(judgement.claimed_value, judgement.evidence_value)
    if comparison == "mismatch" and judgement.verdict in {"SUPPORTED", "PARTIALLY_SUPPORTED"}:
        note("numbers_mismatch",
             f"{judgement.claimed_value} against {judgement.evidence_value} is a real "
             "difference, not rounding")
        judgement.verdict = "CONTRADICTED"
    elif comparison == "match":
        note("numbers_match",
             f"{judgement.claimed_value} and {judgement.evidence_value} agree")

        # The one upgrade this code will ever make, and it is deliberately
        # narrow. When the two values are DIFFERENT numbers that agree within
        # tolerance, the only disagreement is precision: 8,848 against
        # 8,848.86 metres is the same mountain stated to fewer decimal
        # places, and calling that SOME CAP reads as the tool nitpicking
        # rather than checking.
        #
        # It requires the values to differ. If they are identical and the
        # judge still said partially supported, the disagreement is about
        # something else -- the year, the scope, the person -- and that
        # judgement is left alone.
        a, b = first_number(judgement.claimed_value), first_number(judgement.evidence_value)
        if (
            judgement.verdict == "PARTIALLY_SUPPORTED"
            and shape == "count"
            and a is not None and b is not None and a != b
        ):
            # Replace the plain agreement note rather than adding a second
            # one: one fact about the numbers, stated once.
            checks[-1] = messages.check(
                "numbers_match",
                f"{judgement.claimed_value} and {judgement.evidence_value} are the same "
                "value stated to different precision",
            )
            judgement.verdict = "SUPPORTED"
    # Deliberately one-directional. A mismatch is hard evidence that the claim
    # and the sources disagree. A match proves nothing on its own: "Verstappen
    # won in 2025" against "Norris won in 2025" matches on the year while
    # being flatly wrong about the person. Upgrading on a match turned a
    # correct ABSOLUTE CAP into NO CAP, so we never upgrade.

    # The quiet case, and the one a viewer sees most: nothing was wrong. A
    # field that only appears when something went wrong cannot say "we
    # checked and it held up", which is what makes the loud case mean
    # anything.
    if judgement.citations and not any(
        c["code"] in ("quote_dropped", "quote_trimmed", "quote_recovered") for c in checks
    ):
        checks.insert(0, messages.check(
            "quote_verified",
            "every quote was found word for word in the passage it cites",
        ))

    cited_tiers = [
        item.tier for item in evidence
        if any(c.evidence_id == item.evidence_id for c in judgement.citations)
    ]
    judgement.confidence = confidence_from(cited_tiers)

    return judgement, checks


async def judge_claim(
    claim: str, evidence: list[Evidence], shape: str = "other"
) -> tuple[Judgement, list[dict]]:
    if not evidence:
        return (
            Judgement(
                verdict="INSUFFICIENT_EVIDENCE",
                summary="No sources were found for this one.",
                needs_full_pages=False,
            ),
            [],
        )

    judgement = await llm.ask(
        model=config.JUDGE_MODEL,
        system=SYSTEM,
        user=build_prompt(claim, evidence, shape),
        schema=Judgement,
        max_tokens=700,
    )
    judgement, checks = apply_guard_rails(judgement, evidence, claim, shape)
    log.info(
        "judge: %s (%s)",
        judgement.verdict,
        "; ".join(c["code"] for c in checks) or "clean",
    )
    return judgement, checks
