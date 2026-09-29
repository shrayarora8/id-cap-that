"""Who owns this fact, and can we prove it?

The sorter already guesses an `official_domain` and is often good at it --
`grammy.com` for a Grammy count is the awarding body, not the artist's site.
What it lacks is verification, and a guess that is wrong is worse than none:
it sends the check to a site that cannot possibly answer.

Wikidata property P856 is "official website". Measured: Arsenal ->
arsenal.com, Notion -> notion.com, Stripe -> stripe.com, Tesla, Spotify, all
correct. And one instructive failure -- **Snowflake -> twitter.com**, because
the search matched "Snowflake ID", a Twitter identifier format.

So nothing is trusted without a check. Half of claims have no authority at all
(Bolt, Everest, Messi all return none) and that is a normal, silent outcome.
"""

from __future__ import annotations

import asyncio
import logging

import httpx

from . import config, store
from .sources import brand, registrable

log = logging.getLogger(__name__)

SEARCH = "https://www.wikidata.org/w/api.php"
ENTITY = "https://www.wikidata.org/wiki/Special:EntityData/{}.json"
OFFICIAL_WEBSITE = "P856"

_http: httpx.AsyncClient | None = None


def http() -> httpx.AsyncClient:
    global _http
    if _http is None:
        _http = httpx.AsyncClient(headers={"User-Agent": config.HTTP_USER_AGENT},
                                  follow_redirects=True,
                                  timeout=config.FREE_SOURCE_TIMEOUT_S)
    return _http


def looks_like_the_same_thing(subject: str, url: str) -> bool:
    """Does this domain plausibly belong to this subject?

    The Snowflake case: Wikidata confidently returned twitter.com. The brand
    of the domain ("twitter") shares nothing with the subject ("Snowflake"),
    and that is enough to reject it.

    Deliberately crude. It only has to catch a resolution that is obviously
    about something else, and it fails towards "no authority", which costs a
    search rather than a wrong answer.
    """
    site = brand(url)
    if not site:
        return False
    words = {w.lower().strip(".,'") for w in subject.split() if len(w) > 2}
    if site.lower() in words:
        return True
    # notion.com for "Notion", arsenal.com for "Arsenal F.C." -- a subject word
    # contained in the brand, or the reverse, both count.
    return any(w in site.lower() or site.lower() in w for w in words)


def _fits_the_claim(description: str, claim: str) -> int:
    """How well a Wikidata candidate's description matches what was claimed.

    "Snowflake" is a database company, a Twitter id format, AND a Tor
    circumvention tool. The brand check catches twitter.com but not
    snowflake.torproject.org, which shares the name. The claim itself is the
    only thing that can tell them apart, and the sorter already has it.
    """
    from .sources import keywords

    if not description:
        return 0
    return len(keywords(description) & keywords(claim))


async def official_site(subject: str, claim: str = "") -> str | None:
    """The subject's own website, verified, or None.

    None is a normal answer. Most claims have no single organisation that owns
    them, and pretending otherwise sends the check somewhere useless.
    """
    if not subject.strip():
        return None

    cache_key = f"{subject.lower()}|{claim.lower()[:60]}"
    cached = await store.get("entity", cache_key)
    if cached is not None:
        return cached or None

    found = ""
    try:
        r = await http().get(SEARCH, params={
            "action": "wbsearchentities", "search": subject,
            "language": "en", "format": "json", "limit": 5})
        candidates = []
        for hit in r.json().get("search", []):
            e = await http().get(ENTITY.format(hit["id"]))
            claims_ = e.json()["entities"][hit["id"]].get("claims", {})
            prop = claims_.get(OFFICIAL_WEBSITE)
            if not prop:
                continue
            url = prop[0]["mainsnak"]["datavalue"]["value"]
            if not looks_like_the_same_thing(subject, url):
                log.info("entities: rejected %s for %r (brand does not match)",
                         registrable(url), subject)
                continue
            candidates.append((_fits_the_claim(hit.get("description", ""), claim), url))

        if candidates:
            # Best description match wins; Wikidata's own ordering breaks ties,
            # which is what the original single-answer behaviour was.
            candidates.sort(key=lambda pair: -pair[0])
            found = candidates[0][1]
    except Exception as exc:  # noqa: BLE001
        log.info("entities: lookup failed for %r (%s)", subject, type(exc).__name__)

    # Cached either way. A subject with no official site will still have none
    # tomorrow, and re-asking costs the same as asking.
    await store.put("entity", cache_key, found,
                    ttl=store.TTL_SECONDS["entity"])
    return found or None
