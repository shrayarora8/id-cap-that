// Wiring only. Every decision lives on the server; this file moves messages
// between the socket, the state object and the renderer.

import * as ws from "./ws.js";
import * as audio from "./audio.js";
import * as sound from "./sound.js";
import { state, apply } from "./state.js";
import { render } from "./render.js";

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
    el("listen").classList.remove("on");
    el("listen").setAttribute("aria-pressed", "false");
    listenLabel("Listen");
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

el("listen").addEventListener("click", async () => {
  if (state.listening) {
    state.listening = false;
    el("listen").classList.remove("on");
    el("listen").setAttribute("aria-pressed", "false");
    listenLabel("Listen");
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

  // Order matters: the server must have a Deepgram socket open before the
  // first audio frame arrives, or those frames are dropped on the floor.
  ws.sendJSON({ type: "start_listening" });

  try {
    const rate = await audio.start((buf) => ws.sendBinary(buf));
    state.listening = true;
    el("listen").classList.add("on");
    el("listen").setAttribute("aria-pressed", "true");
    listenLabel("Stop");
    state.status = `listening at ${rate} Hz`;
  } catch (err) {
    state.status = `microphone blocked: ${err.message}`;
    ws.sendJSON({ type: "stop_listening" });
  }
  render();
});

// --- the cold start: a stranger, no microphone, nobody explaining ----------

document.querySelectorAll(".eg").forEach((b) => {
  b.addEventListener("click", () => {
    ws.sendJSON({ type: "inject_text", text: b.dataset.eg });
  });
});

// --- sound ------------------------------------------------------------------

el("mute").addEventListener("click", (ev) => {
  const on = sound.toggle();
  ev.currentTarget.setAttribute("aria-pressed", String(on));
  ev.currentTarget.textContent = on ? "Sound on" : "Sound off";
});
el("mute").setAttribute("aria-pressed", String(sound.enabled()));
el("mute").textContent = sound.enabled() ? "Sound on" : "Sound off";

render();

// --- installable app --------------------------------------------------------
// Registered last and failure is non-fatal: a service worker that will not
// install must never stop the app itself from running.
if ("serviceWorker" in navigator) {
  window.addEventListener("load", () => {
    navigator.serviceWorker.register("/sw.js").catch(() => {});
  });
}
