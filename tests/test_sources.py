"""Trust, identity, and turning a page into passages. All pure, all free.

Several of these are bugs that shipped in the previous build.
"""

from __future__ import annotations

import pytest

from server.sources import (
    Passage, canonical, cap_per_source, chunk_page, keyword_score, keywords,
    preselect, registrable, table_row_to_text, tier_for,
)


# --- trust ------------------------------------------------------------------


@pytest.mark.parametrize("url,expected", [
    ("https://en.wikipedia.org/wiki/Messi", 1),
    ("https://www.nasa.gov/mission", 1),
    ("https://ox.ac.uk/research", 1),
    ("https://www.reuters.com/world", 2),
    ("https://espn.com/soccer", 2),
    ("https://some-random-blog.net/post", 3),
    ("https://www.reddit.com/r/soccer", 4),
    ("https://medium.com/@someone/post", 4),
    ("not a url at all", 4),
])
def test_tiers(url, expected):
    assert tier_for(url) == expected


def test_a_companys_own_site_is_primary_for_claims_about_it():
    """The one rule that generalises: it covers every company, product, league
    and team without anyone maintaining a list."""
    assert tier_for("https://notion.com/pricing", "Notion charges $500 a seat") == 1
    assert tier_for("https://notion.com/pricing", "Messi scored 45 goals") == 3


def test_the_brand_rule_needs_a_whole_word():
    """Otherwise 'app.com' is primary for any claim containing 'apple'."""
    assert tier_for("https://ford.com/x", "I can afford it") == 3


def test_the_brand_rule_ignores_very_short_names():
    """Two and three letter brands match far too much ordinary text."""
    assert tier_for("https://abc.com/x", "the abc of it") == 3


# --- identity ---------------------------------------------------------------


def test_www_and_non_www_are_the_same_page():
    """Comparing raw URL strings once spent two of three page-fetch slots on
    the identical page."""
    assert canonical("https://www.notion.com/pricing/") == canonical("https://notion.com/pricing")


def test_canonical_ignores_scheme_case_and_trailing_slash():
    assert canonical("HTTPS://WWW.Example.com/A/") == canonical("https://example.com/A")


def test_registrable_strips_www():
    assert registrable("https://www.bbc.co.uk/news") == "bbc.co.uk"


# --- turning a page into passages ------------------------------------------


def test_a_table_row_becomes_readable_text():
    """The bug this pins: is_useful requires more than half the characters to
    be letters, and a table row is mostly pipes, spaces and digits. Every row
    of every standings table, price table and stats table was silently
    discarded -- and that is exactly where answers live."""
    assert table_row_to_text("| 1 | Max Verstappen | Red Bull | 437 |") == "1 - Max Verstappen - Red Bull - 437"


def test_the_separator_row_is_dropped():
    assert table_row_to_text("|---|---|---|") is None
    assert table_row_to_text("| :--- | ---: |") is None


def test_a_price_table_survives_the_prose_filter():
    page = """# Pricing

| Plan | Price |
|---|---|
| Free | $0 |
| Business | $20 per seat/month billed annually |
| Enterprise | Contact sales for a quote today |
"""
    passages = chunk_page(page, "https://notion.com/pricing", "Pricing", 1)
    combined = " ".join(p.text for p in passages)
    assert "$20 per seat/month" in combined, "the literal answer was thrown away"


def test_headings_stay_with_the_text_under_them():
    """'Goals: 38' only means something under the heading it belongs to."""
    page = "# Career statistics\n\n" + "He scored a lot of goals over many seasons. " * 5
    passages = chunk_page(page, "https://x.com/a", "t", 2)
    assert passages[0].text.startswith("Career statistics:")


def test_navigation_and_cookie_banners_are_dropped():
    page = "Cookie policy and preferences for this website here\n\n" + "Real content. " * 20
    passages = chunk_page(page, "https://x.com/a", "t", 2)
    assert not any("Cookie policy" in p.text for p in passages)


def test_markdown_links_keep_their_words_and_lose_the_url():
    page = "See [the official standings page](https://example.com/very/long/url) for the full table of results. " * 3
    passages = chunk_page(page, "https://x.com/a", "t", 2)
    combined = " ".join(p.text for p in passages)
    assert "the official standings page" in combined
    assert "https://example.com" not in combined


def test_an_empty_page_produces_nothing():
    assert chunk_page("", "https://x.com/a", "t", 2) == []


# --- narrowing --------------------------------------------------------------


def test_stopwords_are_not_keywords():
    assert "the" not in keywords("the goals of the season")
    assert "goals" in keywords("the goals of the season")


def test_numbers_count_double_in_the_keyword_score():
    """A claim about 45 goals is settled by the passage containing a number,
    not by the one that says 'goals' twice."""
    claim = keywords("Messi scored 45 goals")
    with_number = Passage("Messi scored 45 goals last season", "u", "t", 1)
    without = Passage("Messi scored goals for the club goals goals", "u", "t", 1)
    assert keyword_score(with_number, claim) > keyword_score(without, claim)


def test_ranking_happens_before_capping():
    """The bug this pins: cap_per_source keeps whichever chunks come earliest
    in the page. On a pricing page that is the marketing header, so the price
    table -- the literal answer -- was thrown away before ranking."""
    url = "https://notion.com/pricing"
    marketing = Passage("The connected workspace where better faster work happens", url, "t", 1)
    the_answer = Passage("Business plan costs $20 per seat per month", url, "t", 1)

    kept = preselect([marketing, the_answer], "Notion price per seat per month", limit=1, per_source=1)
    assert kept == [the_answer]


def test_one_page_cannot_fill_every_evidence_slot():
    """Three sources agreeing is evidence. Sources disagreeing is DISPUTED,
    which can only be detected if more than one source gets through."""
    same = [Passage(f"passage {i}", "https://one.com/a", "t", 2) for i in range(5)]
    other = [Passage("different source", "https://two.com/b", "t", 2)]
    kept = cap_per_source(same + other, per_source=2)
    assert len(kept) == 3
    assert any("different" in p.text for p in kept)


def test_capping_uses_canonical_urls():
    """Otherwise www.x.com and x.com each get their own quota."""
    passages = [
        Passage("a", "https://www.notion.com/pricing", "t", 1),
        Passage("b", "https://notion.com/pricing/", "t", 1),
        Passage("c", "https://notion.com/pricing", "t", 1),
    ]
    assert len(cap_per_source(passages, per_source=1)) == 1


def test_nothing_relevant_still_returns_something():
    """Returning an empty list here would mean the judge sees no evidence at
    all and says COULD BE CAP, when we did find pages."""
    passages = [Passage("completely unrelated text here", "https://x.com/a", "t", 3)]
    assert preselect(passages, "Messi goals", limit=5) == passages
