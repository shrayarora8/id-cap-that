"""Are the five keys present, and do they actually work?

Run this first, and any time something inexplicable starts happening. It is
deliberately free: every check either reads account metadata or lists models.
Nothing here spends a Firecrawl credit or an Anthropic token, so you can run
it as often as you like.

    .venv/bin/python scripts/check_keys.py
"""

from __future__ import annotations

import asyncio
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

import httpx
from dotenv import load_dotenv

load_dotenv(Path(__file__).parent.parent / ".env")

GREEN, RED, YELLOW, DIM, RESET = "\033[32m", "\033[31m", "\033[33m", "\033[2m", "\033[0m"


def ok(name: str, detail: str = "") -> None:
    print(f"[  {GREEN}ok{RESET}  ] {name:<12} {DIM}{detail}{RESET}")


def fail(name: str, detail: str) -> None:
    print(f"[ {RED}fail{RESET} ] {name:<12} {detail}")


def warn(name: str, detail: str) -> None:
    print(f"[ {YELLOW}warn{RESET} ] {name:<12} {detail}")


async def check_anthropic() -> bool:
    key = os.getenv("ANTHROPIC_API_KEY", "").strip()
    if not key:
        fail("anthropic", "ANTHROPIC_API_KEY missing from .env")
        return False
    try:
        async with httpx.AsyncClient(timeout=10) as c:
            r = await c.get(
                "https://api.anthropic.com/v1/models",
                headers={"x-api-key": key, "anthropic-version": "2023-06-01"},
            )
        if r.status_code != 200:
            fail("anthropic", f"HTTP {r.status_code}: {r.text[:120]}")
            return False
        names = [m["id"] for m in r.json().get("data", [])]
        haiku = [n for n in names if "haiku" in n]
        ok("anthropic", f"{len(names)} models, haiku: {haiku[0] if haiku else 'none found'}")
        return True
    except Exception as exc:  # noqa: BLE001
        fail("anthropic", str(exc)[:120])
        return False


async def check_deepgram() -> bool:
    key = os.getenv("DEEPGRAM_API_KEY", "").strip()
    if not key:
        fail("deepgram", "DEEPGRAM_API_KEY missing from .env")
        return False
    try:
        async with httpx.AsyncClient(timeout=10) as c:
            r = await c.get(
                "https://api.deepgram.com/v1/projects",
                headers={"Authorization": f"Token {key}"},
            )
        if r.status_code != 200:
            fail("deepgram", f"HTTP {r.status_code}: {r.text[:120]}")
            return False
        projects = r.json().get("projects", [])
        ok("deepgram", f"{len(projects)} project(s)")
        return True
    except Exception as exc:  # noqa: BLE001
        fail("deepgram", str(exc)[:120])
        return False


async def check_firecrawl() -> bool:
    """Also reports the remaining credits, which is the number that decides
    how much of the demo is live and how much is served from cache."""
    key = os.getenv("FIRECRAWL_API_KEY", "").strip()
    if not key:
        fail("firecrawl", "FIRECRAWL_API_KEY missing from .env")
        return False
    try:
        async with httpx.AsyncClient(timeout=10) as c:
            r = await c.get(
                "https://api.firecrawl.dev/v2/team/credit-usage",
                headers={"Authorization": f"Bearer {key}"},
            )
        if r.status_code != 200:
            fail("firecrawl", f"HTTP {r.status_code}: {r.text[:120]}")
            return False
        data = r.json().get("data", {})
        left = data.get("remaining_credits", data.get("remainingCredits", "?"))
        ok("firecrawl", f"{left} credits remaining, 10 requests/minute")
        return True
    except Exception as exc:  # noqa: BLE001
        fail("firecrawl", str(exc)[:120])
        return False


async def check_moss() -> bool:
    if not os.getenv("MOSS_PROJECT_ID", "").strip():
        fail("moss", "MOSS_PROJECT_ID missing from .env")
        return False
    if not os.getenv("MOSS_PROJECT_KEY", "").strip():
        fail("moss", "MOSS_PROJECT_KEY missing from .env")
        return False
    try:
        import moss  # noqa: F401
    except ImportError:
        warn("moss", "keys present, but the `moss` package is not installed yet")
        return True
    ok("moss", "keys present, package importable")
    return True


async def main() -> int:
    env = Path(__file__).parent.parent / ".env"
    if not env.exists():
        print(f"{RED}No .env file.{RESET} Copy .env.example to .env and fill it in.")
        return 1

    print(f"{DIM}checking keys in {env}{RESET}\n")
    results = await asyncio.gather(
        check_anthropic(), check_deepgram(), check_firecrawl(), check_moss()
    )
    print()
    if all(results):
        print(f"{GREEN}All good.{RESET} Start the server with:")
        print(f"  {DIM}.venv/bin/uvicorn server.main:app --reload --port 8000{RESET}")
        return 0
    print(f"{RED}Some checks failed.{RESET} Fix those before building on top of them.")
    return 1


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
