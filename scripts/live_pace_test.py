"""How does it behave at a REAL conversational pace, with cold caches?
A judge talking normally leaves a few seconds between claims."""
import asyncio, json, time, websockets

# Spoken at a natural pace: a claim roughly every 6 seconds, with filler.
SCRIPT = [
 ("Hey, so I've been looking at some tools.", 3),
 ("Notion costs eight dollars per seat per month.", 6),
 ("Yeah it's not bad.", 3),
 ("Usain Bolt ran the hundred metres in 9.58 seconds.", 6),
 ("Pretty incredible really.", 3),
 ("Mount Everest is nine thousand metres tall.", 6),
 ("And the iPhone came out in 2010.", 6),
 ("Taylor Swift has won twenty-eight Grammys.", 6),
]

async def main():
    t0 = time.monotonic()
    rows = {}
    async with websockets.connect("ws://127.0.0.1:8000/ws") as ws:
        async def r():
            async for raw in ws:
                m = json.loads(raw)
                if m["type"] == "claim.detected":
                    rows[m["claim_id"]] = {"c": m["normalized"], "t0": time.monotonic()-t0}
                elif m["type"] == "claim.status" and "slot" in (m.get("detail") or ""):
                    rows.setdefault(m["claim_id"], {})["queued"] = m["detail"]
                elif m["type"] == "claim.verdict":
                    rows.setdefault(m["claim_id"], {}).update(s=m["sticker"], took=m["took_ms"]/1000)
                elif m["type"] == "claim.error":
                    rows.setdefault(m["claim_id"], {}).update(s=f"ERROR {m['stage']}: {m['message'][:40]}", took=0)
        t = asyncio.create_task(r())
        await asyncio.sleep(0.4)
        for line, gap in SCRIPT:
            await ws.send(json.dumps({"type":"inject_text","text":line}))
            await asyncio.sleep(gap)
        await asyncio.sleep(25)
        t.cancel()

    print(f"\n{'='*86}")
    worst = 0
    for cid, r_ in rows.items():
        took = r_.get("took", 0); worst = max(worst, took)
        flag = "\033[31m" if took > 10 or "ERROR" in str(r_.get("s","")) else "\033[32m"
        q = f"  \033[33m[{r_['queued']}]\033[0m" if r_.get("queued") else ""
        print(f"  {flag}{r_.get('s','*** no verdict ***'):<24}\033[0m {took:5.1f}s  {r_.get('c','?')[:50]}{q}")
    print(f"\nclaims: {len(rows)}   slowest: {worst:.1f}s")
asyncio.run(main())
