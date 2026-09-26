"""Drive a scripted conversation through the real pipeline and keep the recording.

    python scripts/record_demo.py                  # against a running server
    python scripts/record_demo.py --save           # also copy to tests/fixtures/

This is the demo insurance. It runs real claims against the real web, records
every message with its real timing, and the result plays back through
scripts/replay.py at its original speed with no network at all.

Three reasons that matters more than it sounds:

  * the venue wifi will be bad, and a recorded demo still works
  * the demo video is shot against a recording, so the timings in it are real
    rather than staged
  * it is the only regression test that covers the whole system end to end

The script deliberately covers every branch the UI has to render: a true
claim, a false one with a correction, pure buzzwords, and small talk that is
skipped for free.
"""

from __future__ import annotations

import argparse
import asyncio
import json
import shutil
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

import websockets  # noqa: E402

from server import config  # noqa: E402

URL = "ws://127.0.0.1:8000/ws"
FIXTURES = config.ROOT / "tests" / "fixtures"

# Said in this order, with these gaps, so the recording has the rhythm of a
# real conversation rather than a queue being drained.
SCRIPT = [
    ("So I was reading that Notion charges about five hundred dollars per user per month.", 7.0),
    ("This product will revolutionize the market through cross functional synergy.", 6.0),
    ("How's it going?", 4.0),
    ("Usain Bolt ran the one hundred metres in 9.58 seconds.", 9.0),
]

GREEN, RED, DIM, BOLD, RESET = "\033[32m", "\033[31m", "\033[2m", "\033[1m", "\033[0m"


async def main(save: bool) -> int:
    seen: dict[str, dict] = {}
    started = time.monotonic()

    async with websockets.connect(URL) as ws:
        session_id = None

        async def reader():
            nonlocal session_id
            async for raw in ws:
                msg = json.loads(raw)
                t = time.monotonic() - started

                if msg["type"] == "session.ready":
                    session_id = msg["session_id"]
                elif msg["type"] == "claim.detected":
                    seen[msg["claim_id"]] = {"quote": msg["quote"], "t": t}
                    print(f"{DIM}{t:6.2f}s{RESET} claim {msg['claim_id']}: {msg['normalized'][:70]}")
                elif msg["type"] == "claim.status":
                    print(f"{DIM}{t:6.2f}s   {msg['stage']}: {msg['detail']}{RESET}")
                elif msg["type"] == "claim.evidence":
                    print(f"{DIM}{t:6.2f}s   {len(msg['items'])} source(s), depth={msg['depth']}{RESET}")
                elif msg["type"] == "window.skipped":
                    print(f"{DIM}{t:6.2f}s   skipped: {msg['reason']}{RESET}")
                elif msg["type"] == "claim.verdict":
                    colour = GREEN if msg["verdict"] == "SUPPORTED" else RED
                    took = msg["took_ms"] / 1000
                    print(f"{t:6.2f}s {colour}{BOLD}{msg['sticker']}{RESET} "
                          f"({msg['stage']}, {msg['depth']}, {took:.1f}s) {msg['summary'][:80]}")
                    if msg.get("correction"):
                        print(f"        {DIM}actually: {msg['correction']}{RESET}")
                    seen.setdefault(msg["claim_id"], {})["verdict"] = msg["verdict"]
                elif msg["type"] == "claim.error":
                    print(f"{t:6.2f}s {RED}COULDN'T CHECK{RESET} ({msg['stage']}) {msg['message'][:70]}")

        task = asyncio.create_task(reader())
        await asyncio.sleep(0.5)

        for sentence, gap in SCRIPT:
            print(f"\n{BOLD}>> {sentence}{RESET}")
            await ws.send(json.dumps({"type": "inject_text", "text": sentence}))
            await asyncio.sleep(gap)

        print(f"\n{DIM}letting anything still in flight land...{RESET}")
        await asyncio.sleep(12)
        task.cancel()

    print(f"\n{BOLD}{len(seen)} claim(s){RESET}")
    for cid, info in seen.items():
        print(f"  {cid}: {info.get('verdict', 'no verdict')}")

    if not save:
        print(f"\n{DIM}run again with --save to keep this as a fixture{RESET}")
        return 0

    # The server writes every session to recordings/ already; take the newest.
    found = sorted(config.RECORDINGS_DIR.glob("*.jsonl"), key=lambda p: p.stat().st_mtime)
    if not found:
        print(f"{RED}no recording found -- is RECORD_SESSIONS on?{RESET}")
        return 1

    FIXTURES.mkdir(parents=True, exist_ok=True)
    target = FIXTURES / "real_session.jsonl"
    shutil.copy(found[-1], target)
    count = len([l for l in target.read_text().splitlines() if l.strip()])
    print(f"\n{GREEN}saved{RESET} {target.relative_to(config.ROOT)}: {count} messages")
    print(f"{DIM}play it back with: python scripts/replay.py {target.relative_to(config.ROOT)}{RESET}")
    return 0


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--save", action="store_true", help="copy to tests/fixtures/")
    args = parser.parse_args()
    raise SystemExit(asyncio.run(main(args.save)))
