// Everything the page knows. The page computes nothing: it applies a message
// to this object and redraws. That is what makes the whole system watchable as
// a stream of text with no browser open.

// A reconnect gives us a fresh server session, and that session numbers its
// phrases from s1 again. Keyed by id alone, the new s1 silently replaces the
// old one and a whole conversation disappears. Every phrase therefore carries
// the connection it arrived on and the order it arrived in; the id stays
// exactly as the contract defines it, for spans.
let epoch = 0;
let arrival = 0;

// A typed claim is a whole thought by construction, so it always gets its own
// line. Speech is not: Deepgram splits one sentence across several phrases,
// and those have to join up.
//
// Capitalisation looked like the signal and is not one -- someone typing in
// lowercase produced three claims run together on one line. This is exact
// rather than a guess: a phrase is typed if we just submitted one, or if
// nothing is being recorded, because speech cannot arrive when the microphone
// is off.
let typedPending = 0;

export function noteTyped() {
  typedPending += 1;
}

export const state = {
  sessionId: null,
  windows: [], // closed groups: { id, segments, reason, skipped }
  pending: [], // final phrases not yet grouped into a window
  claims: new Map(),
  interim: "",
  listening: false,
  status: "not connected",
  error: null,
  budget: { claimsLeft: 0, claimsCap: 0, pool: "public" },
};

/** The user corrected a claim the transcription garbled.
 *
 *  Applied locally so the page reacts on the keystroke rather than on the
 *  round trip, and so the corrected words are on screen while the re-check
 *  runs. The server re-emits claim.detected for the same id, which lands on
 *  top of this and makes the two agree.
 *
 *  `heard` keeps what was actually said. A fact-checking product does not get
 *  to quietly rewrite the record of someone's words, even when the words were
 *  our own mistake.
 */
export function editClaim(claimId, text) {
  const c = state.claims.get(claimId);
  if (!c) return false;
  if (c.heard === undefined) c.heard = c.quote || c.normalized || "";
  Object.assign(c, {
    normalized: text,
    corrected: text,
    stage: "queued",
    detail: "re-checking",
    verdict: null,
    sticker: null,
    summary: "",
    correction: "",
    citations: [],
    evidence: [],
    confidence: "none",
    tookMs: null,
    verdictStage: undefined,
  });
  return true;
}

// Returns true when the transcript needs redrawing.
export function apply(msg) {
  switch (msg.type) {
    case "session.ready":
      if (state.sessionId && state.sessionId !== msg.session_id) epoch += 1;
      state.sessionId = msg.session_id;
      state.budget = {
        claimsLeft: msg.budget.claims_left,
        claimsCap: msg.budget.claims_cap,
        pool: msg.budget.pool,
      };
      return true;

    case "budget.update":
      state.budget = {
        claimsLeft: msg.claims_left,
        claimsCap: msg.claims_cap,
        pool: msg.pool,
      };
      return true;

    case "server.note":
      state.status = msg.message;
      // An error must not scroll past as grey status text. The microphone
      // failing silently is the single worst failure this app has, because
      // the screen looks exactly like "nobody is talking".
      state.error = msg.level === "error" ? msg.message : null;
      return true;

    case "transcript.interim":
      state.interim = msg.text;
      return true;

    case "transcript.final": {
      const typed = typedPending > 0 || !state.listening;
      if (typedPending > 0) typedPending -= 1;
      state.interim = "";
      state.pending.push({
        id: msg.segment_id,
        text: msg.text,
        key: `${epoch}:${msg.segment_id}`,
        epoch,
        typed,
        seq: (arrival += 1),
      });
      return true;
    }

    case "window.ready": {
      // Move exactly the phrases this window claimed out of pending.
      const ids = new Set(msg.segment_ids);
      const taken = state.pending.filter((s) => ids.has(s.id));
      state.pending = state.pending.filter((s) => !ids.has(s.id));
      state.windows.push({ id: msg.window_id, segments: taken, reason: msg.reason });
      return true;
    }

    case "window.skipped": {
      const win = state.windows.find((w) => w.id === msg.window_id);
      if (win) win.skipped = msg.reason;
      return true;
    }

    case "claim.detected": {
      // A correction comes back under the same id, carrying what was actually
      // heard. Server-backed, so the page is not relying on its own optimistic
      // copy of the words.
      const prev = state.claims.get(msg.claim_id);
      state.claims.set(msg.claim_id, {
        id: msg.claim_id,
        epoch: prev ? prev.epoch : epoch,
        edited: Boolean(msg.edited),
        heard: msg.heard || (prev && prev.heard) || "",
        corrected: msg.edited ? msg.normalized : (prev && prev.corrected) || undefined,
        spans: msg.spans,
        quote: msg.quote,
        normalized: msg.normalized,
        kind: msg.kind,
        shape: msg.shape,
        checkable: msg.checkable,
        note: msg.note,
        stage: "queued",
        verdict: null,
        sticker: null,
      });
      return true;
    }

    case "claim.status": {
      const c = state.claims.get(msg.claim_id);
      if (c) {
        c.stage = msg.stage;
        c.detail = msg.detail;
      }
      return true;
    }

    case "claim.evidence": {
      const c = state.claims.get(msg.claim_id);
      if (c) {
        c.evidence = msg.items;
        c.depth = msg.depth;
      }
      return true;
    }

    case "claim.verdict": {
      const c = state.claims.get(msg.claim_id);
      if (!c) return false;
      Object.assign(c, {
        stage: "done",
        verdict: msg.verdict,
        sticker: msg.sticker,
        summary: msg.summary,
        verdictStage: msg.stage, // provisional or confirmed
        depth: msg.depth,
        citations: msg.citations,
        correction: msg.correction,
        confidence: msg.confidence,
        tookMs: msg.took_ms,
        timings: msg.timings,
      });
      return true;
    }

    case "claim.error": {
      const c = state.claims.get(msg.claim_id);
      if (!c) return false;
      c.stage = "done";
      c.sticker = "COULDN'T CHECK";
      c.summary = msg.message;
      return true;
    }

    default:
      return false;
  }
}
