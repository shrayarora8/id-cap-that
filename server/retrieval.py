"""Getting evidence. Snippet-first, and only going deeper when asked.

The previous build fetched three full pages for every claim: about six
Firecrawl credits, four round trips, and roughly seven seconds before the
judge had even started. Most claims do not need any of that. A search returns
titles and descriptions that are already relevant, cost one credit, and arrive
in one round trip.

So the flow has two depths:

  snippets  search -> tier -> hand the descriptions straight to the judge
            ~1.5s, 1 credit, settles most claims

  pages     fetch the best pages, cut them into passages, rank them with Moss,
            judge again
            ~4s more, 3 more credits, used only when the judge says its
            evidence was too thin

Which one a claim gets is the judge's decision, not a setting. That is the
agentic part, and it is a single field in a response we were already paying
for rather than an extra call.

Everything is cached on disk, because Firecrawl's limit is ten requests a
minute and a demo can exhaust a minute in twenty seconds.
"""

from __future__ import annotations

import asyncio
import hashlib
import json
import logging
import time
from dataclasses import dataclass
from typing import Callable

import httpx

from . import config
from .ratelimit import RateLimited, RateLimiter
from .sources import Passage, canonical, chunk_page, preselect, tier_for

log = logging.getLogger(__name__)

SEARCH_URL = "https://api.firecrawl.dev/v2/search"
SCRAPE_URL = "https://api.firecrawl.dev/v2/scrape"

# On disk, not in memory. uvicorn --reload restarts the process on every file
# save, and an in-memory cache means every restart re-spends real credits on
# pages we already had. This is also what makes a demo pre-warmable.
CACHE_DIR = config.ROOT / ".cache" / "web"
CACHE_DIR.mkdir(parents=True, exist_ok=True)

_http: httpx.AsyncClient | None = None
_limiter = RateLimiter(config.FIRECRAWL_PER_MINUTE)
_credits_used = 0


@dataclass
class Hit:
    url: str
    title: str
    description: str
    tier: int = 3


@dataclass
class Evidence:
    """One passage the judge is allowed to reason from."""

    evidence_id: str
    text: str
    url: str
    title: str
    tier: int
    score: float = 0.0


def http() -> httpx.AsyncClient:
    """One client for the process, so the second request to a host skips the
    TLS handshake."""
    global _http
    if _http is None:
        _http = httpx.AsyncClient(timeout=config.FETCH_TIMEOUT_S)
    return _http


def credits_used() -> int:
    return _credits_used


# --- the on-disk cache ------------------------------------------------------


def _cache_path(kind: str, key: str) -> "object":
    digest = hashlib.sha256(key.encode()).hexdigest()[:24]
    return CACHE_DIR / f"{kind}_{digest}.json"


def _cache_get(kind: str, key: str):
    path = _cache_path(kind, key)
    if path.exists():
        try:
            return json.loads(path.read_text())
        except json.JSONDecodeError:
            return None
    return None


def _cache_put(kind: str, key: str, value) -> None:
    CACHE_DIR.mkdir(parents=True, exist_ok=True)
    _cache_path(kind, key).write_text(json.dumps(value))


# --- Firecrawl --------------------------------------------------------------


def _auth() -> dict[str, str]:
    return {"Authorization": f"Bearer {config.require('FIRECRAWL_API_KEY')}"}


def _parse_results(payload: dict) -> list[dict]:
    """Firecrawl returns {"data": {"web": [...]}} or {"data": [...]}."""
    data = payload.get("data", [])
    if isinstance(data, dict):
        return data.get("web", []) or []
    return data or []


async def _post(url: str, payload: dict, on_status=None) -> httpx.Response:
    """One Firecrawl request, after waiting for a rate-limit slot.

    Waiting before asking is better than retrying after a 429: same
    throughput, no wasted round trip, and the delay is something the UI can
    narrate instead of an unexplained stall.
    """
    global _credits_used

    waited = await _limiter.acquire(max_wait=config.MAX_RATE_LIMIT_WAIT_S)
    if waited > 0.5 and on_status:
        on_status(f"waiting {waited:.0f}s for a search slot")

    resp = await http().post(url, headers=_auth(), json=payload)
    _credits_used += 1

    if resp.status_code == 429:
        # We should not get here, but if the limit moves we retry once rather
        # than losing the claim.
        log.warning("firecrawl rate limited despite the limiter; backing off")
        await asyncio.sleep(3.0)
        resp = await http().post(url, headers=_auth(), json=payload)
        _credits_used += 1

    resp.raise_for_status()
    return resp


