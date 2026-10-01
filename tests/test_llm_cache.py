"""The LLM cache must never be able to cost a claim.

Measured: the sorter schema gained a required field. Every cached sorter
answer lacked it, failed validation on read, and crashed the sorter -- no
claim at all, for any sentence that had ever been checked before.
"""

from pydantic import BaseModel

from server import llm


class Old(BaseModel):
    a: str


class New(BaseModel):  # same name in spirit: Old plus one required field
    a: str
    b: str


def test_a_schema_change_changes_the_cache_key():
    Old.__name__ = New.__name__ = "SameName"
    try:
        assert llm._schema_tag(Old) != llm._schema_tag(New)
    finally:
        Old.__name__, New.__name__ = "Old", "New"


def test_an_entry_that_no_longer_fits_is_a_miss_not_a_crash(tmp_path):
    stale = tmp_path / "stale.json"
    stale.write_text('{"a": "cached before field b existed"}')
    assert llm._read_cached(stale, New) is None


def test_a_good_entry_still_reads(tmp_path):
    good = tmp_path / "good.json"
    good.write_text('{"a": "x", "b": "y"}')
    assert llm._read_cached(good, New).b == "y"


def test_a_missing_entry_is_a_miss(tmp_path):
    assert llm._read_cached(tmp_path / "nope.json", New) is None
