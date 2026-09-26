"""The guard rails. The most valuable tests in the repo: each one is a bug
that shipped, and together they are the difference between "an AI said so"
and "here is the sentence on the page that says so".

All pure, all free, no API calls.
"""

from __future__ import annotations

import pytest

from server.judge import (
    Citation, Judgement, apply_guard_rails, compare_values, confidence_from,
    find_sentence_by_overlap, find_supporting_sentence, first_number,
    longest_verbatim_prefix, verify_citations,
)
from server.retrieval import Evidence


def ev(eid, text, tier=1, url="https://en.wikipedia.org/x"):
    return Evidence(evidence_id=eid, text=text, url=url, title="t", tier=tier)


def judgement(**kw):
    kw.setdefault("summary", "s")
    kw.setdefault("verdict", "SUPPORTED")
    return Judgement(**kw)


# --- verbatim quotes --------------------------------------------------------


def test_a_real_quote_survives():
    evidence = [ev("E1", "Messi scored 38 goals in the 2025 season for Inter Miami.")]
    j = judgement(citations=[Citation(evidence_id="E1", quote="Messi scored 38 goals")])
    good, bad = verify_citations(j, evidence)
    assert len(good) == 1 and not bad


def test_an_invented_quote_is_rejected():
    evidence = [ev("E1", "Messi scored 38 goals in the 2025 season.")]
    j = judgement(citations=[Citation(evidence_id="E1", quote="Messi scored 45 goals")])
    good, bad = verify_citations(j, evidence)
    assert not good and len(bad) == 1


def test_a_quote_against_a_passage_that_does_not_exist_is_rejected():
    j = judgement(citations=[Citation(evidence_id="E9", quote="anything at all")])
    good, bad = verify_citations(j, [ev("E1", "some text")])
    assert not good and len(bad) == 1


def test_curly_apostrophes_do_not_fail_a_real_quote():
    """The bug this pins: Wikipedia writes Drivers' Championship with U+2019,
    the model retypes it straight, and a character-by-character check rejects
    a quote that is genuinely on the page. Correct verdicts were being
    downgraded by a false alarm."""
    evidence = [ev("E1", "He won the Drivers’ Championship in 2025 with a record points total.")]
    j = judgement(citations=[Citation(evidence_id="E1", quote="He won the Drivers' Championship in 2025")])
    good, bad = verify_citations(j, evidence)
    assert len(good) == 1 and not bad


def test_en_dashes_and_non_breaking_spaces_are_also_forgiven():
    evidence = [ev("E1", "The 2025–2026 season was his best yet by a clear margin.")]
    j = judgement(citations=[Citation(evidence_id="E1", quote="The 2025-2026 season was his best yet")])
    good, _ = verify_citations(j, evidence)
    assert len(good) == 1


def test_a_mistyped_ending_is_trimmed_to_the_part_really_there():
    passage = "Notion Business costs twenty dollars per seat per month billed annually."
    trimmed = longest_verbatim_prefix(
        "Notion Business costs twenty dollars per seat per month billed yearly", passage.lower()
    )
    assert trimmed == "Notion Business costs twenty dollars per seat per month billed"


def test_a_wholly_invented_quote_is_never_rescued_by_trimming():
    """The rescues must never manufacture a citation out of nothing."""
    assert longest_verbatim_prefix(
        "Something entirely fabricated that is nowhere on this page at all",
        "completely different text about another subject".lower(),
    ) is None


def test_a_short_fragment_is_not_a_quote():
    """Trimming down to three words would 'verify' almost anything."""
    assert longest_verbatim_prefix("Messi scored 38 goals here", "messi scored 38 goals here") is None


# --- numbers ----------------------------------------------------------------


@pytest.mark.parametrize("text,expected", [
    ("45 goals", 45),
    ("$500 per user per month", 500),
    ("about five championships", 5),
    ("approximately 20 dollars", 20),
    ("~7 titles", 7),
    ("1,200 employees", 1200),
    ("45.2 goals", 45.2),
    ("", None),
    ("no numbers here", None),
])
def test_first_number_reads_the_leading_quantity(text, expected):
    assert first_number(text) == expected


def test_formula_one_is_not_the_number_one():
    """The bug this pins: scanning the whole string for any number found the
    'One' in 'most Formula One championships', compared 1 against 7, and
    turned a tie into a confident contradiction. A guard rail that fires on a
    false positive is worse than no guard rail."""
    assert first_number("most Formula One championships of any driver") is None


def test_rounding_is_a_match_and_a_real_gap_is_not():
    assert compare_values("45 goals", "45.2 goals") == "match"
    assert compare_values("45 goals", "38 goals") == "mismatch"
    assert compare_values("$500 per seat", "$20 per seat") == "mismatch"


def test_hedging_does_not_make_a_number_approximate():
    """'About five' against four is CONTRADICTED. Hedging is about the
    speaker, not about the world."""
    assert compare_values("about five", "four") == "mismatch"


def test_nothing_to_compare_returns_none():
    assert compare_values("the best team", "a great team") is None
    assert compare_values("", "45") is None


