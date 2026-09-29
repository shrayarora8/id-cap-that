"""Fetching a page ourselves, for the free sources.

This is **not** a Firecrawl replacement and must not be mistaken for one.
Measured on a real claim, plain httpx against four search results: one worked,
one was JavaScript-rendered and came back empty, two returned 403. Firecrawl
runs headless browsers through rotating residential proxies, which is what
defeats both, and that is genuinely hard to replicate.

What this IS good at is the pages the free sources point at -- an
organisation's own site, which is overwhelmingly static and wants to be read.
Measured at 149ms against Firecrawl's seconds, because there is no third-party
hop.

A failure here is never fatal. The leg is simply absent and the claim goes on
without it.
"""

from __future__ import annotations

import asyncio
import logging

import httpx

from . import config, store
from .sources import Passage, canonical, chunk_page, tier_for

log = logging.getLogger(__name__)

_http: httpx.AsyncClient | None = None

# The pages an organisation is likely to have, for the kinds of claim people
# actually make. A guess that 404s costs nothing.
LIKELY_PATHS = {
    "pricing": ("pricing", "plans"),
    "price": ("pricing", "plans"),
    "cost": ("pricing",),
    "charge": ("pricing",),
    "per seat": ("pricing",),
    "per user": ("pricing",),
    "per month": ("pricing",),
    "employee": ("about", "careers"),
    "founded": ("about",),
    "headquarter": ("about",),
    "ceo": ("about", "leadership", "team"),
    "president": ("about", "leadership"),
}


def http() -> httpx.AsyncClient:
    global _http
    if _http is None:
        _http = httpx.AsyncClient(
            headers={"User-Agent": config.HTTP_USER_AGENT},
            follow_redirects=True,
            timeout=config.FREE_SOURCE_TIMEOUT_S,
        )
    return _http


def extract(html: str) -> str:
    """Main content out of a page, falling back to a crude strip.

    trafilatura is built for exactly this and is far better than the twenty
    lines of regex I first tried, which kept the navigation and threw away the
    article.
    """
    try:
        import trafilatura

        text = trafilatura.extract(html, include_comments=False,
                                   include_tables=True, no_fallback=False)
        if text and len(text) > 200:
            return text
    except Exception:  # noqa: BLE001
        pass

    import re

    stripped = re.sub(r"<script.*?</script>|<style.*?</style>", " ", html,
                      flags=re.S | re.I)
    return re.sub(r"\s+", " ", re.sub(r"<[^>]+>", " ", stripped)).strip()


def paths_for(claim: str) -> list[str]:
    wanted: list[str] = []
    low = claim.lower()
    for word, paths in LIKELY_PATHS.items():
        if word in low:
            wanted.extend(p for p in paths if p not in wanted)
    return wanted[:2]


async def one_page(url: str, claim: str, ttl: int) -> str | None:
    """Fetch and extract one page. None when it will not open or says nothing."""
    key = canonical(url)
    held = await store.get("page", key)
    if held is not None:
        return held

    try:
        r = await http().get(url)
        if r.status_code >= 400:
            return None
        text = extract(r.text)
    except Exception as exc:  # noqa: BLE001
        log.info("fetch: %s did not open (%s)", url[:52], type(exc).__name__)
        return None

    # A page that renders with JavaScript returns HTML with nothing in it.
    # That is a miss, not an answer, and must not be stored as one.
    if len(text) < config.MIN_USEFUL_PAGE_CHARS:
        log.info("fetch: %s returned %d chars (javascript?)", url[:52], len(text))
        return None

    await store.put("page", key, text, ttl=ttl)
    return text


async def passages_from_site(site: str, claim: str, ttl: int) -> list[Passage]:
    """The site's own pages most likely to settle this claim."""
    if not site:
        return []

    base = site.rstrip("/")
    urls = [base] + [f"{base}/{p}" for p in paths_for(claim)]

    pages = await asyncio.gather(*(one_page(u, claim, ttl) for u in urls),
                                 return_exceptions=True)

    passages: list[Passage] = []
    for url, text in zip(urls, pages):
        if isinstance(text, str) and text:
            passages.extend(
                chunk_page(text[: config.MAX_PAGE_CHARS], url,
                           canonical(url), tier_for(url, claim))
            )
    if passages:
        log.info("fetch: %d passage(s) from %s", len(passages), base)
    return passages
