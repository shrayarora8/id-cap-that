"""Build a synthetic session recording, for developing the UI before the
pipeline that would produce a real one exists.

    python scripts/make_fixture.py

Writes tests/fixtures/synthetic_session.jsonl. Every message is produced by
the real builders in server/messages.py, so the fixture cannot drift from the
contract -- if a builder changes shape, regenerating this file changes with it.

IT IS NOT EVIDENCE THAT ANYTHING WORKS. The verdicts here were written by
hand. It exists so the page can be built against the three branches that are
otherwise unreachable until stage 6:

  * a provisional verdict that CHANGES when it is confirmed
  * a claim.error
  * the demo budget running out

Replace it with a genuine recorded run as soon as the pipeline produces one.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from server import messages as m  # noqa: E402

OUT = Path(__file__).parent.parent / "tests" / "fixtures" / "synthetic_session.jsonl"

script: list[tuple[float, dict]] = []
_seq = 0


def at(t: float, msg: dict) -> None:
    global _seq
    _seq += 1
    msg["seq"] = _seq
    msg["_t"] = t
    script.append((t, msg))


# --- a session opens --------------------------------------------------------
at(0.00, m.session_ready("sess_fixture", m.PROTOCOL_VERSION,
                         {"claims_left": 3, "claims_cap": 3, "pool": "public"},
                         m.AUDIO_FORMAT))
at(0.02, m.server_note("connected"))
at(0.30, m.server_note("listening"))

# --- 1. a claim whose provisional verdict CHANGES on confirmation -----------
at(2.10, m.transcript_interim("so i was reading that notion charges"))
at(3.10, m.transcript_final("s1", "So I was reading that Notion charges"))
at(4.20, m.transcript_interim("about five hundred dollars per user"))
at(5.30, m.transcript_final("s2", "about five hundred dollars per user per month."))
at(6.30, m.window_ready("w1", ["s1", "s2"],
                        "So I was reading that Notion charges about five hundred "
                        "dollars per user per month.", "utterance_end"))
at(7.60, m.claim_detected(
    claim_id="c1", window_id="w1",
    spans=[{"segment_id": "s1", "start": 22, "end": 36},
           {"segment_id": "s2", "start": 0, "end": 45}],
    quote="Notion charges about five hundred dollars per user per month",
    normalized="Notion charges about $500 per user per month.",
    kind="world_fact", hedge="stated", shape="count", checkable=True,
    search_query="Notion pricing per user per month",
))
at(7.65, m.claim_status("c1", "searching", "searching notion.com"))
at(9.20, m.claim_status("c1", "judging", "weighing 4 snippets"))
at(9.40, m.claim_evidence("c1", [
    m.evidence_item("E1", "https://notion.com/pricing", "Pricing – Notion", 1,
                    "Plus $12 per seat/month billed annually. Business $20 per "
                    "seat/month billed annually. Enterprise: contact sales."),
    m.evidence_item("E2", "https://www.g2.com/products/notion/pricing",
                    "Notion Pricing 2026", 3,
                    "Notion offers a free tier plus paid plans starting around $12."),
], depth="snippets"))
# The fast read: right direction, thin evidence.
at(10.30, m.claim_verdict(
    "c1", "CONTRADICTED", m.STICKERS["CONTRADICTED"],
    "Notion's own pricing page lists seat prices far below $500.",
    stage="provisional", depth="snippets",
    citations=[m.citation("E1", "Business $20 per seat/month billed annually")],
    took_ms=3400, timings={"extract": 1300, "search": 1550, "judge": 550},
    correction="$20 per seat per month", confidence="high",
))
at(10.35, m.claim_status("c1", "escalating", "reading notion.com in full"))
at(13.80, m.claim_evidence("c1", [
    m.evidence_item("E1", "https://notion.com/pricing", "Pricing – Notion", 1,
                    "Business - $20 - per seat/month billed annually - "
                    "Advanced permissions, SAML SSO, private teamspaces."),
    m.evidence_item("E2", "https://notion.com/pricing", "Pricing – Notion", 1,
                    "Enterprise - Contact sales - for organisations that need "
                    "advanced controls and support."),
], depth="pages"))
# Confirmed: same verdict, but now it is a read of the actual page. The page
# should firm the sticker up rather than flip it.
at(15.10, m.claim_verdict(
    "c1", "CONTRADICTED", m.STICKERS["CONTRADICTED"],
    "Notion's pricing page lists Business at $20 per seat per month, not $500.",
    stage="confirmed", depth="pages",
    citations=[m.citation("E1", "Business - $20 - per seat/month billed annually")],
    took_ms=8100, timings={"extract": 1300, "search": 1550, "judge": 550,
                           "escalate": 3450, "rejudge": 1250},
    correction="$20 per seat per month", confidence="high",
))

# --- 2. fluff: instant, never searches --------------------------------------
at(11.40, m.transcript_final("s3", "This product will revolutionize the market"))
at(12.80, m.transcript_final("s4", "through cross functional synergy."))
at(13.10, m.window_ready("w2", ["s3", "s4"],
                         "This product will revolutionize the market through "
                         "cross functional synergy.", "utterance_end"))
at(14.00, m.claim_detected(
    claim_id="c2", window_id="w2",
    spans=[{"segment_id": "s3", "start": 0, "end": 42},
           {"segment_id": "s4", "start": 0, "end": 32}],
    quote="This product will revolutionize the market through cross functional synergy",
    normalized="This product will revolutionise the market through cross functional synergy.",
    kind="fluff", hedge="stated", shape="other", checkable=False,
    note="pure buzzwords, nothing evidence could settle",
))
at(14.01, m.claim_verdict(
    "c2", "NOT_FACT_CHECKABLE", m.STICKERS["NOT_FACT_CHECKABLE"],
    "pure buzzwords, nothing evidence could settle",
    stage="confirmed", depth="snippets", took_ms=900,
    timings={"extract": 900},
))

# --- 3. small talk: skipped for free ----------------------------------------
at(15.40, m.transcript_final("s5", "How's it going?"))
at(17.90, m.window_ready("w3", ["s5"], "How's it going?", "hard_silence"))
at(17.91, m.window_skipped("w3", "small talk"))

# --- 4. a claim that fails mid-check ----------------------------------------
at(19.20, m.transcript_final("s6", "Messi scored 45 goals last season."))
at(20.30, m.window_ready("w4", ["s6"], "Messi scored 45 goals last season.",
                         "utterance_end"))
at(21.50, m.claim_detected(
    claim_id="c3", window_id="w4",
    spans=[{"segment_id": "s6", "start": 0, "end": 33}],
    quote="Messi scored 45 goals last season",
    normalized="Lionel Messi scored 45 goals in the 2025 season.",
    kind="world_fact", hedge="stated", shape="count", checkable=True,
    search_query="Lionel Messi goals 2025 season total",
))
at(21.55, m.claim_status("c3", "searching", "searching the web"))
at(24.80, m.claim_error("c3", "check", "search timed out after 6s"))

# --- 5. the budget runs out -------------------------------------------------
at(26.10, m.transcript_final("s7", "And apparently Apple sold 240 million iPhones."))
at(27.40, m.window_ready("w5", ["s7"],
                         "And apparently Apple sold 240 million iPhones.",
                         "utterance_end"))
at(28.60, m.claim_detected(
    claim_id="c4", window_id="w5",
    spans=[{"segment_id": "s7", "start": 15, "end": 45}],
    quote="Apple sold 240 million iPhones",
    normalized="Apple sold 240 million iPhones.",
    kind="world_fact", hedge="hedged", shape="count", checkable=True,
    search_query="Apple iPhone units sold 2025",
))
at(28.62, m.claim_error("c4", "budget", "demo budget used up"))
at(28.63, m.budget_update(claims_left=0, claims_cap=3, pool="public",
                          exhausted=True,
                          note="add your own keys to keep going"))


def main() -> int:
    OUT.parent.mkdir(parents=True, exist_ok=True)
    with OUT.open("w") as f:
        for _, msg in sorted(script, key=lambda pair: pair[0]):
            f.write(json.dumps(msg) + "\n")
    print(f"wrote {OUT.relative_to(Path.cwd())}: {len(script)} messages")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
