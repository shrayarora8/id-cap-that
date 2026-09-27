# STATUS — the shared blackboard

Two Claude sessions work on this repo at once. This file is how they stay in
sync without talking to each other constantly. **Every session updates this
file in the same commit as the work it describes.** If it is not here, the
other session does not know about it.

Last updated: stage 6 done. Real verdicts against the live web.

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

### Stage by path. Never stage everything.

**We share one working directory, not one checkout each.** `git add -A` and
`git add .` sweep up whatever the other session has open, and a commit landed
44 lines of unfinished frontend work under a backend commit message. Nothing
was lost that time. The next time is a half-written file committed mid-edit,
under someone else's message, and the person who wrote it never sees it happen.

| Session | Stages |
|---|---|
| **backend** | `git add server tests scripts` (+ `STATUS.md`, `README.md`) |
| **frontend** | `git add web docs/DESIGN-SYSTEM.md` (+ `STATUS.md`, `README.md`) |

No `git add -A`. No `git add .`. No `git commit -a`. **A modified file outside
your list is the other session typing, and it is not yours to commit.**

If `git pull --rebase` refuses because the tree is dirty, that is the signal:
look at what is modified before doing anything else.

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
| 1 | Page shell, design system applied, PWA | frontend | **built — lyric transcript live against replay** |
| 2 | WebSocket, session, JS modules, typed-claim box, replay recorder | backend | **done** |
| 3 | AudioWorklet PCM to Deepgram, HTTPS tunnel | backend | **server + browser written, needs a phone test** |
| 4 | Chunker, pre-filter, spans (pure logic, tested) | backend | **done, 87 tests** |
| 5 | LLM cache, sorter, claims underline live | backend | **done** |
| 6 | Snippet-first retrieval, judge, guard rails | backend | **done** |
| 7 | Escalation ladder, Moss deep path, budget pools | backend | not started |
| 8 | Design polish, BS index, demo mode, pre-warm | frontend | not started |

---

## Done, and how to verify it

### Stage 6 — real verdicts

```bash
.venv/bin/python scripts/watch_messages.py "Notion charges five hundred dollars per user per month."
```

Verified live: that one returns **ABSOLUTE CAP** with a quote from notion.com.
"Usain Bolt ran the 100 metres in 9.58 seconds" returns **NO CAP**.

**Measured latency, end of sentence to verdict: 7.6s.** Not the 4s target, and
the breakdown says why:

| Leg | Time |
|---|---|
| transcript final | 0.4s |
| window closes (1.0s silence rule) | 1.1s |
| sorter | 1.7s |
| search | 1.3s |
| judge | 3.2s |

Two sequential Claude calls are 5s of it. The judge is the biggest single leg
and the most variable — measured between 2.7s and 6.5s for the same size of
output. Cutting `max_tokens` from 1200 to 700 roughly halved it.

**Firecrawl spend: 1–3 credits per claim**, against 5–9 in the previous build,
because snippets settle most claims and pages are fetched only when the judge
says its evidence was too thin.

### Known behaviour the frontend should design for

A window is a *group of phrases*, not a sentence and not a paragraph. Rendering
one window as one `<p>` makes ordinary speech look like broken free verse,
which is what it looked like in the first real voice test. Windows are a
backend concept for deciding when to spend money — they are not a layout unit
and should not be drawn as one.

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

- ~~**[frontend → user]** The design system is an unagreed strawman.~~
  **Resolved.** The user is going through it round by round. Decision 1 is
  taken; see `docs/DESIGN-SYSTEM.md`. The strawman below that file's
  "Superseded strawman" line is dead, and so is `web/css/tokens.css` as it
  stands. **Neither session builds from either.**

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
- `frontend` design review started with the user; boards instead of a 1,724-line
  read. **Decision 1 (surface) taken: a flat colour field, Spotify-style
  line states, and the whole field takes the verdict's colour on ABSOLUTE CAP
  and NO CAP.** Recorded in `docs/DESIGN-SYSTEM.md`. Aesthetic is Stripe/Apple
  minimal; the strawman's tilted rubber-stamp sticker is cut.
- `frontend` taking over `web/`. Keeping `state.js`, `ws.js`, `audio.js`,
  `pcm-worklet.js`, `app.js`; rewriting `render.js` (it calls `replaceChildren`
  on the whole transcript, which a lyric view cannot survive) and all CSS.
- `backend` answered all five contract questions in `b7ce18e` by pinning them in
  `server/messages.py` rather than in prose. Evidence items, citation joins,
  tiers, confidence and the closed vocabularies are all now in the contract.
- `frontend` stage 1 built. `web/` is the new design: flat colour field, lyric
  transcript, the field takes the verdict's colour. Verified end to end against
  `scripts/replay.py tests/fixtures/synthetic_session.jsonl` — claims underline
  live, ABSOLUTE CAP lands red and struck, WORD SALAD resolves quietly, the
  skip chip and the tally both work. Type is still a placeholder (round 2).

### Stage 1 — the page

```bash
.venv/bin/python scripts/replay.py tests/fixtures/synthetic_session.jsonl
# then open the URL it prints
```

The layout model, which is what keeps frontend and backend decoupled:

- **Segments are addressable.** Every rendered run of text carries its
  `segment_id` and its character offset, so a claim span always finds its
  exact characters however the transcript has scrolled or regrouped.
- **Sentences are the layout unit,** found from the punctuation `smart_format`
  already provides. A segment straddling a sentence end becomes two chunks.
- **Windows are neither.** `window_id` is an addressing key for
  `window.skipped` and nothing else. Retune the chunker freely; the layout
  cannot move.

A line stays lit while it still has an unresolved claim in it, and lights back
up when a late verdict lands on it, because verdicts arrive out of order.
- `frontend` the work ladder now lives on the words, not in the footer:
  `searching · 3.2s` in the slot the verdict lands in, counting up, implying
  no rate. That is the design answer to backend's measured 7.6s with 3-7s
  variance. Recorded as decision 2 in `docs/DESIGN-SYSTEM.md`.
- `frontend` evidence card verified against real shapes: tier badges,
  the `evidence_id` join from citation to source, correction, confidence.
  Correction promoted above the summary.
- `frontend` three bugs found and fixed by running it rather than reading it:
  `claim.error` was treated as work-in-progress and ticked forever; a selector
  matched tags as if they were marks and deleted them; the card rebuilt on
  every message and flickered.
- `frontend` four issues from the first long live session, all fixed:
  the scroll trap (three causes, see decision 5), the dim state being too dim
  to read, `E1`/`E2` on screen, and `world_fact · count` in the card footer.
  Decisions 5-7 in `docs/DESIGN-SYSTEM.md`.
- `frontend` internal fields never reach the UI now. Backend keeps
  `evidence_id`, `kind` and `shape` on the wire -- the join and the judge need
  them -- the page just doesn't draw them.
- `frontend` tier badges now render only for tiers 1, 2 and 4. Tier 3 is a
  default, not a finding, so an ordinary source is drawn as just its domain.
- `frontend` a claim that never resolves now gives up on screen after 45s
  rather than counting upward forever. Backend's silent-drop change made this
  reachable; the floor is applied from the ticker too, since on a quiet screen
  no message arrives to trigger a redraw.
- `frontend` tier badges removed entirely, on Shray's call. The card shows the
  top three sources as plain clickable domains. `tier` still arrives and still
  drives confidence; it is not drawn. Fourth application of "only say
  something when there is something to say".

