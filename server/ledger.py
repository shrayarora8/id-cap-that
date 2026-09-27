"""What visitors have spent, remembered across restarts.

The per-session cap was never enough on its own. It resets on every reconnect,
so a refresh hands out a fresh allowance, and nothing counted the total across
everybody. Sharing a link with that in place is an open tab on someone else's
account.

This is the ceiling. It lives on disk so a restart does not forget it, and it
covers only visitors: the machine running the demo is on loopback and spends
from its own reserve, so a room full of judges can never leave Shray unable to
demo the thing they came to see.
"""

from __future__ import annotations

import json
import logging
import time
from datetime import date

from . import config

log = logging.getLogger(__name__)

LEDGER = config.ROOT / ".cache" / "spend.json"


def _load() -> dict:
    try:
        data = json.loads(LEDGER.read_text())
    except Exception:  # noqa: BLE001 - a missing or corrupt ledger starts fresh
        data = {}
    month = date.today().strftime("%Y-%m")
    if data.get("month") != month:
        # Firecrawl's allowance is monthly, so the ceiling is too.
        return {"month": month, "public_credits": 0, "public_claims": 0}
    return data


def _save(data: dict) -> None:
    LEDGER.parent.mkdir(parents=True, exist_ok=True)
    LEDGER.write_text(json.dumps(data))


def public_spent() -> int:
    return _load().get("public_credits", 0)


def public_left() -> int:
    return max(0, config.PUBLIC_CREDIT_CEILING - public_spent())


def public_exhausted() -> bool:
    return public_left() <= 0


def record_public_spend(credits: int) -> None:
    """Count what a visitor just cost. Called after the work, not before."""
    if credits <= 0:
        return
    data = _load()
    data["public_credits"] = data.get("public_credits", 0) + credits
    data["public_claims"] = data.get("public_claims", 0) + 1
    data["updated"] = int(time.time())
    _save(data)
    left = max(0, config.PUBLIC_CREDIT_CEILING - data["public_credits"])
    log.info(
        "visitor spend: +%d credits, %d of %d used, %d left",
        credits, data["public_credits"], config.PUBLIC_CREDIT_CEILING, left,
    )


def summary() -> dict:
    data = _load()
    return {
        "month": data.get("month"),
        "public_credits": data.get("public_credits", 0),
        "public_claims": data.get("public_claims", 0),
        "ceiling": config.PUBLIC_CREDIT_CEILING,
        "left": public_left(),
    }
