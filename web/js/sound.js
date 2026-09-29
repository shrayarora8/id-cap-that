// Two sounds, for the two verdicts that matter.
//
// Synthesised rather than fetched: no files to download, nothing to fail at a
// venue, and the tones stay tunable while we are still deciding what they
// should be. These are placeholders — design round 8 picks the real ones.
//
// On by default: the sound is part of the product, and a verdict landing
// without it is a quieter moment than it should be. It can be switched off
// from the top bar, and that choice is remembered per browser.
//
// Nothing plays before the viewer has interacted with the page -- browsers
// refuse it, and by the time any verdict exists they have pressed Record,
// tapped an example or typed a claim.

let ctx = null;
let on = true;

try {
  on = localStorage.getItem("cap.sound") !== "off";
} catch {
  // Private window or blocked storage: fall back to on, the default.
}

export function enabled() {
  return on;
}

export function toggle() {
  on = !on;
  try {
    localStorage.setItem("cap.sound", on ? "on" : "off");
  } catch {
    // Not remembering the choice is survivable; failing here is not.
  }
  if (on) ping([880, 1180], "sine", 0.05);
  return on;
}

function ping(notes, type, gain) {
  if (!on) return;
  try {
    ctx = ctx || new (window.AudioContext || window.webkitAudioContext)();
    if (ctx.state === "suspended") ctx.resume();
    const t0 = ctx.currentTime;
    notes.forEach((f, i) => {
      const osc = ctx.createOscillator();
      const amp = ctx.createGain();
      osc.type = type;
      osc.frequency.setValueAtTime(f, t0 + i * 0.1);
      amp.gain.setValueAtTime(0.0001, t0 + i * 0.1);
      amp.gain.exponentialRampToValueAtTime(gain, t0 + i * 0.1 + 0.012);
      amp.gain.exponentialRampToValueAtTime(0.0001, t0 + i * 0.1 + 0.18);
      osc.connect(amp);
      amp.connect(ctx.destination);
      osc.start(t0 + i * 0.1);
      osc.stop(t0 + i * 0.1 + 0.22);
    });
  } catch {
    // No audio device, autoplay refused, context limit. Never fatal.
  }
}

/** The only thing the renderer calls. */
export function verdict(kind) {
  if (kind === "SUPPORTED") ping([660, 990], "sine", 0.07);
  else if (kind === "CONTRADICTED") ping([320, 196], "square", 0.06);
}
