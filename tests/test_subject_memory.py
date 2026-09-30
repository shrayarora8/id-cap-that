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
    # An invented subject, so a real claim run earlier tonight cannot leave
    # genuine passages on disk for this to accidentally find.
    async def go():
        await keep_subject("Usain Bolt ran the 100 metres in 9.58 seconds.", BOLT)
        return await recall_subject("Fictional Mountain Qwerty is 9,999 metres tall.")

    assert asyncio.run(go()) == []


def test_held_passages_are_ranked_not_keyword_filtered():
    """Relevance is the judge's job now, not a keyword match's.

    An earlier version of this required a literal word match to pass a
    passage through, on the theory that a race-time claim should not be
    judged against a passage about someone's hobbies. True in spirit, but
    the same strict match also silently dropped a passage that said
    "relationship with Zendaya" for a claim asking about "dating" --
    genuinely relevant, zero literal overlap.

    So nothing is REQUIRED to match a keyword any more; passages are ranked
    by relevance and the likely answer is expected to lead, but an
    unrelated passage riding along is not itself a failure -- the judge,
    proven elsewhere to say INSUFFICIENT_EVIDENCE rather than invent a
    connection, is what actually decides.

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
    assert got, "held passages about the subject must come back at all"
    texts = [e.text for e in got]
    assert any("marathon" in t for t in texts), "the answering passage must be included"
    assert texts[0] == held[0].text or "marathon" in texts[0], (
        "the passage that actually answers the claim should rank first"
    )


def test_nothing_held_is_not_an_error():
    assert asyncio.run(recall_subject("Nobody Has Ever Asked About This Thing.")) == []


def test_a_claim_with_no_real_subject_is_skipped():
    """_subject_of falls back to a claim's own raw text when nothing
    capitalised exists at all -- reasonable for its other job (giving the
    Wikipedia leg SOMETHING to search with) but wrong for memory, where it
    would let two unrelated opinion-shaped claims share a "subject" just
    because _subject_of gave up on both the same way.

    Caught directly: writing BOLT's evidence under the fallback "subject"
    of an opinion sentence, then asking for it back by the same sentence,
    must still come back empty -- there was never a real subject to key on.
    """
    async def go():
        await keep_subject("it is very good", BOLT)
        return await recall_subject("it is very good")

    assert asyncio.run(go()) == []