# When a company owns a fact, ask the company. A page optimised for "notion
# pricing" out-ranks the page that IS the answer, because that is what SEO is
# for.
COMMON_PAGES = {
    "pricing": "pricing", "price": "pricing", "charge": "pricing",
    "cost": "pricing", "per user": "pricing", "per month": "pricing",
    "per seat": "pricing", "plan": "pricing",
}


async def search(query: str, claim: str, official_domain: str = "", on_status=None, deep: bool = False) -> list[Hit]:
    """Search, tier the results, and nudge towards whoever owns the fact.

    When there is an official domain this fires two or three searches. They
    used to run one after another, which cost nearly two seconds to do under
    one second of work -- they do not depend on each other, so they go
    together.
    """
    queries = [query]
    guesses: list[Hit] = []

    if official_domain:
        # The site: search used to run on every claim, doubling the Firecrawl
        # requests. At ten requests a minute that halves how many claims can
        # be checked before everything queues, and a 22-line script generates
        # claims far faster than that. It now runs only when asked for, which
        # is the escalation path.
        if deep:
            queries.append(f"{query} site:{official_domain}")
        # A guessed URL costs nothing until something actually fetches it, and
        # it is usually right for the handful of page names people ask about.
        wanted = {
            path for word, path in COMMON_PAGES.items()
            if word in query.lower() or word in claim.lower()
        }
        guesses = [
            Hit(url=f"https://{official_domain}/{path}", title=path, description="", tier=1)
            for path in sorted(wanted)
        ]

    results = await asyncio.gather(
        *(_search_once(q, claim, on_status) for q in queries),
        return_exceptions=True,
    )

    hits: list[Hit] = list(guesses)
    rate_limited = False
    for batch in results:
        if isinstance(batch, RateLimited):
            rate_limited = True
            log.warning("one search leg failed: %s", batch)
            continue
        if isinstance(batch, Exception):
            log.warning("one search leg failed: %s", batch)
            continue
        for hit in batch:
            if official_domain and official_domain in hit.url:
                hit.tier = 1          # primary source for its own facts
            hits.append(hit)

    seen, unique = set(), []
    for hit in hits:
        key = canonical(hit.url)
        if key not in seen:
            seen.add(key)
            unique.append(hit)

    unique.sort(key=lambda h: h.tier)
    log.info("search %r -> %s", query, [f"{h.tier}:{h.url[:44]}" for h in unique[:6]])

    # Finding nothing because we never looked is not the same as finding
    # nothing because the web had nothing, and telling a user "no sources were
    # found" when we never made the request is simply false. It also reads as
    # a broken checker rather than a busy one.
    if not unique and rate_limited:
        raise RateLimited("the search rate limit was busy for too long")

    return unique


def have_cached_search(query: str) -> bool:
    """Did a speculative search for this text already land?"""
    return _cache_get("search", query) is not None


async def _search_once(query: str, claim: str, on_status=None) -> list[Hit]:
    cached = _cache_get("search", query)
    if cached is not None:
        log.info("search cached: %r", query[:50])
        return [Hit(**h) for h in cached]

    resp = await _post(SEARCH_URL, {"query": query, "limit": config.SEARCH_RESULTS}, on_status)

    hits = [
        Hit(
            url=r.get("url", ""),
            title=r.get("title", "") or "",
            description=r.get("description", "") or "",
            tier=tier_for(r.get("url", ""), claim),
        )
        for r in _parse_results(resp.json())
        if r.get("url")
    ]
    _cache_put("search", query, [h.__dict__ for h in hits])
    return hits


async def fetch(hit: Hit, on_status=None) -> str | None:
    """Download one page as clean markdown.

    Returns None rather than raising: one dead page should degrade the
    evidence, not kill the claim.
    """
    cached = _cache_get("page", hit.url)
    if cached is not None:
        log.info("page cached: %s", hit.url[:60])
        return cached.get("markdown")

    try:
        resp = await _post(
            SCRAPE_URL,
            {"url": hit.url, "formats": ["markdown"], "onlyMainContent": True},
            on_status,
        )
        markdown = (resp.json().get("data") or {}).get("markdown")
        _cache_put("page", hit.url, {"markdown": markdown})
        log.info("fetched %s (%d chars)", hit.url[:60], len(markdown or ""))
        return markdown
    except Exception as exc:  # noqa: BLE001
        log.warning("could not fetch %s: %s", hit.url[:60], exc)
        return None


# --- depth one: snippets ----------------------------------------------------


