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


async def search(query: str, claim: str, official_domain: str = "", on_status=None) -> list[Hit]:
    """Search, tier the results, and nudge towards whoever owns the fact.

    When there is an official domain this fires two or three searches. They
    used to run one after another, which cost nearly two seconds to do under
    one second of work -- they do not depend on each other, so they go
    together.
    """
    queries = [query]
    guesses: list[Hit] = []

    if official_domain:
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
    for batch in results:
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


async def _moss_session(MossClient):
    """Created once and kept. Everything after it runs in-process, which is
    where the single-digit millisecond queries come from."""
    global _moss_session_obj
    async with _moss_lock:
        if _moss_session_obj is None:
            client = MossClient(
                config.require("MOSS_PROJECT_ID"), config.require("MOSS_PROJECT_KEY")
            )
            _moss_session_obj = await client.session(index_name="evidence")
            log.info("moss: session index ready")
    return _moss_session_obj
