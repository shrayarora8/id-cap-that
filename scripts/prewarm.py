"""Run a script through the pipeline in advance, so the demo costs nothing.

    python scripts/prewarm.py demo/script.txt
    python scripts/prewarm.py --check demo/script.txt     # what is already warm

Both caches are on disk and keyed on content: Claude answers in .cache/llm,
searches and pages in .cache/web. Running the demo script once ahead of time
fills them, and then on the day every claim in it resolves from disk with
**zero API calls and zero Firecrawl credits**, in well under two seconds.

This is the single most valuable thing for the demo, for three reasons:

  * Firecrawl's free tier allows ten requests a minute. A person talking
    normally produces claims faster than that, so a live scripted run queues
    and some claims take half a minute. Warm, none of them touch the network.
  * It removes the venue wifi from the critical path entirely.
  * It makes the demo's timings repeatable, so the thing you rehearse is the
    thing that happens.

It is not cheating and should not be hidden: the answers were fetched from
the live web, they are simply fetched earlier. Anything said off-script still
goes out to the internet exactly as normal, which is worth showing.
"""

from __future__ import annotations

import argparse
import asyncio
import json
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

import websockets  # noqa: E402

from server import config  # noqa: E402

URL = "ws://127.0.0.1:8000/ws"
GREEN, RED, DIM, BOLD, RESET = "\033[32m", "\033[31m", "\033[2m", "\033[1m", "\033[0m"


def lines_of(path: Path) -> list[str]:
    out = []
    for raw in path.read_text().splitlines():
        line = raw.strip()
        if line and not line.startswith("#"):
            out.append(line)
    return out


def cache_size() -> tuple[int, int]:
    llm = len(list((config.ROOT / ".cache" / "llm").glob("*.json")))
    web = len(list((config.ROOT / ".cache" / "web").glob("*.json")))
    return llm, web


async def run(lines: list[str], pace: float) -> dict:
    """Feed the script through a real session and collect what came back."""
    seen: dict[str, dict] = {}

    async with websockets.connect(URL) as ws:
        async def reader():
            async for raw in ws:
                msg = json.loads(raw)
                if msg["type"] == "claim.detected":
                    seen[msg["claim_id"]] = {"claim": msg["normalized"]}
                elif msg["type"] == "claim.verdict":
                    seen.setdefault(msg["claim_id"], {})["sticker"] = msg["sticker"]
                    seen[msg["claim_id"]]["took"] = msg["took_ms"] / 1000
                elif msg["type"] == "claim.error":
                    seen.setdefault(msg["claim_id"], {})["sticker"] = f"ERROR:{msg['stage']}"
                    seen[msg["claim_id"]]["took"] = 0.0

        task = asyncio.create_task(reader())
        await asyncio.sleep(0.4)
        for line in lines:
            await ws.send(json.dumps({"type": "inject_text", "text": line}))
            await asyncio.sleep(pace)

        # Warming deliberately waits as long as it takes. Rate-limit queuing
        # is exactly what we are paying now so the demo does not pay it later.
        print(f"{DIM}waiting for everything in flight...{RESET}")
        for _ in range(24):
            await asyncio.sleep(5)
            if seen and all("sticker" in v for v in seen.values()):
                break
        task.cancel()
    return seen


async def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("script", help="a text file, one spoken line per line")
    parser.add_argument("--check", action="store_true", help="report only, do not warm")
    parser.add_argument("--pace", type=float, default=2.5, help="seconds between lines")
    args = parser.parse_args()

    path = Path(args.script)
    if not path.exists():
        print(f"{RED}no such file: {path}{RESET}")
        return 1

    lines = lines_of(path)
    before = cache_size()
    pace = 0.8 if args.check else args.pace

    print(f"{BOLD}{'checking' if args.check else 'warming'}{RESET} {path.name}: {len(lines)} line(s)")
    print(f"{DIM}cache before: {before[0]} llm, {before[1]} web{RESET}\n")

    started = time.monotonic()
    seen = await run(lines, pace)
    took = time.monotonic() - started
    after = cache_size()

    slow = 0
    for info in seen.values():
        sticker = info.get("sticker", "*** never resolved ***")
        t = info.get("took", 0.0)
        if t > 2.5:
            slow += 1
        colour = RED if t > 2.5 or "ERROR" in sticker or "never" in sticker else GREEN
        print(f"  {colour}{sticker:<24}{RESET} {t:5.1f}s  {DIM}{info.get('claim','?')[:58]}{RESET}")

    print(f"\n{len(seen)} claim(s) in {took:.0f}s")
    print(f"{DIM}cache after: {after[0]} llm (+{after[0]-before[0]}), "
          f"{after[1]} web (+{after[1]-before[1]}){RESET}")

    if args.check:
        if slow:
            print(f"\n{RED}{slow} claim(s) took over 2.5s -- not warm.{RESET} "
                  f"Run without --check.")
            return 1
        print(f"\n{GREEN}All warm.{RESET} This script will run from disk with no API calls.")
        return 0

    print(f"\n{GREEN}Warmed.{RESET} Verify with:")
    print(f"  {DIM}python scripts/prewarm.py --check {path}{RESET}")
    return 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
