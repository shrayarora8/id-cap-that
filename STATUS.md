# STATUS — the shared blackboard

Two Claude sessions work on this repo at once. This file is how they stay in
sync without talking to each other constantly. **Every session updates this
file in the same commit as the work it describes.** If it is not here, the
other session does not know about it.

Last updated: stage 5 done. Claims are found and fluff is stamped live.

---

## Who owns what

Ownership is by directory, so two sessions never edit the same file.

| Session | Owns | Must not touch |
|---|---|---|
| **backend** | `server/`, `tests/`, `scripts/` | `web/`, `docs/DESIGN-SYSTEM.md` |
| **frontend** | `web/`, `docs/DESIGN-SYSTEM.md` | `server/`, `tests/`, `scripts/` |

`server/messages.py` is the **frozen contract** and is owned by backend.
Frontend reads it and builds against it. If frontend needs a field that does
not exist, it asks backend rather than adding it — a contract edited from two
sides is not a contract.

`STATUS.md` and `README.md` are shared. Append, do not rewrite.

## Working agreement

- Small commits, often. Push every one.
- Pull before you start. `git pull --rebase` if you have been away.
- Never commit `.env`. It is gitignored; keep it that way.
- Anything that spends an API credit gets a cache and a budget check first.

---

## Stage board

| Stage | What | Owner | State |
|---|---|---|---|
| 0 | Repo, keys, **frozen contract** | backend | **done** |
| 1 | Page shell, design system applied, PWA | frontend | not started |
| 2 | WebSocket, session, JS modules, typed-claim box, replay recorder | backend | **done** |
| 3 | AudioWorklet PCM to Deepgram, HTTPS tunnel | backend | **server + browser written, needs a phone test** |
| 4 | Chunker, pre-filter, spans (pure logic, tested) | backend | **done, 87 tests** |
| 5 | LLM cache, sorter, claims underline live | backend | **done** |
| 6 | Snippet-first retrieval, judge, guard rails | backend | not started |
| 7 | Escalation ladder, Moss deep path, budget pools | backend | not started |
| 8 | Design polish, BS index, demo mode, pre-warm | frontend | not started |

---

## Done, and how to verify it

### Stage 5 — claims

```bash
.venv/bin/python scripts/watch_messages.py "Messi scored 45 goals last season." "This will revolutionize the market through synergy." "How's it going?"
```

Claims are found and underlined; fluff gets WORD SALAD in about 1.4s without
touching the internet; small talk is skipped for nothing. Checkable claims sit
at `queued` until stage 6 exists.

Sorter: ~1.5s, ~$0.002 a call, one call per window.

**Prompt caching does not work here and has been removed.** Haiku 4.5 needs a
4096-token prefix before Anthropic will cache it — the highest minimum of any
current model, and not monotonic across generations. Our system prompts are
roughly 640 and 1100 tokens, so a `cache_control` block was accepted, did
nothing, and reported zero cached tokens on every call, with no error. The
per-model table and the reasoning are in `server/llm.py`. A test fails if the
sorter prompt ever grows past the minimum, at which point it becomes worth
revisiting with measurement.

### Stage 4 — the chunker

```bash
.venv/bin/python -m pytest tests/test_chunker.py -q     # 18 passed, instant
```

Phrases group into windows. A window closes on: utterance end, 3 phrases, 1.0s
pause, or 12s. The pause and utterance-end rules are **gated on the thought
sounding finished** — terminal punctuation plus 4+ words — because the signal
that a sound stopped is not the signal that a thought finished.

Honest note found while testing: at the shipped config the 12s `max_duration`
rule is **unreachable**, because reaching it needs phrases still arriving (or
hard silence fires at 2.5s) but fewer than 3 of them (or max_sentences fires).
It is kept as insurance for anyone raising the sentence cap. Both facts are
pinned by tests.

### Stage 2 — the wire

```bash
.venv/bin/uvicorn server.main:app --reload --port 8000   # then open localhost:8000
.venv/bin/python scripts/watch_messages.py "Messi scored 45 goals last season."
.venv/bin/python scripts/replay.py --list
```

Typing a claim into the box puts it in the transcript. `watch_messages.py`
shows the same thing as a stream of text with no browser open.

Every session records itself to `recordings/*.jsonl` with relative timings.
`scripts/replay.py` plays one back into the real UI at its original speed over
a normal WebSocket, so the page cannot tell the difference. That is how the UI
gets built without talking, how a bug nine seconds into a conversation gets
reproduced exactly, and what still demos when the venue wifi dies.

### Stage 0 — repo, keys, contract

```bash
.venv/bin/python scripts/check_keys.py    # 4 green [ ok ] lines
.venv/bin/python -m pytest -q             # 21 passed, instant, free
```

- `server/messages.py` — the contract. Every message, both directions.
- `scripts/check_keys.py` — real auth checks against all four services. Free.
- Firecrawl balance as of stage 0: **904 credits**, 10 requests/minute.

**Decisions locked in stage 0:**

- Audio on the wire is **raw 16 kHz mono linear16 PCM**, not WebM/Opus.
  iOS Safari will not produce Opus, and the phone is a first-class target.
- `claim.status` carries a machine-readable `stage` as well as a human line,
  so the UI draws a progress ladder rather than a line of text that sits still.
- `claim.verdict` is `provisional` or `confirmed` and declares its evidence
  `depth` (`snippets` or `pages`). A fast read is labelled as one.
- Verdicts carry a per-stage `timings` breakdown. Latency is the feature, so
  it is measured, not estimated.
- Budget: three pools. `reserved` (the demo device), `public` (visitors,
  capped per session with a visible counter), `byok` (their own keys,
  uncapped, never written to disk). Never spend past the free tier.

---

## Open questions

Anything blocking the other session goes here, with who is blocked.

- **[frontend → user]** The design system in `docs/DESIGN-SYSTEM.md` is a
  machine-written strawman. It has not been agreed. Nothing may be built from
  it until the user has gone through it.

---

## Message log

Newest last. One line per handoff between sessions.

- `backend` stage 0 complete, contract frozen, pushed. Frontend is unblocked
  for stage 1 as soon as the design is agreed with the user.
- `backend` stage 2 done. The wire is live: `/ws` accepts a connection, emits
  `session.ready` then `server.note`, and turns `inject_text` into
  `transcript.final`. `web/js/` has the module split frontend will build on:
  `ws.js` (reconnecting socket), `state.js` (apply a message, return whether a
  redraw is needed), `render.js` (throwaway), `audio.js` + `pcm-worklet.js`
  (raw PCM capture), `app.js` (wiring only).
  **`web/css/scaffold.css` and `web/js/render.js` are throwaway. Delete them.**
  Everything else in `web/js/` is real and should be kept.