def test_a_number_mismatch_forces_a_contradiction():
    evidence = [ev("E1", "Notion Business costs twenty dollars per seat per month, billed annually.")]
    j = judgement(
        verdict="SUPPORTED",
        claimed_value="500 dollars per seat per month",
        evidence_value="20 dollars per seat per month",
        citations=[Citation(evidence_id="E1", quote="Notion Business costs twenty dollars per seat per month")],
    )
    result, notes = apply_guard_rails(j, evidence)
    assert result.verdict == "CONTRADICTED"
    assert any("real" in n for n in notes)


def test_the_comparison_never_upgrades_a_verdict():
    """Deliberately one-directional. 'Verstappen won in 2025' against 'Norris
    won in 2025' matches on the year while being flatly wrong about the
    person. Upgrading on a match turned a correct ABSOLUTE CAP into NO CAP."""
    evidence = [ev("E1", "Lando Norris was crowned champion in 2025 after a dramatic final race.")]
    j = judgement(
        verdict="CONTRADICTED",
        claimed_value="2025",
        evidence_value="2025",
        citations=[Citation(evidence_id="E1", quote="Lando Norris was crowned champion in 2025")],
    )
    result, _ = apply_guard_rails(j, evidence)
    assert result.verdict == "CONTRADICTED", "a matching number must never upgrade"


# --- the verdict cannot stand without a quote -------------------------------


def test_a_verdict_with_no_verifiable_quote_is_downgraded():
    evidence = [ev("E1", "Some text that says nothing about the claim in question.")]
    j = judgement(verdict="SUPPORTED", citations=[Citation(evidence_id="E1", quote="totally invented")])
    result, notes = apply_guard_rails(j, evidence)
    assert result.verdict == "INSUFFICIENT_EVIDENCE"
    assert any("cannot stand" in n for n in notes)


def test_insufficient_evidence_needs_no_quote():
    j = judgement(verdict="INSUFFICIENT_EVIDENCE", citations=[])
    result, _ = apply_guard_rails(j, [ev("E1", "unrelated")])
    assert result.verdict == "INSUFFICIENT_EVIDENCE"


def test_a_paraphrased_quote_is_recovered_from_the_passage():
    """The model got the fact right and retyped the sentence. Rather than
    throwing away a correct verdict, find the sentence stating that value."""
    evidence = [ev("E1", "The Business plan is priced at 20 dollars per seat each month for teams.")]
    j = judgement(
        verdict="CONTRADICTED",
        evidence_value="20 dollars",
        citations=[Citation(evidence_id="E1", quote="Business costs $20 a seat monthly")],
    )
    result, notes = apply_guard_rails(j, evidence)
    assert result.verdict == "CONTRADICTED"
    assert result.citations and "20 dollars per seat" in result.citations[0].quote
    assert any("recovered" in n for n in notes)


def test_the_numeric_rescue_refuses_to_invent():
    assert find_supporting_sentence("45 goals", [ev("E1", "Nothing about any quantity at all here.")]) is None


def test_the_overlap_rescue_finds_a_non_numeric_sentence():
    evidence = [ev("E1", "Lando Norris was crowned world champion in 2025 after the final race in Abu Dhabi.")]
    found = find_sentence_by_overlap("Lando Norris was crowned world champion in 2025", evidence)
    assert found is not None and "Norris" in found.quote


def test_the_overlap_rescue_refuses_a_weak_match():
    evidence = [ev("E1", "An entirely unrelated sentence about completely different subject matter.")]
    assert find_sentence_by_overlap("Messi scored 45 goals last season", evidence) is None


# --- trust is a separate axis -----------------------------------------------


def test_confidence_comes_from_the_best_cited_tier():
    assert confidence_from([1]) == "high"
    assert confidence_from([2, 3]) == "high"
    assert confidence_from([3]) == "medium"
    assert confidence_from([4]) == "low"
    assert confidence_from([]) == "none"


def test_a_low_trust_source_does_not_weaken_the_verdict():
    """The bug this pins: a contradiction became a weaker verdict purely
    because the citation sat on a domain that was not in one of our lists.
    What the evidence says and how good the source is are two questions."""
    evidence = [ev("E1", "This forum post claims the price is twenty dollars a seat per month.", tier=4,
                   url="https://reddit.com/r/x")]
    j = judgement(
        verdict="CONTRADICTED",
        citations=[Citation(evidence_id="E1", quote="the price is twenty dollars a seat per month")],
    )
    result, _ = apply_guard_rails(j, evidence)
    assert result.verdict == "CONTRADICTED", "the verdict is untouched"
    assert result.confidence == "low", "the source quality is reported separately"


def test_confidence_reflects_only_the_sources_actually_cited():
    evidence = [
        ev("E1", "A wikipedia sentence long enough to be a real citation here.", tier=1),
        ev("E2", "A forum post that was retrieved but never cited by the judge.", tier=4),
    ]
    j = judgement(citations=[Citation(evidence_id="E1", quote="A wikipedia sentence long enough")])
    result, _ = apply_guard_rails(j, evidence)
    assert result.confidence == "high"
