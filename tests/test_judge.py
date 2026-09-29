"""The guard rails. The most valuable tests in the repo: each one is a bug
that shipped, and together they are the difference between "an AI said so"
and "here is the sentence on the page that says so".

All pure, all free, no API calls.
"""

from __future__ import annotations

import pytest

from server.judge import (
    Citation, Judgement, apply_guard_rails, compare_values, confidence_from,
    evidence_is_about_the_claim, evidence_names_everyone_in_the_claim, looks_like_a_year,
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
    result, notes = apply_guard_rails(j, evidence, "Notion Business costs five hundred dollars per seat per month.")
    assert result.verdict == "CONTRADICTED"
    assert any(c["code"] == "numbers_mismatch" for c in notes)


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
    assert any(c["code"] == "verdict_unsupported" for c in notes)


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
    result, notes = apply_guard_rails(j, evidence, "The Notion Business plan costs 500 dollars per seat each month.")
    assert result.verdict == "CONTRADICTED"
    assert result.citations and "20 dollars per seat" in result.citations[0].quote
    assert any(c["code"] == "quote_recovered" for c in notes)


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
    result, _ = apply_guard_rails(j, evidence, "The price is five hundred dollars a seat per month.")
    assert result.verdict == "CONTRADICTED", "the verdict is untouched"
    assert result.confidence == "low", "the source quality is reported separately"


def test_confidence_reflects_only_the_sources_actually_cited():
    evidence = [
        ev("E1", "A wikipedia sentence long enough to be a real citation here.", tier=1),
        ev("E2", "A forum post that was retrieved but never cited by the judge.", tier=4),
    ]
    j = judgement(citations=[Citation(evidence_id="E1", quote="A wikipedia sentence long enough")])
    result, _ = apply_guard_rails(j, evidence, "A wikipedia sentence long enough to be a real citation.")
    assert result.confidence == "high"


# --- is the evidence even about the claim? ----------------------------------


def test_a_real_quote_from_an_unrelated_page_is_not_evidence():
    """The bug this pins, seen live. Someone said the fragment "Fifty
    seconds." The sorter made it a claim, the search found a Lisbon
    restaurant called Fifty Seconds, a passage genuinely said "a lift takes
    exactly 50 seconds", the quote verified, and the verdict was NO CAP.

    Every step behaved correctly and the result was nonsense, because nothing
    asked whether the evidence was about the same subject as the claim."""
    evidence = [ev("E1", "Access is via a lift that takes exactly 50 seconds to reach the top, hence the name.",
                   tier=3, url="https://guide.michelin.com/x")]
    j = judgement(
        verdict="SUPPORTED",
        citations=[Citation(evidence_id="E1", quote="a lift that takes exactly 50 seconds to reach the top")],
    )
    result, notes = apply_guard_rails(j, evidence, "The process took fifty seconds.")
    assert result.verdict == "INSUFFICIENT_EVIDENCE"
    assert any(c["code"] == "evidence_off_topic" for c in notes)
    assert result.citations == []


def test_evidence_on_the_same_subject_is_kept():
    evidence = [ev("E1", "Taylor Swift has won 14 Grammy Awards including a record four Album of the Year wins.")]
    j = judgement(
        verdict="CONTRADICTED",
        citations=[Citation(evidence_id="E1", quote="Taylor Swift has won 14 Grammy Awards")],
    )
    result, _ = apply_guard_rails(j, evidence, "Taylor Swift has won 28 Grammy Awards.")
    assert result.verdict == "CONTRADICTED"


def test_a_claim_with_almost_no_distinctive_words_cannot_be_settled():
    """If there is nothing to match on, we cannot show the evidence is
    relevant, so the honest answer is that we do not know."""
    evidence = [ev("E1", "Some passage that happens to contain the word here somewhere.")]
    j = judgement(verdict="SUPPORTED", citations=[Citation(evidence_id="E1", quote="Some passage that happens to contain")])
    result, _ = apply_guard_rails(j, evidence, "It was.")
    assert result.verdict == "INSUFFICIENT_EVIDENCE"


# --- what our own code did, sent to the page --------------------------------


def test_a_clean_verdict_still_reports_that_it_was_checked():
    """The quiet case, and the one a viewer sees most. A field that only
    appears when something went wrong cannot say "we checked and it held
    up" -- which is what makes the loud case mean anything."""
    evidence = [ev("E1", "Taylor Swift has won 14 Grammy Awards including four Album of the Year wins.")]
    j = judgement(
        verdict="CONTRADICTED",
        citations=[Citation(evidence_id="E1", quote="Taylor Swift has won 14 Grammy Awards")],
    )
    _, checks = apply_guard_rails(j, evidence, "Taylor Swift has won 28 Grammy Awards.")
    assert any(c["code"] == "quote_verified" for c in checks)


def test_an_invented_quote_is_reported_as_dropped():
    evidence = [ev("E1", "A passage that says nothing whatsoever about the subject at hand.")]
    j = judgement(verdict="SUPPORTED", citations=[Citation(evidence_id="E1", quote="entirely made up")])
    _, checks = apply_guard_rails(j, evidence, "Some claim about a thing.")
    codes = [c["code"] for c in checks]
    assert "quote_dropped" in codes
    assert "quote_verified" not in codes, "a dropped quote is not a clean check"


def test_every_check_code_is_in_the_contract():
    """The page styles on these codes, so an unknown one renders as nothing."""
    from server import messages

    evidence = [ev("E1", "Notion Business costs twenty dollars per seat per month, billed annually.")]
    j = judgement(
        verdict="SUPPORTED",
        claimed_value="500 dollars",
        evidence_value="20 dollars",
        citations=[Citation(evidence_id="E1", quote="Notion Business costs twenty dollars per seat per month")],
    )
    _, checks = apply_guard_rails(j, evidence, "Notion Business costs five hundred dollars per seat.")
    assert checks
    for c in checks:
        assert c["code"] in messages.CHECK_CODES, f"{c['code']} is not in the contract"
        assert c["note"], "every check needs a human sentence"


def test_checks_are_plain_dicts_the_page_can_render():
    evidence = [ev("E1", "Usain Bolt set the world record of 9.58 seconds in Berlin in 2009.")]
    j = judgement(citations=[Citation(evidence_id="E1", quote="Usain Bolt set the world record of 9.58 seconds")])
    _, checks = apply_guard_rails(j, evidence, "Usain Bolt ran 9.58 seconds.")
    for c in checks:
        assert set(c) == {"code", "note"}


# --- years, precision, and relevance ----------------------------------------


def test_a_year_is_never_within_tolerance_of_another_year():
    """The bug this pins: 1995 and 1991 are 0.2% apart, so a percentage
    tolerance called a four-year error a rounding error. "Python was invented
    in 1995" was reported as AGREEING with a passage that said 1991.

    Percentage tolerance is meaningful for a measurement and meaningless for
    a date."""
    assert compare_values("1995", "1991") == "mismatch"
    assert compare_values("2010", "2007") == "mismatch"
    assert compare_values("1889", "1889") == "match"


def test_quantities_keep_their_tolerance():
    assert compare_values("8848 meters", "8848.86 metres") == "match"
    assert compare_values("45 goals", "45.2 goals") == "match"
    assert compare_values("45 goals", "47 goals") == "mismatch"


def test_the_claims_own_number_does_not_decide_relevance():
    """The bug this pins: a passage that CONTRADICTS a claim cannot contain
    the claim's number -- that is what makes it a contradiction. Counting it
    dragged "Python was invented in 1995" against a Wikipedia passage saying
    1991 to 0.333, just under the threshold, and the correct ABSOLUTE CAP was
    discarded as off-topic."""
    evidence = [ev("E1", "Python was created by Guido van Rossum and first released on February 20, 1991.")]
    assert evidence_is_about_the_claim(
        "Python was invented in 1995.", [Citation(evidence_id="E1", quote="x")], evidence
    )


def test_a_genuinely_unrelated_passage_is_still_rejected():
    """Loosening relevance must not let the Fifty Seconds restaurant back in."""
    evidence = [ev("E1", "Access is via a lift that takes exactly 50 seconds to reach the top.")]
    assert not evidence_is_about_the_claim(
        "Python was invented in 1995.", [Citation(evidence_id="E1", quote="x")], evidence
    )


def test_a_precision_difference_is_not_a_partial_truth():
    """8,848 against 8,848.86 metres is the same mountain stated to fewer
    decimal places. Calling that SOME CAP reads as nitpicking, not checking."""
    evidence = [ev("E1", "Mount Everest is 8,848.86 metres above sea level according to the 2020 survey.")]
    j = judgement(
        verdict="PARTIALLY_SUPPORTED",
        claimed_value="8848 meters",
        evidence_value="8848.86 metres",
        citations=[Citation(evidence_id="E1", quote="Mount Everest is 8,848.86 metres above sea level")],
    )
    result, checks = apply_guard_rails(j, evidence, "Mount Everest is 8,848 meters tall", shape="count")
    assert result.verdict == "SUPPORTED"
    assert sum(1 for c in checks if c["code"] == "numbers_match") == 1, "one fact, stated once"


def test_identical_numbers_never_upgrade_a_partial_verdict():
    """If the values agree exactly and the judge still said partially
    supported, the disagreement is about the year or the scope or the person,
    and that judgement must be left alone."""
    evidence = [ev("E1", "Messi scored 45 goals during the 2023 season for his club side.")]
    j = judgement(
        verdict="PARTIALLY_SUPPORTED",
        claimed_value="45 goals",
        evidence_value="45 goals",
        citations=[Citation(evidence_id="E1", quote="Messi scored 45 goals during the 2023 season")],
    )
    result, _ = apply_guard_rails(j, evidence, "Messi scored 45 goals in 2024", shape="count")
    assert result.verdict == "PARTIALLY_SUPPORTED"


def test_a_passage_is_relevant_when_it_names_the_subject():
    """The bug this pins: a real Wikipedia passage about Everest was rejected
    as off-topic because it wrote "metres", never repeated "Mount Everest" in
    the sentence, and a ratio of shared words therefore scored near zero.

    The name of the thing is a far stronger signal than how much vocabulary a
    claim happens to share with a page, and one hit is enough."""
    evidence = [ev("E1", "The official measurement announced by China and Nepal in December 2020 is 8,848.86 metres.")]
    evidence[0].title = "Mount Everest"
    assert evidence_is_about_the_claim(
        "Mount Everest is 8,848 meters tall",
        [Citation(evidence_id="E1", quote="x")],
        evidence,
    )


def test_a_nameless_claim_cannot_be_rescued_by_a_matching_title():
    """Loosening relevance must not let the Fifty Seconds restaurant back in.
    A title is a good place to find a name and a bad place to match generic
    words -- the restaurant is literally called Fifty Seconds."""
    evidence = [ev("E1", "Access is via a lift that takes exactly 50 seconds to reach the top.")]
    evidence[0].title = "Fifty Seconds restaurant"
    assert not evidence_is_about_the_claim(
        "The process took fifty seconds.",
        [Citation(evidence_id="E1", quote="x")],
        evidence,
    )


def test_refuting_evidence_need_not_contain_the_wrong_entity():
    """The bug this pins. "The Great Barrier Reef is off the coast of New
    Zealand" was answered by a passage saying Queensland, Australia. New
    Zealand appears nowhere in it -- because New Zealand is the error. The
    entity rail fired and a correct ABSOLUTE CAP became COULD BE CAP, on a
    card that already said "not New Zealand" in its own summary.

    Evidence that refutes a claim cannot contain the wrong part of it."""
    evidence = [ev("E1", "The Great Barrier Reef is located off the coast of Queensland, Australia.")]
    j = judgement(
        verdict="CONTRADICTED",
        citations=[Citation(evidence_id="E1", quote="The Great Barrier Reef is located off the coast of Queensland")],
    )
    result, _ = apply_guard_rails(
        j, evidence, "The Great Barrier Reef is off the coast of New Zealand.", shape="other"
    )
    assert result.verdict == "CONTRADICTED"


def test_confirming_evidence_still_needs_every_name():
    """The case the rail was built for must still be caught: a Zendaya
    article must not satisfy a claim about Taylor Swift."""
    evidence = [ev("E1", "Zendaya and Tom Holland confirmed they are in a romantic relationship.")]
    j = judgement(
        verdict="SUPPORTED",
        citations=[Citation(evidence_id="E1", quote="Zendaya and Tom Holland confirmed they are in a romantic relationship")],
    )
    result, notes = apply_guard_rails(j, evidence, "Taylor Swift dated Tom Holland.", shape="other")
    assert result.verdict == "INSUFFICIENT_EVIDENCE"
    assert any(c["code"] == "entities_missing" for c in notes)


# --- names written with punctuation ----------------------------------------


def test_a_hyphen_in_the_source_does_not_destroy_a_correct_verdict():
    """The bug this pins, found on a live claim. Wikipedia's opening sentence
    about Cristiano Ronaldo says he "captains the Saudi Pro League club
    Al-Nassr". The claim said "Al Nassr". The judge read it correctly -- its
    own summary quoted the sentence -- and this rail threw the verdict away
    over one character.

    Quote verification had been forgiving of typography since the first build
    via PUNCTUATION_EQUIVALENTS; the entity check never was. The same hole was
    open for Coca-Cola, Rolls-Royce and McDonald's."""
    real = (
        "Cristiano Ronaldo dos Santos Aveiro (born 5 February 1985) is a Portuguese "
        "professional footballer who plays as a forward for and captains the Saudi "
        "Pro League club Al-Nassr and the Portugal national team."
    )
    assert evidence_names_everyone_in_the_claim(
        "Cristiano Ronaldo plays for Al Nassr",
        [Citation(evidence_id="E1", quote="x")],
        [ev("E1", real)],
    )


def test_name_matching_is_forgiving_but_relevance_is_not():
    """Flattening punctuation must not reopen the Zendaya hole: a claim about
    two named people still needs both of them on the page."""
    evidence = [ev("E1", "Zendaya and Tom Holland confirmed their relationship in 2021.")]
    assert not evidence_names_everyone_in_the_claim(
        "Taylor Swift dated Tom Holland",
        [Citation(evidence_id="E1", quote="x")],
        evidence,
    )


def test_a_verbatim_quote_is_still_checked_strictly():
    """_flatten_name is deliberately separate from _normalise. A name may be
    matched loosely; a quote may not -- verbatim means verbatim."""
    evidence = [ev("E1", "The Business plan costs twenty dollars per seat per month.")]
    j = judgement(
        verdict="SUPPORTED",
        citations=[Citation(evidence_id="E1", quote="The Business plan costs ONE MILLION dollars")],
    )
    good, bad = verify_citations(j, evidence)
    assert not good and len(bad) == 1