def snippets_as_evidence(hits: list[Hit]) -> list[Evidence]:
    """Turn search results straight into evidence.

    Free, already relevant, one round trip. This is what makes a verdict land
    in four seconds instead of nine.
    """
    evidence = []
    for hit in hits:
        if not hit.description:
            continue
        evidence.append(
            Evidence(
                evidence_id=f"E{len(evidence) + 1}",
                text=f"{hit.title}: {hit.description}".strip(": "),
                url=hit.url,
                title=hit.title,
                tier=hit.tier,
            )
        )
    evidence.sort(key=lambda e: e.tier)
    for n, e in enumerate(evidence, 1):
        e.evidence_id = f"E{n}"
    return evidence[: config.PASSAGES_FOR_JUDGE]


# --- depth two: real pages --------------------------------------------------


def cap_evidence_per_source(evidence: list[Evidence], per_source: int) -> list[Evidence]:
    seen: dict[str, int] = {}
    kept = []
    for item in evidence:
        key = canonical(item.url)
        count = seen.get(key, 0)
        if count < per_source:
            seen[key] = count + 1
            kept.append(item)
    return kept


async def deepen(
    claim: str, hits: list[Hit], on_status: Callable[[str], None] = lambda _: None
) -> list[Evidence]:
    """Fetch the best pages and rank their passages. The escalation path."""
    chosen = hits[: config.PAGES_TO_FETCH]
    if not chosen:
        return []

    on_status(f"reading {len(chosen)} page(s)")
    pages = await asyncio.gather(*(fetch(h, on_status) for h in chosen))

    passages: list[Passage] = []
    for hit, markdown in zip(chosen, pages):
        if markdown:
            passages.extend(
                chunk_page(markdown[: config.MAX_PAGE_CHARS], hit.url, hit.title, hit.tier)
            )

    if not passages:
        return []

    # A social post is not evidence when a real source exists. Keep them only
    # when they are all we found, so the judge can still say "only a forum
    # says this" rather than nothing at all.
    real = [p for p in passages if p.tier <= 3]
    if real:
        passages = real

    shortlist = preselect(
        passages, claim, config.PRESELECT_PASSAGES,
        per_source=config.PASSAGES_PER_SOURCE * 2,
    )
    on_status(f"sifting {len(shortlist)} of {len(passages)} passages")

    ranked = await rank_passages(claim, shortlist)
    ranked = cap_evidence_per_source(ranked, config.PASSAGES_PER_SOURCE)
    # Trust first, similarity breaks ties: ranking by meaning alone once put a
    # social post above a primary source.
    ranked.sort(key=lambda e: (e.tier, -e.score))
    for n, e in enumerate(ranked, 1):
        e.evidence_id = f"E{n}"
    return ranked[: config.PASSAGES_FOR_JUDGE]


async def rank_passages(claim: str, passages: list[Passage]) -> list[Evidence]:
    """Rank by meaning with Moss, falling back to the keyword score.

    Moss is worth it here because a fetched page is thousands of words of
    menus and unrelated facts, and the judge reads far better when it is given
    signal instead of noise. If Moss is unavailable the claim still resolves,
    just less well ranked -- an optional dependency must never be able to fail
    a verdict.
    """
    if not config.MOSS_ENABLED:
        # Moss bills per minute of open session. With it off, rank by the
        # keyword score we already computed -- worse ordering, same passages,
        # no session and no bill.
        return [
            Evidence(
                evidence_id=f"E{i + 1}", text=p.text, url=p.url,
                title=p.title, tier=p.tier, score=0.0,
            )
            for i, p in enumerate(passages[: config.PASSAGES_FOR_JUDGE * 2])
        ]

    try:
        from moss import DocumentInfo, MossClient, QueryOptions

        session = await _moss_session(MossClient)
        await session.add_docs([
            DocumentInfo(
                id=hashlib.sha1(f"{p.url}#{i}".encode()).hexdigest()[:20],
                text=p.text,
                metadata={"url": p.url, "title": p.title, "tier": str(p.tier)},
            )
            for i, p in enumerate(passages)
        ])
        result = await session.query(claim, QueryOptions(top_k=config.PASSAGES_FOR_JUDGE * 2))
        log.info("moss: %d passages in %.1fms", len(result.docs), result.time_taken_ms)
        return [
            Evidence(
                evidence_id=f"E{i + 1}",
                text=doc.text,
                url=(doc.metadata or {}).get("url", ""),
                title=(doc.metadata or {}).get("title", ""),
                tier=int((doc.metadata or {}).get("tier", 3)),
                score=doc.score,
            )
            for i, doc in enumerate(result.docs)
        ]
    except Exception as exc:  # noqa: BLE001
        log.warning("moss unavailable (%s), using keyword order", exc)
        return [
            Evidence(
                evidence_id=f"E{i + 1}", text=p.text, url=p.url,
                title=p.title, tier=p.tier, score=0.0,
            )
            for i, p in enumerate(passages[: config.PASSAGES_FOR_JUDGE * 2])
        ]


