# I'd cap that

Listens to a live conversation, pulls out the factual claims, checks them
against pages it fetches from the live web, and marks the exact words in the
scrolling transcript: **NO CAP**, **ABSOLUTE CAP**, **SOME CAP**,
**COULD BE CAP**, **SOURCES ARE FIGHTING**, or **WORD SALAD** for things no
evidence could ever settle.

Runs as an installed PWA on a phone, or in a browser on a laptop. Same app,
whole pipeline either way.

## The shape of it

```
mic -> AudioWorklet (raw PCM) -> WebSocket -> Deepgram
    -> chunker      wait for a finished thought
    -> pre-filter   drop small talk in free Python
    -> Claude       what was actually claimed?        \ these two run
    -> Firecrawl    speculative search on the window  / at the same time
    -> Claude       verdict + a verbatim quote
    -> guard rails IN CODE   quote must really exist, numbers compared
    -> highlighted words in the live transcript
```

Two ideas hold it up:

1. **The browser and the server exchange nothing but small JSON messages, and
   everything is named by an id.** A phrase is `s7`, a window is `w3`, a claim
   is `c2`, a passage is `E1`. `server/messages.py` defines every message.
   Because ids are stable, a verdict that lands eight seconds late still finds
   the exact characters it belongs to in a transcript that has scrolled on.
2. **The guard rails are code, not prompts.** A model told to quote verbatim
   mostly obeys. Mostly is not a product. We verify the quote is really on the
   page, we compare numbers with arithmetic, and we downgrade when they fail.

## Latency is the feature

Target: **under 5 seconds** from the end of a sentence to a verdict on screen.

| Stage | Budget |
|---|---|
| Deepgram final text | 0.3s |
| Window closes | 0.7s |
| Claim extraction, overlapped with a speculative search | 1.3s |
| Judge, on search snippets | 1.2s |
| **Verdict on screen** | **~3.5s** |

If the snippets are too thin, the claim escalates on its own: fetch the pages,
rank the passages, judge again. That path lands around 8s and the sticker
firms up in place.

## Running it

```bash
python3 -m venv .venv && .venv/bin/pip install -r requirements.txt
cp .env.example .env          # then fill in the five keys
.venv/bin/python scripts/check_keys.py
.venv/bin/uvicorn server.main:app --reload --port 8000
```

Open http://localhost:8000. There is a text box as well as a microphone, so
the whole pipeline can be tested without talking.

## Testing without spending anything

```bash
.venv/bin/python -m pytest -q                      # pure logic, instant, free
.venv/bin/python -m pytest -q -m "not llm and not net"
```

## Costs and limits

| Service | Job here | Limit |
|---|---|---|
| Anthropic (Haiku) | finds claims, weighs evidence | ~$0.002 per claim with prompt caching |
| Deepgram | live speech to text | large free credit |
| Firecrawl | web search, page fetch | **10 req/min**; snippet-first keeps most claims at 1 credit |
| Moss | ranks passages, in-process | free tier |

`scripts/budget.py` prints what is left.

## Documents

- `docs/DESIGN.md` — decisions and why, the timing budget, what is deliberately not built
- `docs/DESIGN-SYSTEM.md` — the UI spec, followed literally
- `docs/CONTRACT.md` — every message, generated from `server/messages.py`

The previous build of this product, with a full write-up of its ten failure
modes, is at `../../ShowerHacks`. Its guard rails were ported here deliberately;
its UI was not.
