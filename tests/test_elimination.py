"""Refuting a claim by elimination -- only where elimination is sound.

"Holland is married to Zendaya" refutes "Tom Holland and Taylor Swift are
dating" even though Taylor Swift is never mentioned: a current spouse is a
one-at-a-time fact. "Tesla was founded by Eberhard and Tarpenning" does NOT
refute "Tesla was co-founded by JB Straubel": companies have several
founders, and Straubel is one. The judge got the second wrong twice, with
the prompt telling it not to. This rail is the rule; the prompt is advice.
"""

from server.judge import Citation, Judgement, apply_guard_rails
from server.retrieval import Evidence


def judged(claim: str, passage: str, quote: str, verdict: str = "CONTRADICTED"):
    evidence = [Evidence(evidence_id="E1", text=passage, title="Source",
                         url="https://en.wikipedia.org/wiki/Source", tier=1)]
    j = Judgement(verdict=verdict, summary="s",
                  citations=[Citation(evidence_id="E1", quote=quote)])
    return apply_guard_rails(j, evidence, claim)


def test_a_one_at_a_time_fact_may_be_refuted_by_elimination():
    passage = "Holland is married to Zendaya, his co-star in the Spider-Man films."
    j, checks = judged("Tom Holland and Taylor Swift are dating.", passage, passage)
    assert j.verdict == "CONTRADICTED"
    assert "exclusive_assumed" not in [c["code"] for c in checks]


def test_naming_some_founders_does_not_rule_out_another():
    passage = "Tesla was founded in July 2003 by Martin Eberhard and Marc Tarpenning."
    j, checks = judged("Tesla was co-founded by JB Straubel.", passage, passage)
    assert j.verdict == "INSUFFICIENT_EVIDENCE"
    assert "exclusive_assumed" in [c["code"] for c in checks]


def test_a_passage_that_names_the_person_can_still_refute_it():
    # Nothing is assumed when the passage addresses the claimed name itself.
    passage = "Elon Musk is not considered one of Tesla's founders by the company."
    j, _ = judged("Elon Musk founded Tesla.", passage, passage)
    assert j.verdict == "CONTRADICTED"


def test_past_relationships_are_not_one_at_a_time():
    passage = "Holland is married to Zendaya, his co-star in the Spider-Man films."
    j, checks = judged("Tom Holland once dated Taylor Swift.", passage, passage)
    assert j.verdict == "INSUFFICIENT_EVIDENCE"
    assert "exclusive_assumed" in [c["code"] for c in checks]


def test_the_rail_never_touches_a_supported_verdict():
    passage = "Holland is married to Zendaya, his co-star in the Spider-Man films."
    j, _ = judged("Tom Holland is married to Zendaya.", passage, passage, verdict="SUPPORTED")
    assert j.verdict == "SUPPORTED"
