# I'd cap that

Listens to a live conversation, pulls out the factual claims, checks them
against pages it fetches from the live web, and marks the exact words in the
scrolling transcript: **NO CAP**, **ABSOLUTE CAP**, **SOME CAP**,
**COULD BE CAP**, **SOURCES ARE FIGHTING**, or **WORD SALAD** for things no
evidence could ever settle.

Runs as an installed PWA on a phone, or in a browser on a laptop. Same app,
whole pipeline either way.

## The shape:

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
-  **The browser and the server exchange small JSON messages, and everything is named
   by an id.** A phrase is `s7`, a window is `w3`, a claim
   is `c2`, a passage is `E1`. `server/messages.py` defines every message.

## Latency

Target: **under 5 seconds** from the end of a sentence to a verdict on screen.

| Stage | Budget |
|---|---|
| Deepgram final text | 0.3s |
| Window closes | 0.7s |
| Claim extraction, overlapped with a speculative search | 1.3s |
| Judge, on search snippets | 1.2s |
| **Verdict on screen** | **~3.5s** |

If the snippets are too thin, the claim escalates on its own: fetch the pages,
rank the passages, judge again. That path lands around 8s.

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
```/ShowerHacks`. Its guard rails were ported here deliberately;
its UI was not.
