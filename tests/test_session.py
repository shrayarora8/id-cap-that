"""claim_id must never collide across sessions.

Measured bug: a reconnect (network blip, laptop sleeping, a backgrounded
tab) starts a fresh Session, and a fresh Session's claim counter restarts
at c1. A claim from the old session and a claim from the new one then
share an id.

The page keys its claim state by that id alone, the way it once keyed
transcript segments before segments were given an epoch to guard against
exactly this. The result, seen live: a verdict about the Nobel Prizes,
correctly judged with the right evidence, rendered on top of an unrelated
Tesla claim -- both were "c1" from two different sessions.
"""

from unittest.mock import MagicMock

from server.session import Session


def test_two_sessions_never_produce_the_same_claim_id():
    a, b = Session(MagicMock()), Session(MagicMock())
    ids_a = {a.next_claim_id() for _ in range(5)}
    ids_b = {b.next_claim_id() for _ in range(5)}
    assert ids_a.isdisjoint(ids_b)


def test_claim_ids_are_stable_and_ordered_within_one_session():
    # The old c1, c2, c3 shape is kept for readability in logs -- only the
    # collision across sessions needed fixing.
    s = Session(MagicMock())
    first, second = s.next_claim_id(), s.next_claim_id()
    assert first.startswith("c1_")
    assert second.startswith("c2_")
    assert first != second
