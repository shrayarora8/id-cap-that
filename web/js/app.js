// Wiring only. Every decision lives on the server; this file moves messages
// between the socket, the state object and the renderer.

import * as ws from "./ws.js";
import * as audio from "./audio.js";
import * as sound from "./sound.js";
import { state, apply } from "./state.js";
import { render, dismissCold } from "./render.js";

const el = (id) => document.getElementById(id);

// The listen button holds a status dot as well as its label, so its text is
// set on the last child rather than by blowing away its contents.
function listenLabel(text) {
  const b = el("listen");
  b.lastChild.nodeType === Node.TEXT_NODE
    ? (b.lastChild.textContent = text)
    : b.appendChild(document.createTextNode(text));
}

ws.connect({
  onMessage: (msg) => {
    if (apply(msg)) render();
  },
  onOpen: () => {
    state.status = "connected";
    render();
  },
  onClose: () => {
    state.status = "reconnecting…";
    state.listening = false;
    starting = false;
    setListen("off");
    audio.stop();
    render();
  },
});

// --- the text box: the whole pipeline without a microphone ------------------

el("say").addEventListener("keydown", (ev) => {
  if (ev.key !== "Enter") return;
  const text = ev.target.value.trim();
  if (!text) return;
  ws.sendJSON({ type: "inject_text", text });
  ev.target.value = "";
});

// --- the microphone ---------------------------------------------------------

// A click must change the button on the click, not when the server answers.
// Waiting on a Deepgram round trip left it looking dead for a second or two,
// which is exactly how a user ends up pressing it four times.
let starting = false;

function setListen(mode) {
  const b = el("listen");
  b.classList.toggle("on", mode === "on");
  b.classList.toggle("starting", mode === "starting");
  b.disabled = mode === "starting";
  b.setAttribute("aria-pressed", String(mode === "on"));
  listenLabel(mode === "on" ? "Stop" : mode === "starting" ? "Starting" : "Record");
}

el("listen").addEventListener("click", async () => {
  if (starting) return;            // a second click while the mic is opening
  if (state.listening) {
    state.listening = false;
    setListen("off");
    await audio.stop();
    ws.sendJSON({ type: "stop_listening" });
    return;
  }

  if (!audio.isSecure()) {
    state.status = "microphone needs https — open the tunnel URL, not the IP";
    render();
    return;
  }
  if (!audio.isSupported()) {
    state.status = "this browser has no AudioWorklet — use the text box";
    render();
    return;
  }

  // Feedback first, work second.
  starting = true;
  setListen("starting");
  state.status = "opening the microphone…";
  render();

  // Order matters: the server must have a Deepgram socket open before the
  // first audio frame arrives, or those frames are dropped on the floor.
  ws.sendJSON({ type: "start_listening" });

  try {
    // audio.start now reports WHICH microphone it opened. Showing it is the
    // fix for a real confusion: on a Mac with an iPhone nearby, macOS hands
    // the browser the phone, the laptop's own mic is never heard, and nothing
    // on screen says so.
    const { label } = await audio.start((buf) => ws.sendBinary(buf));
    state.listening = true;
    setListen("on");
    state.status = `listening · ${label}`;
  } catch (err) {
    setListen("off");
    state.status = `microphone blocked: ${err.message}`;
    ws.sendJSON({ type: "stop_listening" });
  }
  starting = false;
  render();
});

// --- the cold start: a stranger, no microphone, nobody explaining ----------

document.querySelectorAll(".eg").forEach((b) => {
  b.addEventListener("click", () => {
    ws.sendJSON({ type: "inject_text", text: b.dataset.eg });
  });
});

el("cold-x").addEventListener("click", () => {
  dismissCold();
  render();
});

// --- sound ------------------------------------------------------------------

el("mute").addEventListener("click", (ev) => {
  const on = sound.toggle();
  ev.currentTarget.setAttribute("aria-pressed", String(on));
  ev.currentTarget.title = on ? "Sound on" : "Sound off";
});
el("mute").setAttribute("aria-pressed", String(sound.enabled()));
el("mute").title = sound.enabled() ? "Sound on" : "Sound off";

// Which build is actually running. The tier badges were reported as still on
// screen hours after they were deleted, and there was no way to tell from the
// page whether it was old code or a stale checkout. Now there is.
export const BUILD = "d381dd9";
document.documentElement.dataset.build = BUILD;
console.info("i'd cap that — build", BUILD);

render();

// --- installable app --------------------------------------------------------
// Registered last and failure is non-fatal: a service worker that will not
// install must never stop the app itself from running.
if ("serviceWorker" in navigator) {
  window.addEventListener("load", () => {
    navigator.serviceWorker.register("/sw.js").catch(() => {});
  });
}
