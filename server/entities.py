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


# --- one entity per claim ---------------------------------------------------
#
# The two free legs used to resolve a name independently, and measured
# against seven everyday subjects they disagreed or were wrong on four:
#
#   Tesla        Wikipedia fetched NIKOLA Tesla, the inventor
#   Arsenal      Wikipedia fetched "arsenal", a store of weapons
#   Snowflake    the official site resolved to Tor's Snowflake proxy
#   Tom Holland  the official site resolved to the historian, not the actor
#
# The last one is what broke the elimination test: handed passages about two
# different men called Tom Holland, the judge correctly refused to say
# anything about "Tom Holland" at all. Every passage was real, every quote
# would have verified, and the evidence was still worthless.
#
# A name alone cannot pick between them. What the claim is about can: the
# sorter now says what KIND of thing its subject is ("electric car company",
# "English actor"), and Wikidata describes every candidate the same way. The
# best match is resolved ONCE, and both legs take their source from that one
# entity -- so they can no longer disagree about who the subject is.

from dataclasses import dataclass  # noqa: E402
import re  # noqa: E402

_KIND_STOPWORDS = {
    "a", "an", "the", "of", "and", "in", "for", "from", "based", "born",
    "american", "british", "english", "company",  # see _kind_words
}


def _kind_words(text: str) -> set[str]:
    """The words that DISTINGUISH one kind of thing from another.

    Nationalities and "company" are dropped from the distinguishing set
    because they are near-universal in Wikidata descriptions and in the
    sorter's hint alike -- "American company" overlaps every American
    company. They still count, but only as a tie-break (see resolve).
    """
    words = set(re.findall(r"[a-z]+", (text or "").lower()))
    return {w.rstrip("s") for w in words if len(w) > 2} - _KIND_STOPWORDS


def _all_words(text: str) -> set[str]:
    return {w.rstrip("s") for w in re.findall(r"[a-z]+", (text or "").lower()) if len(w) > 2}


@dataclass
class Entity:
    qid: str
    label: str
    description: str
    wiki_title: str | None
    site: str | None


async def resolve(subject: str, kind: str) -> Entity | None:
    """The one real-world thing this claim is about, or None.

    None means "could not tell" and the caller falls back to resolving each
    leg by name, exactly as before -- so a missing or unhelpful hint can
    never make a claim worse than it was.
    """
    if not subject.strip() or not kind.strip():
        return None

    cache_key = f"{subject.lower()}|{kind.lower()}"
    cached = await store.get("resolved", cache_key)
    if cached is not None:
        return Entity(**cached) if cached else None

    entity: Entity | None = None
    try:
        r = await http().get(SEARCH, params={
            "action": "wbsearchentities", "search": subject,
            "language": "en", "format": "json", "limit": 10})
        hits = r.json().get("search", [])

        want, want_all = _kind_words(kind), _all_words(kind)

        # Which candidates have an English Wikipedia article -- one batched
        # call for all of them. A Wikidata item with no article is usually a
        # minor duplicate (Tesla has a "brand of electric vehicles" item as
        # well as Tesla, Inc.), and it is the article that gives us evidence.
        ids = [h["id"] for h in hits]
        wiki_of: dict[str, str] = {}
        if ids:
            links = await http().get(SEARCH, params={
                "action": "wbgetentities", "ids": "|".join(ids),
                "props": "sitelinks", "sitefilter": "enwiki", "format": "json"})
            for qid, data in links.json().get("entities", {}).items():
                title = data.get("sitelinks", {}).get("enwiki", {}).get("title")
                if title:
                    wiki_of[qid] = title

        def score(rank: int, hit: dict) -> tuple[int, int, int]:
            desc = hit.get("description", "")
            return (len(want & _kind_words(desc)), len(want_all & _all_words(desc)), -rank)

        scored = [(score(i, h), h) for i, h in enumerate(hits)]

        # 1. A distinguishing word in common, and a real article behind it.
        tier_a = [(sc, h) for sc, h in scored if sc[0] > 0 and h["id"] in wiki_of]
        # 2. Nothing distinguishing matched, but Wikidata's own top result has
        #    an article and shares the category ("company"). Tesla, Inc. is
        #    described as "automotive, energy storage and solar power" -- no
        #    word in common with "electric car company" except "company".
        top = scored[0] if scored else None
        tier_b = [top] if top and top[1]["id"] in wiki_of and top[0][1] > 0 else []
        # 3. A distinguishing match with no article: usable for its website
        #    only. Small companies often have a site and no Wikipedia page.
        tier_c = [(sc, h) for sc, h in scored if sc[0] > 0]

        best = None
        for tier in (tier_a, tier_b, tier_c):
            if tier:
                best = max(tier, key=lambda pair: pair[0])[1]
                break

        if best:
            qid = best["id"]
            e = await http().get(SEARCH, params={
                "action": "wbgetentities", "ids": qid, "props": "claims",
                "format": "json"})
            data = e.json()["entities"][qid]
            wiki = wiki_of.get(qid)
            site = None
            prop = data.get("claims", {}).get(OFFICIAL_WEBSITE)
            if prop:
                url = prop[0]["mainsnak"]["datavalue"]["value"]
                if looks_like_the_same_thing(subject, url):
                    site = url
            entity = Entity(qid=qid, label=best.get("label", ""),
                            description=best.get("description", ""),
                            wiki_title=wiki, site=site)
            log.info("entities: %r (%s) -> %s %r, wiki=%r site=%s", subject, kind,
                     qid, entity.description, wiki, site)
        else:
            log.info("entities: no candidate for %r fits %r", subject, kind)
    except Exception as exc:  # noqa: BLE001
        log.info("entities: resolve failed for %r (%s)", subject, type(exc).__name__)
        # Not cached: a network failure is not an answer.
        return None

    await store.put("resolved", cache_key, entity.__dict__ if entity else {},
                    ttl=store.TTL_SECONDS["entity"])
    return entity
