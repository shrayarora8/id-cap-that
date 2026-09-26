# STATUS — the shared blackboard

Two Claude sessions work on this repo at once. This file is how they stay in
sync without talking to each other constantly. **Every session updates this
file in the same commit as the work it describes.** If it is not here, the
other session does not know about it.

Last updated: stage 0 complete.

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
| 2 | WebSocket, session, JS modules, typed-claim box, replay recorder | both | not started |
| 3 | AudioWorklet PCM to Deepgram, HTTPS tunnel | backend | not started |
| 4 | Chunker, pre-filter, spans (pure logic, tested) | backend | not started |
| 5 | LLM cache, sorter, claims underline live | backend | not started |
| 6 | Snippet-first retrieval, judge, guard rails | backend | not started |
| 7 | Escalation ladder, Moss deep path, budget pools | backend | not started |
| 8 | Design polish, BS index, demo mode, pre-warm | frontend | not started |

---

## Done, and how to verify it

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
