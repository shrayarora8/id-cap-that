// Runs on the audio thread, not the main thread.
//
// Its whole job: take whatever sample rate the device's microphone runs at,
// convert to 16-bit signed integers, and post them back in chunks. It does
// NOT resample -- the AudioContext is constructed at the target rate and the
// browser resamples for us, which it does better than we could here.
//
// This exists instead of MediaRecorder because iOS Safari will not give us
// Opus. It gives AAC in an mp4 container, which Deepgram's streaming endpoint
// will not take. Raw PCM works identically on every browser we care about.

const CHUNK_SAMPLES = 2048; // ~128ms at 16 kHz. Small enough to feel live.

class PCMWorklet extends AudioWorkletProcessor {
  constructor() {
    super();
    this.buffer = new Int16Array(CHUNK_SAMPLES);
    this.filled = 0;
  }

  process(inputs) {
    const channel = inputs[0] && inputs[0][0];
    if (!channel) return true; // no input yet; keep the node alive

    for (let i = 0; i < channel.length; i++) {
      // Float -1..1 to signed 16-bit. Clamp first: a sample slightly over 1.0
      // wraps to a large negative number and you hear it as a loud click.
      const sample = Math.max(-1, Math.min(1, channel[i]));
      this.buffer[this.filled++] = sample < 0 ? sample * 0x8000 : sample * 0x7fff;

      if (this.filled === CHUNK_SAMPLES) {
        // Transfer the buffer rather than copying it, then allocate a fresh
        // one -- a transferred ArrayBuffer is detached and unusable here.
        const out = this.buffer;
        this.port.postMessage(out.buffer, [out.buffer]);
        this.buffer = new Int16Array(CHUNK_SAMPLES);
        this.filled = 0;
      }
    }
    return true;
  }
}

registerProcessor("pcm-worklet", PCMWorklet);
