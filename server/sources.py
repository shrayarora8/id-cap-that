"""Deciding which pages deserve to be believed, and cutting them up.

Two jobs, both pure functions with no network, so both are cheap to test:

  1. tier_for(url, claim)  -- how much trust does this source get?
  2. chunk_page(markdown)  -- turn a 5,000 word page into passages worth reading

A downloaded page is mostly navigation, cookie banners, related links and
footers. Handing all of that to Claude is slow, expensive, and makes it worse
at the job.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from urllib.parse import urlparse

# Sites that are the primary record for something, or are edited and corrected.
TIER1_SUFFIXES = (".gov", ".edu", ".gov.uk", ".ac.uk", ".edu.au", ".int")
TIER1_DOMAINS = {
    "wikipedia.org", "britannica.com", "who.int", "un.org", "nasa.gov",
    "fifa.com", "uefa.com", "premierleague.com", "formula1.com", "olympics.com",
    "sec.gov", "europa.eu",
}

# Serious secondary reporting and well-known reference databases.
TIER2_DOMAINS = {
    "reuters.com", "apnews.com", "bbc.com", "bbc.co.uk", "nytimes.com",
    "theguardian.com", "ft.com", "economist.com", "bloomberg.com",
    "espn.com", "skysports.com", "transfermarkt.com", "transfermarkt.co.uk",
    "fbref.com", "statista.com", "forbes.com", "cnbc.com", "nature.com",
    "sciencedirect.com", "arxiv.org",
}

# Anyone can write these. Never enough on their own to contradict a claim.
LOW_TRUST_DOMAINS = {
    "reddit.com", "quora.com", "medium.com", "pinterest.com", "facebook.com",
    "x.com", "twitter.com", "tiktok.com", "answers.com", "ask.com",
    "wikihow.com", "blogspot.com", "wordpress.com", "substack.com",
}


@dataclass
class Passage:
    """One readable chunk of one page."""

    text: str
    url: str
    title: str
    tier: int

    @property
    def source_name(self) -> str:
        return registrable(self.url)


def registrable(url: str) -> str:
    """example.co.uk from https://www.example.co.uk/a/b."""
    host = (urlparse(url).hostname or "").lower()
    return host[4:] if host.startswith("www.") else host


def canonical(url: str) -> str:
    """One name per page.

    A URL is not an identity: www.notion.com/pricing/ and notion.com/pricing
    are the same page, and comparing raw strings once spent two of three
    page-fetch slots downloading the same thing twice. Identity is decided
    here, once, and every de-duplication uses this function.
    """
    parsed = urlparse(url)
    return f"{registrable(url)}{parsed.path.rstrip('/')}".lower()


def brand(url: str) -> str:
    """'notion' from notion.com. Used to spot a company's own website."""
    host = registrable(url)
    parts = host.split(".")
    return parts[0] if parts else ""


def tier_for(url: str, claim: str = "") -> int:
    """1 is best, 4 is worst.

    The interesting rule is the third: if the brand name of the site appears
    as a word in the claim, that site is primary FOR THAT CLAIM. notion.com is
    tier 1 for a claim about Notion and tier 3 for a claim about Messi. That
    one rule covers every company, product, league and team without anyone
    maintaining a list.
    """
    host = registrable(url)
    if not host:
        return 4

    if any(host.endswith(suffix) for suffix in TIER1_SUFFIXES):
        return 1
    if any(host == d or host.endswith("." + d) for d in TIER1_DOMAINS):
        return 1

    name = brand(url)
    if name and len(name) > 3 and re.search(rf"\b{re.escape(name)}\b", claim, re.IGNORECASE):
        return 1  # the subject's own site

    if any(host == d or host.endswith("." + d) for d in TIER2_DOMAINS):
        return 2
    if any(host == d or host.endswith("." + d) for d in LOW_TRUST_DOMAINS):
        return 4

    return 3


# --- turning a page into passages ------------------------------------------

LINK_RE = re.compile(r"\[([^\]]*)\]\([^)]*\)")
IMAGE_RE = re.compile(r"!\[[^\]]*\]\([^)]*\)")
JUNK_RE = re.compile(
    r"^(cookie|privacy|subscribe|sign in|log in|advertisement|share this|"
    r"follow us|all rights reserved|terms of|menu|skip to)",
    re.IGNORECASE,
)

MIN_CHUNK = 120
MAX_CHUNK = 700

TABLE_ROW_RE = re.compile(r"^\s*\|.*\|\s*$")
TABLE_RULE_RE = re.compile(r"^[\s|:-]+$")


def table_row_to_text(line: str) -> str | None:
    """Turn a markdown table row into a readable fragment.

    | 1 | Max Verstappen | Red Bull | 437 |  ->  1 - Max Verstappen - Red Bull - 437

    Standings, price tables and stats tables are exactly where the answer
    usually lives, and to a prose filter they look like punctuation. Dropping
    them is why a championship could not be confirmed from a page that
    literally contained the final standings.
    """
    if not TABLE_ROW_RE.match(line) or TABLE_RULE_RE.match(line):
        return None
    cells = [c.strip() for c in line.strip().strip("|").split("|")]
    cells = [c for c in cells if c]
    return " - ".join(cells) if len(cells) >= 2 else None


