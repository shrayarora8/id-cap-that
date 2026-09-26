// Draws the transcript from state. Deliberately plain: the design system has
// not been agreed yet, so this is scaffolding the frontend session replaces.
//
// The one thing here that is NOT throwaway is how a claim is painted. A claim
// carries spans of (segment_id, start, end), and a claim can straddle two
// phrases, so it contributes a span to each phrase it touches. Only the last
// span of a claim carries the sticker, or the sticker appears twice.

import { state } from "./state.js";

const el = (id) => document.getElementById(id);

function spansFor(segmentId) {
  const found = [];
  for (const claim of state.claims.values()) {
    claim.spans.forEach((span, i) => {
      if (span.segment_id === segmentId) {
        found.push({ claim, span, isLast: i === claim.spans.length - 1 });
      }
    });
  }
  return found.sort((a, b) => a.span.start - b.span.start);
}

function claimClass(claim) {
  if (claim.stage !== "done") return "claim checking";
  switch (claim.verdict) {
    case "SUPPORTED": return "claim nocap";
    case "CONTRADICTED": return "claim cap";
    case "PARTIALLY_SUPPORTED": return "claim partial";
    case "DISPUTED": return "claim disputed";
    case "NOT_FACT_CHECKABLE": return "claim salad";
    default: return "claim unknown";
  }
}

function segmentSpan(seg) {
  const wrap = document.createElement("span");
  const marks = spansFor(seg.id);

  if (!marks.length) {
    wrap.textContent = seg.text + " ";
    return wrap;
  }

  let cursor = 0;
  for (const { claim, span, isLast } of marks) {
    if (span.start > cursor) wrap.append(seg.text.slice(cursor, span.start));

    const mark = document.createElement("mark");
    mark.className = claimClass(claim);
    mark.dataset.claimId = claim.id;
    mark.textContent = seg.text.slice(span.start, span.end);

    if (claim.sticker && isLast) {
      const sticker = document.createElement("span");
      sticker.className = "sticker";
      sticker.textContent = claim.sticker;
      if (claim.verdictStage === "provisional") sticker.classList.add("provisional");
      mark.append(sticker);
    }
    wrap.append(mark);
    cursor = Math.max(cursor, span.end);
  }
  wrap.append(seg.text.slice(cursor) + " ");
  return wrap;
}

function windowBlock(win, isPending) {
  const block = document.createElement("p");
  block.className = isPending ? "window pending" : "window";
  block.append(...win.segments.map(segmentSpan));

  if (win.skipped) {
    const tag = document.createElement("span");
    tag.className = "why";
    tag.textContent = `skipped: ${win.skipped}`;
    block.append(tag);
  }
  return block;
}

export function render() {
  el("status").textContent = state.status;

  const b = state.budget;
  el("budget").textContent =
    b.pool === "byok" ? "your keys" : `${b.claimsLeft} claims left`;

  const blocks = state.windows.map((w) => windowBlock(w, false));
  if (state.pending.length) {
    blocks.push(windowBlock({ segments: state.pending }, true));
  }
  el("transcript").replaceChildren(...blocks);

  el("interim").textContent = state.interim;

  // The detail list, so evidence is visible before the design pass exists.
  const recent = [...state.claims.values()].slice(-8).reverse();
  el("detail").replaceChildren(
    ...recent.map((c) => {
      const box = document.createElement("div");
      box.className = "claim-detail";

      const head = document.createElement("div");
      head.className = `claim-head ${claimClass(c).replace("claim ", "")}`;
      head.textContent = c.sticker || c.detail || c.stage;
      box.append(head);

      const body = document.createElement("div");
      body.textContent = c.normalized || c.quote;
      box.append(body);

      if (c.correction) {
        const fix = document.createElement("div");
        fix.className = "correction";
        fix.textContent = `actually: ${c.correction}`;
        box.append(fix);
      }
      for (const cite of c.citations || []) {
        const q = document.createElement("div");
        q.className = "quote";
        q.textContent = `"${cite.quote}"`;
        box.append(q);
      }
      if (c.tookMs) {
        const meta = document.createElement("div");
        meta.className = "meta";
        meta.textContent = `${(c.tookMs / 1000).toFixed(1)}s · ${c.depth || ""} · ${c.confidence || ""}`;
        box.append(meta);
      }
      return box;
    })
  );
}
