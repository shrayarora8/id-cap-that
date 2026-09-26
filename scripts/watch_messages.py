"""Watch the whole system behave as a stream of text, with no browser open.

    python scripts/watch_messages.py "Notion charges 500 dollars per user per month."

Connects to the running server, injects each sentence you pass as if the
microphone had heard it, and prints every message that comes back with the
elapsed time. This is the fastest way to see what the page would see.
"""

from __future__ import annotations

import asyncio
import json
import sys
import time

import websockets

URL = "ws://127.0.0.1:8000/ws"

DIM, BOLD, RESET = "\033[2m", "\033[1m", "\033[0m"
COLOUR = {
    "server.note": "\033[36m",
    "session.ready": "\033[35m",
    "budget.update": "\033[35m",
    "transcript.final": "\033[37m",
    "transcript.interim": "\033[2m",
    "window.ready": "\033[34m",
    "window.skipped": "\033[2m",
    "claim.detected": "\033[33m",
    "claim.status": "\033[2m",
    "claim.verdict": "\033[32m",
    "claim.error": "\033[31m",
}


def show(msg: dict, t0: float) -> None:
    kind = msg.get("type", "?")
    colour = COLOUR.get(kind, "")
    rest = {
        k: v for k, v in msg.items() if k not in ("type", "ts", "seq")
    }
    body = json.dumps(rest, ensure_ascii=False)
    if len(body) > 150:
        body = body[:147] + "…"
    elapsed = time.monotonic() - t0
    print(f"{DIM}{elapsed:6.2f}s  seq{msg.get('seq', 0):<3}{RESET} {colour}{kind:<20}{RESET} {body}")


async def main(sentences: list[str]) -> int:
    t0 = time.monotonic()
    async with websockets.connect(URL) as ws:

        async def reader() -> None:
            async for raw in ws:
                show(json.loads(raw), t0)

        task = asyncio.create_task(reader())
        await asyncio.sleep(0.4)

        for sentence in sentences:
            print(f"\n{BOLD}>> {sentence}{RESET}")
            await ws.send(json.dumps({"type": "inject_text", "text": sentence}))
            await asyncio.sleep(1.2)

        # Let anything still in flight land.
        await asyncio.sleep(float(sys.argv[-1]) if sys.argv[-1].replace(".", "").isdigit() else 6.0)
        task.cancel()
    return 0


if __name__ == "__main__":
    args = [a for a in sys.argv[1:] if not a.replace(".", "").isdigit()]
    if not args:
        args = ["Notion charges about five hundred dollars per user per month."]
    raise SystemExit(asyncio.run(main(args)))
