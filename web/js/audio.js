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
let chosenDeviceId = null;   // null = let the browser decide

// A device that macOS Continuity hands over: the Mac quietly uses a nearby
// iPhone as the default input, so getUserMedia returns the phone's microphone
// and the laptop's own mic is never heard. Nothing on screen says so, and
// disconnecting the phone does not hand the input back.
const CONTINUITY = /iphone|ipad|continuity/i;

export function isSupported() {
  return !!(navigator.mediaDevices?.getUserMedia && window.AudioWorklet);
}

// getUserMedia is blocked on anything but a secure origin. On a phone that
// means the page must be https, which is why there is a tunnel.
export function isSecure() {
  return window.isSecureContext;
}

/** Every microphone the browser will admit to, once permission exists. */
export async function listMicrophones() {
  const devices = await navigator.mediaDevices.enumerateDevices();
  return devices
    .filter((d) => d.kind === "audioinput")
    .map((d) => ({
      id: d.deviceId,
      label: d.label || "Microphone",
      isPhone: CONTINUITY.test(d.label || ""),
    }));
}

/** Use this microphone from the next start(). null goes back to the default. */
export function setMicrophone(deviceId) {
  chosenDeviceId = deviceId;
}

export function currentMicrophone() {
  return chosenDeviceId;
}

/**
 * Pick a sensible default when the user has not chosen.
 *
 * The bug: on a Mac with an iPhone nearby, Continuity makes the phone the
 * default audio input. getUserMedia dutifully returns the phone, the laptop's
 * own microphone is never heard, and unplugging the phone does not hand the
 * input back -- it just stops working. A judge picking this up would have no
 * idea why it had gone deaf.
 *
 * So when the default is a phone and a real local microphone exists, use the
 * local one. An explicit choice always wins over this.
 */
async function preferredDeviceId() {
  if (chosenDeviceId) return chosenDeviceId;
  try {
    const mics = await listMicrophones();
    if (!mics.length) return null;
    const local = mics.find((m) => !m.isPhone);
    const phoneIsDefault = mics[0] && mics[0].isPhone;
    if (phoneIsDefault && local) return local.id;
  } catch {
    // enumerateDevices can fail before permission is granted; the default
    // is fine in that case.
  }
  return null;
}

/**
 * Start capturing. `onChunk` receives an ArrayBuffer of 16-bit PCM, ready to
 * put straight on the wire. Returns { sampleRate, label }.
 */
export async function start(onChunk) {
  // A first permission prompt has to happen before device labels exist, so
  // this may run twice on the very first use: once to get permission, once
  // to open the microphone we actually want.
  let deviceId = await preferredDeviceId();

  const constraints = (id) => ({
    audio: {
      ...(id ? { deviceId: { exact: id } } : {}),
      channelCount: 1,
      echoCancellation: true,
      noiseSuppression: true,
      autoGainControl: true,
    },
  });

  stream = await navigator.mediaDevices.getUserMedia(constraints(deviceId));

  if (!deviceId) {
    // Labels are only readable after permission. Now that we have it, check
    // whether we were handed a phone and swap if so.
    const better = await preferredDeviceId();
    if (better) {
      stream.getTracks().forEach((t) => t.stop());
      stream = await navigator.mediaDevices.getUserMedia(constraints(better));
      deviceId = better;
    }
  }

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

  const label = stream.getAudioTracks()[0]?.label || "microphone";
  return { sampleRate: context.sampleRate, label };
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
