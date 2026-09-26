"""Local verification of every case Shray reported broken, plus regressions."""
import asyncio, json, sys, time
import websockets

CASES = [
    ("Taylor Swift has won 28 Grammys.",            "ABSOLUTE CAP", "was 54.5s"),
    ("Max Verstappen holds the record for the most championships.", "any", "was 3 stickers"),
    ("Fifty seconds.",                              "NOTHING",      "was a bogus NO CAP"),
    ("Taking too long.",                            "NOTHING",      "was WORD SALAD"),
    ("This product will revolutionize the market through cross functional synergy.", "WORD SALAD", "must still fire"),
    ("Usain Bolt ran the one hundred metres in 9.58 seconds.", "NO CAP", "regression check"),
    ("Snowflake is the best database in the world.",  "WORD SALAD", "was ignored entirely"),
    ("Taylor Swift dated Tom Holland.",               "any",        "was NO CAP off a Zendaya page"),
]

async def main():
    results = []
    for sentence, expect, why in CASES:
        async with websockets.connect("ws://127.0.0.1:8000/ws") as ws:
            t0 = time.monotonic()
            got = {"stickers": [], "skipped": None, "claims": 0, "t": None}

            async def reader():
                async for raw in ws:
                    m = json.loads(raw)
                    if m["type"] == "claim.detected":
                        got["claims"] += 1
                    elif m["type"] == "claim.verdict":
                        got["stickers"].append(m["sticker"])
                        got["t"] = time.monotonic() - t0
                    elif m["type"] == "window.skipped":
                        got["skipped"] = m["reason"]
                    elif m["type"] == "claim.error":
                        got["stickers"].append(f"ERROR:{m['stage']}")

            task = asyncio.create_task(reader())
            await asyncio.sleep(0.3)
            await ws.send(json.dumps({"type": "inject_text", "text": sentence}))
            await asyncio.sleep(16)
            task.cancel()

        stickers = got["stickers"]
        if expect == "NOTHING":
            ok = not stickers
            actual = f"skipped: {got['skipped']}" if got["skipped"] else (", ".join(stickers) or "nothing")
        elif expect == "any":
            ok = len(stickers) == 1
            actual = f"{len(stickers)} sticker(s): {', '.join(stickers)}"
        else:
            ok = stickers == [expect]
            actual = ", ".join(stickers) or "nothing"

        took = f"{got['t']:.1f}s" if got["t"] else "-"
        mark = "\033[32mPASS\033[0m" if ok else "\033[31mFAIL\033[0m"
        results.append(ok)
        print(f"{mark} {took:>6}  {sentence[:52]:<54} {actual}   \033[2m({why})\033[0m")

    print()
    print(f"{sum(results)}/{len(results)} passed")
    return 0 if all(results) else 1

sys.exit(asyncio.run(main()))
