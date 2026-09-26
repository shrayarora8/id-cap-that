// Microphone to raw PCM, for both laptops and phones.
//
// The one thing to know: we ask for an AudioContext at exactly the sample
// rate Deepgram was told to expect. The browser resamples the microphone into
// that rate for us. Doing it ourselves in JS was the obvious approach and it
// is the wrong one -- a naive decimation aliases, and it sounds fine to a
// human while measurably hurting recognition.

const TARGET_RATE = 16000;

let context = null;
let node = null;
let stream = null;

export function isSupported() {
  return !!(navigator.mediaDevices?.getUserMedia && window.AudioWorklet);
}

// getUserMedia is blocked on anything but a secure origin. On a phone that
// means the page must be https, which is why there is a tunnel.
export function isSecure() {
  return window.isSecureContext;
}

/**
 * Start capturing. `onChunk` receives an ArrayBuffer of 16-bit PCM, ready to
 * put straight on the wire. Returns the real sample rate in use.
 */
export async function start(onChunk) {
  stream = await navigator.mediaDevices.getUserMedia({
    audio: {
      channelCount: 1,
      echoCancellation: true,
      noiseSuppression: true,
      autoGainControl: true,
    },
  });

  // Safari still needs the prefixed constructor.
  const Ctx = window.AudioContext || window.webkitAudioContext;
  context = new Ctx({ sampleRate: TARGET_RATE });

  // iOS starts every AudioContext suspended until a user gesture has run.
  // The listen button is that gesture, but resume() is still required.
  if (context.state === "suspended") await context.resume();

  await context.audioWorklet.addModule("/js/pcm-worklet.js");

  const source = context.createMediaStreamSource(stream);
  node = new AudioWorkletNode(context, "pcm-worklet");
  node.port.onmessage = (ev) => onChunk(ev.data);

  source.connect(node);
  // Connecting to the destination would play your own voice back at you.
  // The worklet pulls input regardless of whether it is connected onward in
  // Chrome, but Safari will not run a node with no downstream, so it goes to
  // a muted gain node instead of the speakers.
  const mute = context.createGain();
  mute.gain.value = 0;
  node.connect(mute);
  mute.connect(context.destination);

  return context.sampleRate;
}

export async function stop() {
  if (node) {
    node.port.onmessage = null;
    node.disconnect();
    node = null;
  }
  if (stream) {
    stream.getTracks().forEach((t) => t.stop()); // releases the mic indicator
    stream = null;
  }
  if (context) {
    await context.close();
    context = null;
  }
}
