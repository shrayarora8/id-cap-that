"""Evidence is about a subject, not about a sentence.

The claim cache only hits on identical text, so changing one word threw away
everything we held and paid for the whole pipeline again -- even though the
passages already on disk answered the new claim perfectly well. This is the
job Moss did before it was turned off for billing by the session-minute.
"""

import asyncio

from server.retrieval import (
    Evidence, keep_subject, recall_subject,
)

BOLT = [
    Evidence(evidence_id="E1", tier=1, url="https://en.wikipedia.org/wiki/Usain_Bolt",
             title="Usain Bolt",
             text="Usain Bolt ran the 100 metres in 9.58 seconds in Berlin in 2009, a world record."),
    Evidence(evidence_id="E2", tier=1, url="https://en.wikipedia.org/wiki/Usain_Bolt",
             title="Usain Bolt",
             text="Bolt is a Jamaican retired sprinter, widely considered the greatest of all time."),
    Evidence(evidence_id="E3", tier=1, url="https://en.wikipedia.org/wiki/Usain_Bolt",
             title="Usain Bolt",
             text="He also holds the 200 metres world record at 19.19 seconds."),
]


def test_a_reworded_claim_reuses_what_we_hold():
    async def go():
        await keep_subject("Usain Bolt ran the 100 metres in 9.58 seconds.", BOLT)
        # Same subject, DIFFERENT number -- the claim cache would miss this.
        return await recall_subject("Usain Bolt ran the 100 metres in 7.2 seconds.")

    got = asyncio.run(go())
    assert got, "held passages about Bolt must answer another Bolt claim"
    assert any("9.58" in e.text for e in got)


def test_a_different_subject_does_not_reuse_them():
    async def go():
        await keep_subject("Usain Bolt ran the 100 metres in 9.58 seconds.", BOLT)
        return await recall_subject("Mount Everest is 8,848 metres tall.")

    assert asyncio.run(go()) == []


def test_irrelevant_passages_about_the_right_subject_are_dropped():
    """Holding a subject's passages must not mean offering ALL of them.

    A claim about a race time should not be judged against a passage about
    where someone was born. The judge is protected from the noise here
    rather than asked to see past it.

    Uses an invented subject so the on-disk store, which real runs also
    write to, cannot make this pass or fail by accident.
    """
    who = "Fictional Testperson Qqzz"
    held = [
        Evidence(evidence_id="A", tier=1, url="https://example.test/a", title=who,
                 text=f"{who} ran the marathon in 2 hours and 1 minute."),
        Evidence(evidence_id="B", tier=1, url="https://example.test/b", title=who,
                 text=f"{who} enjoys gardening and owns a small blue boat."),
    ]

    async def go():
        await keep_subject(f"{who} ran the marathon in 2 hours.", held)
        return await recall_subject(f"{who} ran the marathon in 9 hours.")

    got = asyncio.run(go())
    texts = " ".join(e.text for e in got)
    assert "marathon" in texts, "the passage that answers it must survive"
    assert "gardening" not in texts, "the unrelated passage must be dropped"


def test_nothing_held_is_not_an_error():
    assert asyncio.run(recall_subject("Nobody Has Ever Asked About This Thing.")) == []


def test_a_claim_with_no_real_subject_is_skipped():
    async def go():
        await keep_subject("it is very good", BOLT)
        return await recall_subject("it is very good")

    assert asyncio.run(go()) == []
