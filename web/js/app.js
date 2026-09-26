// Wiring only. Every decision lives on the server; this file moves messages
// between the socket, the state object and the renderer.

import * as ws from "./ws.js";
import * as audio from "./audio.js";
import { state, apply } from "./state.js";
import { render } from "./render.js";

const el = (id) => document.getElementById(id);

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
    el("listen").textContent = "start listening";
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
    el("listen").textContent = "stop";
    state.status = `listening at ${rate} Hz`;
  } catch (err) {
    state.status = `microphone blocked: ${err.message}`;
    ws.sendJSON({ type: "stop_listening" });
  }
  render();
});

render();

// --- installable app --------------------------------------------------------
// Registered last and failure is non-fatal: a service worker that will not
// install must never stop the app itself from running.
if ("serviceWorker" in navigator) {
  window.addEventListener("load", () => {
    navigator.serviceWorker.register("/sw.js").catch(() => {});
  });
}