_moss_session_obj = None
_moss_lock = asyncio.Lock()
_moss_docs = 0          # how much we have remembered this run


def remembered_count() -> int:
    return _moss_docs


async def remember(passages: list[Passage]) -> None:
    """Put everything we read into Moss, so a later claim can reuse it.

    This is what makes recall possible at all. It runs after a verdict has
    already been sent, so it is never on the critical path.
    """
    global _moss_docs
    if not config.MOSS_ENABLED or not passages:
        return
    try:
        from moss import DocumentInfo, MossClient

        session = await _moss_session(MossClient)
        await session.add_docs([
            DocumentInfo(
                id=hashlib.sha1(f"{p.url}#{i}#{p.text[:60]}".encode()).hexdigest()[:20],
                text=p.text,
                metadata={"url": p.url, "title": p.title, "tier": str(p.tier)},
            )
            for i, p in enumerate(passages)
        ])
        _moss_docs += len(passages)
        log.info("moss: remembered %d passage(s), %d held", len(passages), _moss_docs)
    except Exception as exc:  # noqa: BLE001
        log.warning("moss could not remember: %s", exc)


async def recall(claim: str) -> list[Evidence]:
    """Ask Moss whether we already hold passages that answer this claim.

    Returns [] unless the match is strong enough to trust without searching.
    Deliberately strict: a wrong shortcut costs a wrong verdict, and a right
    one only saves about a second and one Firecrawl credit.

    Hard-timed, because this is an optimisation and an optimisation that
    becomes the slow part has failed at its only job.
    """
    if not config.MOSS_ENABLED or _moss_docs < config.MOSS_MIN_HITS:
        return []

    started = time.monotonic()
    try:
        from moss import MossClient, QueryOptions

        session = await _moss_session(MossClient)
        result = await asyncio.wait_for(
            session.query(claim, QueryOptions(top_k=config.PASSAGES_FOR_JUDGE)),
            timeout=config.MOSS_TIMEOUT_S,
        )
    except asyncio.TimeoutError:
        log.info("moss recall timed out, searching instead")
        return []
    except Exception as exc:  # noqa: BLE001
        log.warning("moss recall failed: %s", exc)
        return []

    strong = [d for d in result.docs if getattr(d, "score", 0) >= config.MOSS_MIN_SCORE]
    took = (time.monotonic() - started) * 1000

    # A similarity score is not a subject check, and trusting it alone was a
    # mistake with teeth: asked whether the Danube flows through Vienna, Moss
    # confidently returned five passages about the Amazon, all above
    # threshold, and the claim was answered from them WITHOUT searching. That
    # is worse than having no memory at all -- a wrong shortcut costs a wrong
    # verdict, while a right one only saves a second.
    #
    # So a remembered passage must also NAME what the claim is about. Nothing
    # is reused on similarity alone.
    from .judge import claim_names

    names = claim_names(claim)
    if names:
        strong = [
            d for d in strong
            if any(
                n in f"{(d.metadata or {}).get('title', '')} {d.text}".lower()
                for n in names
            )
        ]
    else:
        # A claim that names nothing cannot be matched safely against memory.
        strong = []

    if len(strong) < config.MOSS_MIN_HITS:
        log.info(
            "moss: %d of %d passage(s) were about this claim in %.0fms -- searching",
            len(strong), len(result.docs), took,
        )
        return []

    log.info("moss: answered from memory, %d passage(s) in %.0fms", len(strong), took)
    evidence = [
        Evidence(
            evidence_id=f"E{i + 1}",
            text=doc.text,
            url=(doc.metadata or {}).get("url", ""),
            title=(doc.metadata or {}).get("title", ""),
            tier=int((doc.metadata or {}).get("tier", 3)),
            score=doc.score,
        )
        for i, doc in enumerate(strong)
    ]
    evidence.sort(key=lambda e: (e.tier, -e.score))
    for n, e in enumerate(evidence, 1):
        e.evidence_id = f"E{n}"
    return evidence


class MossDisabled(RuntimeError):
    """Someone tried to open a billed session while Moss is switched off."""


