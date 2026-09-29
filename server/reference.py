"""Wikipedia, as a free source of evidence.

Measured before this existed: ten new claims answered from Wikipedia and the
official site alone, no search at all, settled ten of ten. Wikipedia carries
the half of claims that have no authoritative owner -- Bolt's 9.58, Everest's
height, Shakespeare's plays.

Two things learned the hard way while measuring:

  * The **summary** endpoint is too thin. It misses "9.58" on Usain Bolt's
    page entirely. The full article has it, at 67kb, which is exactly the size
    `sources.chunk_page` was written for.
  * Wikipedia throttles anonymous hammering, and when it does it returns
    **non-JSON rather than an error**. A measurement that did not pace itself
    silently reported 3/10 instead of 10/10. Hence the User-Agent with contact
    details, which their policy asks for, and the retries.
"""

from __future__ import annotations

import asyncio
import logging

import httpx

from . import config, store
from .sources import Passage, chunk_page

log = logging.getLogger(__name__)

API = "https://en.wikipedia.org/w/api.php"
# Wikipedia's API policy asks for a descriptive agent with a way to contact
# whoever is responsible. Anonymous scrapers get throttled first.
UA = {"User-Agent": config.HTTP_USER_AGENT}

_http: httpx.AsyncClient | None = None


def http() -> httpx.AsyncClient:
    global _http
    if _http is None:
        _http = httpx.AsyncClient(headers=UA, follow_redirects=True,
                                  timeout=config.FREE_SOURCE_TIMEOUT_S)
    return _http


async def _get(params: dict, tries: int = 2) -> dict | None:
    """Wikipedia returns HTML when it throttles, so a JSON failure is a
    throttle, not a bug. Retry once, then give up quietly."""
    for attempt in range(tries):
        try:
            r = await http().get(API, params=params)
            if r.status_code == 200:
                return r.json()
        except Exception:  # noqa: BLE001 - includes the JSON decode on a throttle
            pass
        if attempt + 1 < tries:
            await asyncio.sleep(0.6)
    return None


async def find_article(subject: str) -> str | None:
    """The article title for a subject, or None.

    Search by the SUBJECT, not the whole claim. Searching "Shakespeare wrote
    37 plays" finds nothing useful; searching "William Shakespeare" finds the
    article that contains the answer.
    """
    if not subject.strip():
        return None

    cached = await store.get("wikititle", subject.lower())
    if cached is not None:
        return cached or None

    data = await _get({"action": "query", "list": "search", "srsearch": subject,
                       "format": "json", "srlimit": 1})
    hits = (data or {}).get("query", {}).get("search", [])
    title = hits[0]["title"] if hits else ""
    await store.put("wikititle", subject.lower(), title,
                    ttl=store.TTL_SECONDS["entity"])
    return title or None


async def passages_for(subject: str, claim: str) -> list[Passage]:
    """The Wikipedia article about `subject`, cut into passages.

    Returns [] on anything going wrong. A free source that cannot fail a claim
    is the entire point -- it either contributes evidence or it does not.
    """
    title = await find_article(subject)
    if not title:
        return None or []

    url = f"https://en.wikipedia.org/wiki/{title.replace(' ', '_')}"
    text = await store.get("page", url)

    if text is None:
        data = await _get({"action": "query", "prop": "extracts", "explaintext": 1,
                           "format": "json", "titles": title})
        if not data:
            return []
        pages = data.get("query", {}).get("pages", {})
        text = next(iter(pages.values()), {}).get("extract", "") if pages else ""
        if not text:
            return []
        await store.put("page", url, text, ttl=store.TTL_SECONDS["reference"])

    log.info("wikipedia: %r -> %r (%dkb)", subject, title, len(text) // 1000)
    # Tier 1: an edited, corrected, cited reference work.
    return chunk_page(text[: config.MAX_PAGE_CHARS], url, title, 1)
