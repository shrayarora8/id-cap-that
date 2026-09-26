"""Play a recorded session back into the live UI, at its original speed.

    python scripts/replay.py                      # the most recent recording
    python scripts/replay.py recordings/x.jsonl
    python scripts/replay.py --speed 2            # twice as fast
    python scripts/replay.py --list

Every session writes itself to recordings/. This plays one back with the exact
rhythm it originally had, over a normal WebSocket, so the page cannot tell the
difference. Three reasons that matters:

  1. The UI can be built and tuned without talking, and without spending a
     single credit.
  2. A bug that only happens after nine seconds of a particular conversation
     can be reproduced exactly, as many times as you like.
  3. When the venue wifi dies five minutes before the demo, there is still a
     demo.

Point a browser at the server and run this; the page fills in as if someone
were speaking into it.
"""

from __future__ import annotations

import argparse
import asyncio
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from fastapi import FastAPI, WebSocket, WebSocketDisconnect  # noqa: E402
from fastapi.responses import FileResponse  # noqa: E402
from fastapi.staticfiles import StaticFiles  # noqa: E402

ROOT = Path(__file__).parent.parent
WEB_DIR = ROOT / "web"
RECORDINGS = ROOT / "recordings"


def recordings() -> list[Path]:
    return sorted(RECORDINGS.glob("*.jsonl"), key=lambda p: p.stat().st_mtime)


def latest() -> Path | None:
    found = recordings()
    return found[-1] if found else None


def load(path: Path) -> list[dict]:
    out = []
    for line in path.read_text().splitlines():
        line = line.strip()
        if line:
            out.append(json.loads(line))
    return out


def build_app(messages: list[dict], speed: float) -> FastAPI:
    app = FastAPI(title="replay")

    @app.get("/health")
    async def health():
        return {"ok": True, "replay": True, "messages": len(messages)}

    @app.get("/")
    async def index():
        return FileResponse(WEB_DIR / "index.html")

    @app.get("/sw.js")
    async def service_worker():
        """Served explicitly because a StaticFiles mount at "/" does not pick
        it up here the way the real server does, and a 404 puts a service
        worker registration failure in the console -- which is noise in a
        demo recording."""
        return FileResponse(WEB_DIR / "sw.js", media_type="text/javascript")

    @app.websocket("/ws")
    async def ws_endpoint(ws: WebSocket) -> None:
        await ws.accept()
        print(f"page connected, replaying {len(messages)} messages at {speed}x")
        previous = 0.0
        try:
            for msg in messages:
                gap = (msg.get("_t", previous) - previous) / speed
                if gap > 0:
                    await asyncio.sleep(min(gap, 10.0))
                previous = msg.get("_t", previous)

                out = {k: v for k, v in msg.items() if k != "_t"}
                await ws.send_json(out)
                print(f"  {previous:6.2f}s  {out.get('type')}")
            print("replay finished; the page keeps whatever it drew")
            while True:
                await asyncio.sleep(3600)
        except (WebSocketDisconnect, asyncio.CancelledError):
            pass

    app.mount("/", StaticFiles(directory=WEB_DIR), name="web")
    return app


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("recording", nargs="?", help="a .jsonl in recordings/")
    parser.add_argument("--speed", type=float, default=1.0)
    parser.add_argument("--port", type=int, default=8001)
    parser.add_argument("--list", action="store_true")
    args = parser.parse_args()

    if args.list:
        found = recordings()
        if not found:
            print("no recordings yet -- run the server and say something")
            return 1
        for p in found:
            count = len(load(p))
            print(f"{p.name}  {count} messages  {p.stat().st_size / 1024:.1f} KB")
        return 0

    path = Path(args.recording) if args.recording else latest()
    if path is None or not path.exists():
        print("no recording found. Run the server, talk, then try again.")
        return 1

    messages = load(path)
    if not messages:
        print(f"{path.name} is empty")
        return 1

    import uvicorn

    print(f"replaying {path.name}: {len(messages)} messages, {args.speed}x")
    print(f"open http://127.0.0.1:{args.port}")
    uvicorn.run(build_app(messages, args.speed), host="0.0.0.0", port=args.port, log_level="warning")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
