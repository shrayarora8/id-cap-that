// The lyric transcript.
//
// Three ideas hold this file up:
//
//   1. SEGMENTS ARE THE ADDRESSABLE UNIT. Claim spans are (segment_id, start,
//      end) character offsets into one `transcript.final`, so every piece of
//      rendered text remembers which segment it came from and at what offset.
//   2. SENTENCES ARE THE LAYOUT UNIT. A line on screen is a sentence, found
//      from the punctuation Deepgram's smart_format already gives us.
//   3. WINDOWS ARE NEITHER. A window is a backend grouping that decides when
//      we spend money. It can be half a sentence or three. Drawing one window
//      as one paragraph is what made the first voice test look like broken
//      free verse. window_id is used here only as an addressing key.
//
// Because of 1 and 2, the chunker can be retuned freely and the layout never
// moves. Because of 3, a claim that straddles a segment or a line break still
// finds its exact characters.
//
// Nothing is rebuilt that has not changed: a line is re-created only when its
// text or its claim spans change, and a verdict landing mutates attributes in
// place so the animation is never restarted.

import { state } from "./state.js";
import * as sound from "./sound.js";

const el = (id) => document.getElementById(id);
const lyr = () => el("lyr");

const SEG_N = (id) => Number(String(id).replace(/^\D+/, "")) || 0;