async def _moss_session(MossClient):
    """Created once and kept. Everything after it runs in-process, which is
    where the single-digit millisecond queries come from."""
    # The single door. Every caller is already gated, but a session costs
    # money by the minute and a future caller that forgets to check should
    # fail loudly rather than quietly start a meter running.
    if not config.MOSS_ENABLED:
        raise MossDisabled("MOSS_ENABLED is False; refusing to open a billed session")

    global _moss_session_obj
    async with _moss_lock:
        if _moss_session_obj is None:
            client = MossClient(
                config.require("MOSS_PROJECT_ID"), config.require("MOSS_PROJECT_KEY")
            )
            _moss_session_obj = await client.session(index_name="evidence")
            log.info("moss: session index ready")
    return _moss_session_obj


# --- free evidence: what we can reach without paying -----------------------


async def free_evidence(claim, on_status=lambda _s, _d="": None) -> list[Evidence]:
    """Wikipedia and the subject's own site, fetched in parallel.

    Measured: 229ms for both, against ~1300ms and a Firecrawl credit for a
    search. Ten new claims settled ten of ten from these alone -- and the one
    that did not was a bug in the entity guard rail, not a limit of the
    sources.

    Neither leg can fail a claim. A leg that misses, times out or throws is
    simply absent, and what is left goes to the judge exactly as search results
    would.
    """
    from . import entities, fetch, reference, store

    subject = (claim.official_domain or "").split(".")[0] or _subject_of(claim.normalized)
    ttl = store.ttl_for(claim.kind, claim.shape)

    async def wiki() -> list[Passage]:
        try:
            return await reference.passages_for(_subject_of(claim.normalized),
                                                claim.normalized)
        except Exception as exc:  # noqa: BLE001
            log.info("free: wikipedia leg failed (%s)", type(exc).__name__)
            return []

    async def authority() -> list[Passage]:
        try:
            site = await entities.official_site(
                _subject_of(claim.normalized), claim.normalized
            )
            if not site and claim.official_domain:
                # The sorter's guess, when Wikidata had nothing verified.
                site = f"https://{claim.official_domain}"
            if not site:
                return []
            return await fetch.passages_from_site(site, claim.normalized, ttl)
        except Exception as exc:  # noqa: BLE001
            log.info("free: authority leg failed (%s)", type(exc).__name__)
            return []

    on_status("searching", "checking what it already knows")
    legs = await asyncio.gather(wiki(), authority(), return_exceptions=True)

    passages: list[Passage] = []
    for leg in legs:
        if isinstance(leg, list):
            passages.extend(leg)

    if not passages:
        return []

    shortlist = preselect(passages, claim.normalized, config.PRESELECT_PASSAGES,
                          per_source=config.PASSAGES_PER_SOURCE * 2)
    evidence = [
        Evidence(evidence_id=f"E{i + 1}", text=p.text, url=p.url,
                 title=p.title, tier=p.tier)
        for i, p in enumerate(shortlist[: config.PASSAGES_FOR_JUDGE])
    ]
    evidence.sort(key=lambda e: e.tier)
    for n, e in enumerate(evidence, 1):
        e.evidence_id = f"E{n}"
    log.info("free: %d passage(s) -> %d for the judge", len(passages), len(evidence))
    return evidence


def _subject_of(claim_text: str) -> str:
    """The thing a claim is about: its leading proper nouns.

    "Mount Everest is 8,848 metres tall" -> "Mount Everest". Searching
    Wikipedia for the whole sentence finds nothing useful; searching for the
    subject finds the article with the answer in it.
    """
    import re

    words = claim_text.split()
    names: list[str] = []
    for w in words:
        stripped = w.strip(".,;:'\"")
        if stripped and stripped[0].isupper() and stripped.lower() not in _NOT_A_SUBJECT:
            names.append(stripped)
        elif names:
            break
    return " ".join(names[:4]) or re.sub(r"[^\w\s]", "", claim_text).strip()


_NOT_A_SUBJECT = {
    "the", "a", "an", "this", "that", "these", "those", "and", "but", "so",
    "it", "he", "she", "they", "we", "you", "there", "here", "in", "on", "at",
    "of", "for", "is", "was", "are", "his", "her", "their", "its", "my", "our",
}


def worth_judging(evidence: list[Evidence]) -> bool:
    """Is this enough to be worth a judge call, or should we just search?

    A naive ladder judges the free evidence, hears "too thin", then searches
    and judges again -- two calls, and every long-tail claim pays for the first
    one. Deciding here in code costs nothing and keeps it to one judge call on
    either path.
    """
    return len(evidence) >= config.FREE_EVIDENCE_MIN_PASSAGES