def clean_line(line: str) -> str:
    line = IMAGE_RE.sub("", line)
    line = LINK_RE.sub(r"\1", line)          # keep the words, drop the URL
    return line.strip()


def is_useful(line: str) -> bool:
    if len(line) < 25:
        return False
    if JUNK_RE.match(line):
        return False
    letters = sum(c.isalpha() for c in line)
    return letters / max(len(line), 1) > 0.5


def chunk_page(markdown: str, url: str, title: str, tier: int) -> list[Passage]:
    """Split a page into passages of roughly MAX_CHUNK characters.

    Headings are kept with the text under them, because "Goals: 38" only
    means something under the heading it belongs to.
    """
    passages: list[Passage] = []
    buffer: list[str] = []
    heading = ""
    # MIN_CHUNK exists to drop stray prose fragments. A table is not prose:
    # a whole price table can be under 120 characters and still be the entire
    # answer, so a buffer holding table data is exempt from the minimum.
    buffer_has_data = False

    def flush() -> None:
        nonlocal buffer_has_data
        if not buffer:
            return
        text = " ".join(buffer).strip()
        if len(text) >= MIN_CHUNK or buffer_has_data:
            body = f"{heading}: {text}" if heading else text
            passages.append(Passage(text=body, url=url, title=title, tier=tier))
        buffer.clear()
        buffer_has_data = False

    for raw in markdown.splitlines():
        line = clean_line(raw)

        if line.startswith("#"):
            flush()
            heading = line.lstrip("# ").strip()
            continue

        # Table rows skip the prose test entirely: they are data, not sentences.
        row = table_row_to_text(line)
        if row:
            buffer.append(row)
            buffer_has_data = True
            if sum(len(b) for b in buffer) >= MAX_CHUNK:
                flush()
            continue

        if not is_useful(line):
            continue

        buffer.append(line)
        if sum(len(b) for b in buffer) >= MAX_CHUNK:
            flush()

    flush()
    return passages


# --- narrowing the pile before the expensive step --------------------------

STOPWORDS = {
    "the", "a", "an", "and", "or", "of", "in", "on", "at", "to", "for", "is",
    "was", "were", "are", "be", "been", "by", "with", "from", "that", "this",
    "it", "its", "as", "his", "her", "their", "he", "she", "they", "we", "you",
    "did", "does", "do", "has", "have", "had", "how", "many", "much", "what",
}


def keywords(text: str) -> set[str]:
    """The distinctive words in a piece of text.

    The length filter drops "of", "an" and so on -- but it must NOT drop
    numbers. "45", "20", "$0" and "7" are one to three characters and they are
    the single most important token in a claim about a quantity. Filtering
    them out meant "45 goals" and "38 goals" scored identically, so the
    keyword pass could not tell the passage containing the answer from one
    that merely mentioned goals.
    """
    words = re.findall(r"[a-z0-9']+", text.lower())
    return {
        w for w in words
        if w not in STOPWORDS and (len(w) > 2 or any(c.isdigit() for c in w))
    }


def keyword_score(passage: Passage, claim_words: set[str]) -> float:
    """How much of the claim's vocabulary appears in this passage.

    Crude on purpose: its only job is to throw out the obviously irrelevant
    nine tenths before we pay to embed anything. Numbers count double, because
    a claim about 45 goals is settled by the passage containing a number, not
    by the one that says "goals" twice.
    """
    if not claim_words:
        return 0.0
    found = claim_words & keywords(passage.text)
    digits = sum(1 for w in found if any(c.isdigit() for c in w))
    return (len(found) + digits) / len(claim_words)


def cap_per_source(passages: list[Passage], per_source: int) -> list[Passage]:
    """Stop one page filling every slot.

    Five passages from one article tell the judge one thing five times. Three
    sources agreeing is evidence; sources disagreeing is DISPUTED, which can
    only ever be detected if more than one source gets through.
    """
    seen: dict[str, int] = {}
    kept = []
    for passage in passages:
        key = canonical(passage.url)
        count = seen.get(key, 0)
        if count < per_source:
            seen[key] = count + 1
            kept.append(passage)
    return kept


def preselect(
    passages: list[Passage], claim: str, limit: int, per_source: int = 0
) -> list[Passage]:
    """Keep the passages most likely to be about this claim.

    Order matters: rank FIRST, then cap per source. Capping first keeps
    whichever chunks happen to come earliest in the page, which on a pricing
    page is the marketing header rather than the price table. That looked like
    a harmless refactor and threw away the literal answer.
    """
    claim_words = keywords(claim)
    ranked = sorted(
        passages,
        key=lambda p: (keyword_score(p, claim_words), -p.tier),
        reverse=True,
    )
    relevant = [p for p in ranked if keyword_score(p, claim_words) > 0] or ranked

    if per_source:
        relevant = cap_per_source(relevant, per_source)
    return relevant[:limit]