// Sentence end: terminal punctuation, any closing quote or bracket, then
// whitespace or the end of the phrase.
const SENTENCE_END = /[.!?…]+["'”’)\]]*(?:\s+|$)/g;

// A line with no punctuation in it at all must still break eventually, or a
// rambling speaker produces one line the height of the screen.
const SOFT_MAX = 150;

const SLUG = (v) => String(v || "").toLowerCase();

// A check can now be dropped without a terminal message: the sorter stopped
// emitting claims it cannot resolve, and a claim already on screen has no
// guarantee of ever being answered. Without a floor, its counter ticks up
// forever -- the same failure the claim.error bug had, which is the worst
// thing this UI can do given the counter is the honesty pitch. Generous,
// because a cold check measures ~9s and the judge alone has taken 6.5s.
const GIVE_UP_MS = 45000;

// ---------------------------------------------------------------------------
// state kept by the renderer itself (never by the server)

let lineSigs = [];          // per-line signature, for reconciliation
let flashed = new Set();    // claims whose field flash has already fired
let relitTimers = new Map();
let openCard = null;        // claim_id whose card is showing
let startedAt = new Map();  // claim_id -> when we first saw it unresolved
let cardSig = "";           // what the open card was last built from
let ticker = null;
let pinned = true;
let unread = 0;
let newCap = false;
const PIN_SLOP = 48;

/** When the reader has scrolled away, say what they are missing and give them
 *  one tap back. Without this, scrolling up silently stops the feed. */
function paintJump() {
  const box = lyr();
  let pill = document.querySelector(".jump");
  if (pinned || !unread) {
    if (pill) pill.remove();
    return;
  }
  if (!pill) {
    pill = document.createElement("button");
    pill.type = "button";
    pill.className = "jump";
    pill.onclick = () => {
      pinned = true;
      unread = 0;
      newCap = false;
      pill.remove();
      box.scrollTo({ top: box.scrollHeight, behavior: "smooth" });
    };
    document.body.appendChild(pill);
  }
  pill.dataset.new = newCap ? "cap" : "";
  pill.textContent = newCap ? `↓ ${unread} new · 1 cap` : `↓ ${unread} new`;
}

// ---------------------------------------------------------------------------
// text -> lines

/** Every segment the page knows about, in stable order, however it is grouped. */
function orderedSegments() {
  const seen = new Map();
  for (const w of state.windows) {
    for (const s of w.segments) seen.set(s.id, { id: s.id, text: s.text, win: w });
  }
  for (const s of state.pending) {
    if (!seen.has(s.id)) seen.set(s.id, { id: s.id, text: s.text, win: null });
  }
  return [...seen.values()].sort((a, b) => SEG_N(a.id) - SEG_N(b.id));
}

/** Split one segment's text at sentence ends, keeping each piece's offset. */
function piecesOf(text) {
  const out = [];
  let last = 0;
  SENTENCE_END.lastIndex = 0;
  let m;
  while ((m = SENTENCE_END.exec(text)) !== null) {
    const end = m.index + m[0].length;
    out.push({ base: last, text: text.slice(last, end), closes: true });
    last = end;
    if (SENTENCE_END.lastIndex <= m.index) SENTENCE_END.lastIndex = m.index + 1;
  }
  if (last < text.length) out.push({ base: last, text: text.slice(last), closes: false });
  return out;
}

/** The whole transcript as lines of chunks. A chunk knows its segment and offset. */
function buildLines() {
  const lines = [];
  let cur = [];
  let len = 0;
  let closed = true;

  const flush = (didClose) => {
    if (!cur.length) return;
    lines.push({ chunks: cur, closed: didClose, wins: new Set(cur.map((c) => c.win).filter(Boolean)) });
    cur = [];
    len = 0;
  };

  for (const seg of orderedSegments()) {
    for (const p of piecesOf(seg.text)) {
      if (!p.text) continue;
      cur.push({ segId: seg.id, base: p.base, text: p.text, win: seg.win });
      len += p.text.length;
      if (p.closes) { flush(true); closed = true; }
      else if (len >= SOFT_MAX) { flush(false); closed = false; }
      else closed = false;
    }
  }
  flush(false);
  return { lines, closed: lines.length ? lines[lines.length - 1].closed : true };
}

// ---------------------------------------------------------------------------
// claims

/** Claim fragments that fall inside one chunk, in chunk-local coordinates. */
function hitsIn(chunk) {
  const hits = [];
  for (const c of state.claims.values()) {
    for (const sp of c.spans || []) {
      if (sp.segment_id !== chunk.segId) continue;
      const s = Math.max(sp.start, chunk.base);
      const e = Math.min(sp.end, chunk.base + chunk.text.length);
      if (e > s) hits.push({ id: c.id, s: s - chunk.base, e: e - chunk.base });
    }
  }
  return hits.sort((a, b) => a.s - b.s);
}

function lineSignature(line) {
  const text = line.chunks.map((c) => `${c.segId}:${c.base}:${c.text.length}`).join("|");
  const marks = line.chunks
    .flatMap((c) => hitsIn(c).map((h) => `${h.id}@${h.s}-${h.e}`))
    .join(",");
  const skip = [...line.wins].map((w) => w.skipped || "").join(",");
  return `${text}#${marks}#${skip}`;
}

// ---------------------------------------------------------------------------
// DOM

function buildLine(line) {
  const p = document.createElement("p");
  p.className = "line";

  line.chunks.forEach((chunk, ci) => {
    const hits = hitsIn(chunk);
    let at = 0;

    const emit = (text, claimId) => {
      if (!text) return;
      if (!claimId) {
        p.appendChild(document.createTextNode(text));
        return;
      }
      const mark = document.createElement("span");
      mark.className = "mark";
      mark.dataset.claimId = claimId;
      mark.setAttribute("role", "button");
      mark.setAttribute("tabindex", "0");
      const txt = document.createElement("span");
      txt.className = "txt";
      txt.textContent = text;
      mark.appendChild(txt);
      p.appendChild(mark);
    };

    for (const h of hits) {
      if (h.s > at) emit(chunk.text.slice(at, h.s), null);
      emit(chunk.text.slice(h.s, h.e), h.id);
      at = Math.max(at, h.e);
    }
    emit(chunk.text.slice(at), null);

    const isLast = ci === line.chunks.length - 1;
    if (!isLast && !/\s$/.test(chunk.text)) p.appendChild(document.createTextNode(" "));
  });

  // A window the pre-filter dropped. Addressed by window_id, drawn on words.
  const skipped = [...line.wins].map((w) => w.skipped).filter(Boolean);
  if (skipped.length) {
    const tag = document.createElement("span");
    tag.className = "skip";
    tag.textContent = `skipped: ${skipped[0]}`;
    p.appendChild(tag);
  }

  return p;
}

/** The work ladder, and the verdict, in the same slot.
 *
 *  End of sentence to verdict measures 7.6s, and the same claim can take 3s or
 *  7s. That is too long to carry with a loop and a footer, and the variance
 *  rules out anything that implies a rate: a progress bar that fills in four
 *  seconds and then waits three reads as broken.
 *
 *  So the ladder is put where the eye already is — in the slot the verdict
 *  will occupy, right beside the words — and it names the work and counts up.
 *  Nothing predicts an end. The count is honest about how long this took,
 *  which is the pitch.
 */
const STAGE_WORDS = {
  queued: "checking",
  extracting: "reading the claim",
  searching: "searching",
  reading: "reading sources",
  sifting: "weighing evidence",
  judging: "deciding",
  escalating: "digging deeper",
};

function workLabel(c) {
  const stage = STAGE_WORDS[c.stage] || "checking";
  const t0 = startedAt.get(c.id);
  const secs = t0 ? ((performance.now() - t0) / 1000).toFixed(1) : "0.0";
  return `${stage} · ${secs}s`;
}

function tick() {
  const nodes = [...lyr().querySelectorAll(".tag.work")];
  if (!nodes.length) {
    clearInterval(ticker);
    ticker = null;
    return;
  }
  let stalled = false;
  for (const n of nodes) {
    const c = state.claims.get(n.dataset.claimId);
    if (!c) continue;
    const t0 = startedAt.get(c.id);
    if (t0 && performance.now() - t0 > GIVE_UP_MS) stalled = true;
    else n.textContent = workLabel(c);
  }
  // Nothing may arrive to trigger a render, so the floor has to be applied
  // from here or the counter runs forever on a silent screen.
  if (stalled) paintClaims();
}

function paintClaims() {
  let working = false;

  for (const c of state.claims.values()) {
    const marks = [...lyr().querySelectorAll(`.mark[data-claim-id="${CSS.escape(c.id)}"]`)];
    if (!marks.length) continue;

    const slug = SLUG(c.verdict);
    // claim.error resolves a claim without giving it a verdict: it sets a
    // sticker and nothing else. Treating that as "still checking" leaves a
    // counter ticking forever on a claim that already gave up.
    const t0 = startedAt.get(c.id);
    const stalled = !c.verdict && !c.sticker && Boolean(t0) &&
      performance.now() - t0 > GIVE_UP_MS;
    const errored = (!c.verdict && Boolean(c.sticker)) || stalled;
    const checking = !c.verdict && !c.sticker && !stalled && c.checkable !== false;
    if (checking) {
      working = true;
      if (!startedAt.has(c.id)) startedAt.set(c.id, performance.now());
    }

    for (const m of marks) {
      m.classList.toggle("checking", checking);
      m.toggleAttribute("data-err", errored);
      if (c.verdict) {
        m.dataset.v = c.verdict;
        m.style.setProperty("--vc", `var(--v-${slug})`);
        m.style.setProperty("--vline", `var(--line-${slug})`);
      } else {
        delete m.dataset.v;
      }
      m.setAttribute("aria-expanded", String(openCard === c.id));
      m.setAttribute("aria-label", ariaFor(c));
    }

    const last = marks[marks.length - 1];
    const kind = checking ? "work" : "verdict";
    const label = checking
      ? workLabel(c)
      : (c.sticker || c.verdict || (stalled ? "NO ANSWER" : ""));

    // A claim almost never includes the sentence's full stop, so without this
    // the label lands between the words and their punctuation: "...per month
    // ABSOLUTE CAP." Pull the punctuation inside the mark instead.
    const after = last.nextSibling;
    if (after && after.nodeType === Node.TEXT_NODE && !last.querySelector(".punct")) {
      const m = /^[.,;:!?…)"'”’\]]+/.exec(after.textContent);
      if (m) {
        after.textContent = after.textContent.slice(m[0].length);
        const punct = document.createElement("span");
        punct.className = "punct";
        punct.textContent = m[0];
        last.appendChild(punct);
      }
    }

    // Reuse the existing tag when only its text changed, so the counter can
    // tick without replaying the entrance animation ten times a second.
    const host = endsLine(last) ? last : (last.closest(".line") || last);

    let tag = lyr().querySelector(`.tag[data-claim-id="${CSS.escape(c.id)}"]`);
    if (tag && (tag.dataset.kind !== kind || tag.parentElement !== host)) {
      tag.remove();
      tag = null;
    }
    if (!label) {
      if (tag) tag.remove();
      continue;
    }
    if (!tag) {
      tag = document.createElement("span");
      tag.className = kind === "work" ? "tag work" : "tag";
      tag.dataset.kind = kind;
      tag.dataset.claimId = c.id;
      tag.setAttribute("aria-hidden", "true");
      host.appendChild(tag);
    }
    tag.textContent = label;
  }

  if (working && !ticker) ticker = setInterval(tick, 100);
}

/** Does this claim finish the line it is on?
 *
 *  When it does, the label sits right after the words and reads as an
 *  annotation. When it does not, the label lands mid-sentence -- "It costs $8
 *  per seat per month, ABSOLUTE CAP which I think is reasonable" -- and the
 *  reader has to step over it. In that case the label goes to the end of the
 *  line instead. The coloured, struck words still say which claim it is.
 */
function endsLine(mark) {
  const line = mark.closest(".line");
  if (!line) return true;
  for (let i = line.childNodes.length - 1; i >= 0; i -= 1) {
    const n = line.childNodes[i];
    if (n.nodeType === Node.TEXT_NODE && !n.textContent.trim()) continue;
    if (n.nodeType === Node.ELEMENT_NODE && n.classList.contains("tag")) continue;
    return n === mark || n.contains(mark);
  }
  return true;
}

function ariaFor(c) {
  const claim = c.normalized || c.quote || "claim";
  if (!c.verdict && c.sticker) return `Claim: ${claim}. Could not be checked.`;
  if (!c.verdict) return `Claim: ${claim}. Being checked.`;
  const stage = c.verdictStage === "provisional" ? " Quick read." : "";
  return `Claim: ${claim}. Verdict: ${c.sticker || c.verdict}.${stage}`;
}

/** Which lines are lit. A line stays lit while it still has work in it. */
function paintLineStates(lines) {
  const nodes = [...lyr().querySelectorAll(".line")];
  const unresolved = new Set();
  for (const c of state.claims.values()) {
    if (!c.verdict) for (const sp of c.spans || []) unresolved.add(sp.segment_id);
  }

  nodes.forEach((node, i) => {
    const line = lines[i];
    if (!line) return;
    const segs = new Set(line.chunks.map((c) => c.segId));
    const held = [...segs].some((s) => unresolved.has(s));
    const live = i === nodes.length - 1;

    node.classList.toggle("live", live);
    node.classList.toggle("held", held && !live);
    node.classList.toggle("sunk", !live && !held && i < nodes.length - 5);
  });
}

/** Interim words land in the line being spoken, and are the only node
 *  allowed to be replaced on every frame. */
function paintInterim(closed) {
  const box = lyr();
  let node = box.querySelector(".interim");

  if (!state.interim) {
    if (node) {
      const line = node.closest(".line");
      node.remove();
      if (line && !line.textContent.trim()) line.remove();
    }
    return;
  }

  if (!node) {
    node = document.createElement("span");
    node.className = "interim";
    const last = box.querySelector(".line:last-of-type");
    if (last && !closed) {
      last.appendChild(document.createTextNode(" "));
      last.appendChild(node);
    } else {
      const p = document.createElement("p");
      p.className = "line live";
      p.appendChild(node);
      box.appendChild(p);
    }
  }
  node.textContent = state.interim;
}

// ---------------------------------------------------------------------------
// the field taking a verdict

const LOUD = new Set(["CONTRADICTED", "SUPPORTED"]);

function flashField() {
  for (const c of state.claims.values()) {
    if (!c.verdict || flashed.has(c.id + c.verdict)) continue;
    flashed.add(c.id + c.verdict);

    el("announce").textContent = `${c.sticker || c.verdict}: ${c.normalized || c.quote || ""}`;

    // A verdict can land eight seconds late, on a line that has gone dim and
    // scrolled up. Light it back up so the change is seen where it happened.
    for (const sp of c.spans || []) {
      const m = lyr().querySelector(`.mark[data-claim-id="${CSS.escape(c.id)}"]`);
      const line = m && m.closest(".line");
      if (!line || line.classList.contains("live")) break;
      line.classList.add("relit");
      clearTimeout(relitTimers.get(c.id));
      relitTimers.set(c.id, setTimeout(() => line.classList.remove("relit"),
        parseInt(getComputedStyle(document.documentElement).getPropertyValue("--hold-relit")) || 2400));
      break;
    }

    if (!LOUD.has(c.verdict)) continue;

    if (!pinned && c.verdict === "CONTRADICTED") newCap = true;
    sound.verdict(c.verdict);
    document.body.dataset.flash = c.verdict;
    clearTimeout(flashField._t);
    flashField._t = setTimeout(() => {
      delete document.body.dataset.flash;
    }, parseInt(getComputedStyle(document.documentElement).getPropertyValue("--hold-field")) || 1500);
  }
}

function paintTally() {
  let cap = 0, nocap = 0;
  for (const c of state.claims.values()) {
    if (c.verdict === "CONTRADICTED") cap += 1;
    if (c.verdict === "SUPPORTED") nocap += 1;
  }
  el("t-cap").textContent = cap;
  el("t-nocap").textContent = nocap;
  el("t-cap").parentElement.dataset.zero = cap ? "0" : "1";
  el("t-nocap").parentElement.dataset.zero = nocap ? "0" : "1";
}

// ---------------------------------------------------------------------------
// the evidence card

// No tier badges at all. PRIMARY on notion.com tells a reader something the
// domain already told them, and the classification chrome was crowding the
// evidence it was wrapped around. `tier` still arrives and still drives
// confidence -- it just isn't drawn.
//
// Three sources, not all of them: past three, the list stops being evidence
// you read and starts being a list you scroll.
const MAX_SOURCES = 3;

function closeCard() {
  const c = document.querySelector(".card");
  if (c) c.remove();
  openCard = null;
  cardSig = "";
}

/** Only the fields the card actually draws. Rebuilding it on every message
 *  replays the entrance animation several times a second while a claim is
 *  being checked, which reads as flicker. */
function cardSignature(c) {
  return [
    c.verdict, c.sticker, c.verdictStage, c.depth, c.summary, c.correction,
    c.confidence, c.tookMs, c.detail, c.stage,
    (c.citations || []).length, (c.evidence || []).length,
  ].join("|");
}

function showCard(claimId) {
  closeCard();
  const c = state.claims.get(claimId);
  if (!c) return;
  openCard = claimId;
  cardSig = cardSignature(c);

  const slug = SLUG(c.verdict);
  const card = document.createElement("div");
  card.className = "card";
  card.setAttribute("role", "dialog");
  card.setAttribute("aria-label", "Evidence");
  if (c.verdict) card.style.setProperty("--vc", `var(--v-${slug})`);

  const host = (u) => { try { return new URL(u).hostname.replace(/^www\./, ""); } catch { return u; } };

  const head = document.createElement("div");
  head.className = "card-head";
  head.innerHTML =
    `<span class="card-v"></span>` +
    `<button class="card-x" type="button" aria-label="Close">✕</button>`;
  head.querySelector(".card-v").textContent = c.sticker || (c.checkable === false ? "not checkable" : "checking…");
  head.querySelector(".card-x").onclick = () => { closeCard(); paintClaims(); };
  card.appendChild(head);

  const h3 = document.createElement("h3");
  h3.textContent = c.normalized || c.quote || "";
  card.appendChild(h3);

  if (c.verdictStage === "provisional") {
    const p = document.createElement("span");
    p.className = "prov";
    p.textContent = "quick read";
    card.appendChild(p);
  }

  // Above the summary, not below the quotes. A correction is the one thing on
  // this card a person can act on -- it turns a dunk into information.
  if (c.correction) {
    const fix = document.createElement("div");
    fix.className = "fix";
    fix.innerHTML = `<span>actually:</span> `;
    fix.appendChild(document.createTextNode(c.correction));
    card.appendChild(fix);
  }

  if (c.summary) {
    const p = document.createElement("p");
    p.textContent = c.summary;
    card.appendChild(p);
  }

  if (!c.verdict && !c.sticker && c.checkable !== false) {
    const p = document.createElement("p");
    p.textContent = c.detail || "checking…";
    card.appendChild(p);
  }

  // The raw excerpt is not shown. Passages are scraped from live pages, so a
  // mid-table fragment or half a line of marketing copy reads badly often
  // enough that it damages the card it is meant to support.
  //
  // Nothing about verification changes: quotes are still extracted, still
  // checked character by character against the page, still dropped or
  // recovered by the server's guard rails. We stop printing the raw text; the
  // reason and the sources carry the card.

  for (const e of (c.evidence || []).slice(0, MAX_SOURCES)) {
    const a = document.createElement("a");
    a.className = "src";
    a.href = e.url;
    a.target = "_blank";
    a.rel = "noopener noreferrer";
    a.title = e.title || e.url;
    const name = document.createElement("span");
    name.className = "host";
    name.textContent = host(e.url);
    a.appendChild(name);
    card.appendChild(a);
  }

  const foot = document.createElement("div");
  foot.className = "card-foot";
  if (c.confidence && c.confidence !== "none") {
    const conf = document.createElement("span");
    conf.className = "conf";
    conf.dataset.level = c.confidence;
    conf.setAttribute("aria-label", `${c.confidence} confidence`);
    conf.innerHTML = "<i></i><i></i><i></i>";
    conf.appendChild(document.createTextNode(` ${c.confidence} confidence`));
    foot.appendChild(conf);
  }
  // `kind` and `shape` are for the judge, not for a person -- "world_fact ·
  // count" tells a reader nothing they wanted to know. What a person actually
  // wants here is how long it took and how much was read.
  const meta = document.createElement("span");
  meta.className = "card-meta";
  const n = Math.min((c.evidence || []).length, MAX_SOURCES);
  meta.textContent = [
    c.tookMs >= 100 ? `${(c.tookMs / 1000).toFixed(1)}s` : "",
    n ? `${n} source${n === 1 ? "" : "s"}` : "",
  ].filter(Boolean).join(" · ");
  foot.appendChild(meta);
  card.appendChild(foot);

  document.body.appendChild(card);
}

// ---------------------------------------------------------------------------
// chrome

function paintChrome() {
  const busy = [...state.claims.values()].some((c) => !c.verdict && c.checkable !== false);
  el("stxt").textContent = state.status;
  el("status").dataset.busy = busy ? "1" : "0";
  el("rotor").textContent = busy ? "◜" : "◌";

  const b = state.budget;
  const box = el("budget");
  if (b.pool === "byok" || !b.claimsCap) {
    box.textContent = "";
  } else {
    box.textContent = `${b.claimsLeft}/${b.claimsCap}`;
    box.dataset.out = b.claimsLeft <= 0 ? "1" : "0";
    box.title = `${b.claimsLeft} checks left in this session`;
  }

  const err = el("error");
  if (state.error) {
    err.hidden = false;
    err.innerHTML = "<b>Not working</b>";
    err.appendChild(document.createTextNode(state.error));
  } else {
    err.hidden = true;
  }
}

// ---------------------------------------------------------------------------

export function render() {
  const box = lyr();

  // Whether to keep following the conversation is decided from where the
  // reader actually is, measured before anything is appended -- never from a
  // scroll event, which can coalesce or be missed, and one missed event pins
  // the transcript to the bottom for the rest of the session.
  const wasAtBottom =
    box.scrollHeight - box.scrollTop - box.clientHeight <= PIN_SLOP;

  const { lines, closed } = buildLines();

  // Rebuild only from the first line that actually changed. Everything above
  // it keeps its DOM, its text selection and its running animations.
  const sigs = lines.map(lineSignature);
  const lineSigsBefore = lineSigs.length;
  let from = 0;
  while (from < sigs.length && from < lineSigs.length && sigs[from] === lineSigs[from]) from += 1;

  if (from < lineSigs.length || from < sigs.length) {
    const nodes = [...box.querySelectorAll(".line")];
    for (let i = from; i < nodes.length; i += 1) nodes[i].remove();
    const frag = document.createDocumentFragment();
    for (let i = from; i < lines.length; i += 1) frag.appendChild(buildLine(lines[i]));
    box.appendChild(frag);
  }
  lineSigs = sigs;

  const cold = el("cold");
  if (cold) cold.hidden = lines.length > 0 || Boolean(state.interim);

  paintInterim(closed);
  paintClaims();
  paintLineStates(lines);
  flashField();
  paintTally();
  paintChrome();

  if (openCard) {
    const c = state.claims.get(openCard);
    if (c && cardSignature(c) !== cardSig) showCard(openCard);
  }

  if (wasAtBottom) {
    pinned = true;
    unread = 0;
    newCap = false;
    box.scrollTo({ top: box.scrollHeight, behavior: "auto" });
  } else {
    pinned = false;
    if (sigs.length !== lineSigsBefore) unread += 1;
  }
  paintJump();
}

// --- one listener for the whole transcript, however much of it there is -----

document.addEventListener("click", (ev) => {
  const mark = ev.target.closest && ev.target.closest(".mark");
  if (mark) {
    const id = mark.dataset.claimId;
    if (openCard === id) { closeCard(); paintClaims(); }
    else { showCard(id); paintClaims(); }
    return;
  }
  if (!ev.target.closest || !ev.target.closest(".card")) { closeCard(); paintClaims(); }
});

document.addEventListener("keydown", (ev) => {
  if (ev.key === "Escape" && openCard) { closeCard(); paintClaims(); return; }
  const mark = ev.target.closest && ev.target.closest(".mark");
  if (mark && (ev.key === "Enter" || ev.key === " ")) {
    ev.preventDefault();
    showCard(mark.dataset.claimId);
    paintClaims();
  }
});

// Autoscroll only while pinned, and never yank the page while someone is
// reading further up. Attached immediately rather than on DOMContentLoaded:
// this is a module, the element is already parsed, and if this listener ever
// fails to attach the transcript pins to the bottom forever and a whole
// conversation becomes unreachable.
(function watchScroll() {
  const box = lyr();
  if (!box) return;
  box.addEventListener("scroll", () => {
    const wasPinned = pinned;
    pinned = box.scrollHeight - box.scrollTop - box.clientHeight <= PIN_SLOP;
    if (pinned && !wasPinned) {
      unread = 0;
      newCap = false;
      paintJump();
    }
  }, { passive: true });
})();
