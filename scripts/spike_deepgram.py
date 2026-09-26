"""Prove the speech-to-text path works, without a microphone and without a browser.

    python scripts/spike_deepgram.py
    python scripts/spike_deepgram.py "Notion charges five hundred dollars."

Uses macOS `say` to synthesise a sentence, converts it to exactly the format
we send from the browser (16 kHz mono signed 16-bit PCM), streams it to
Deepgram in the same size chunks the AudioWorklet produces, and prints the
drafts and finals as they come back.

This exists because "the microphone does not work" has at least four possible
causes -- bad key, bad URL parameters, wrong audio format, browser permissions
-- and this script eliminates the first three in five seconds.
"""

from __future__ import annotations

import asyncio
import subprocess
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from server import config  # noqa: E402
from server.transcribe import DeepgramRelay  # noqa: E402

CHUNK_BYTES = 2048 * 2  # the worklet's 2048 samples, 2 bytes each


def synthesise(text: str) -> bytes:
    """Speak `text` and return raw 16 kHz mono PCM, exactly what the browser sends."""
    with tempfile.TemporaryDirectory() as tmp:
        aiff = Path(tmp) / "say.aiff"
        raw = Path(tmp) / "say.raw"
        subprocess.run(["say", "-o", str(aiff), text], check=True)
        subprocess.run(
            [
                "afconvert", str(aiff), str(raw),
                "-f", "caff", "-d", "LEI16@16000", "-c", "1",
            ],
            check=True, capture_output=True,
        )
        data = raw.read_bytes()
    # A CAF file has a header before the samples. Find the 'data' chunk rather
    # than guessing an offset, or the first fraction of a second is noise.
    marker = data.find(b"data")
    return data[marker + 12:] if marker != -1 else data


async def main(text: str) -> int:
    print(f"synthesising: {text!r}")
    pcm = synthesise(text)
    seconds = len(pcm) / 2 / config.AUDIO_SAMPLE_RATE
    print(f"{len(pcm)} bytes of PCM, {seconds:.1f}s of audio\n")

    finals: list[str] = []
    done = asyncio.Event()

    def on_interim(t: str) -> None:
        print(f"  draft   {t}")

    def on_final(t: str, speech_final: bool) -> None:
        print(f"  FINAL   {t}")
        finals.append(t)

    def on_utterance_end() -> None:
        print("  (utterance end)")
        done.set()

    relay = DeepgramRelay(on_interim, on_final, on_utterance_end)
    await relay.start()
    print("connected to deepgram, streaming...\n")

    # Stream at real speed, as the browser does. Blasting it as fast as
    # possible works too, but then the timing signals mean nothing.
    for i in range(0, len(pcm), CHUNK_BYTES):
        await relay.send_audio(pcm[i:i + CHUNK_BYTES])
        await asyncio.sleep(CHUNK_BYTES / 2 / config.AUDIO_SAMPLE_RATE)

    try:
        await asyncio.wait_for(done.wait(), timeout=6.0)
    except asyncio.TimeoutError:
        pass
    await relay.close()

    print()
    if finals:
        print("TRANSCRIPT:", " ".join(finals))
        print("\nSpeech to text works. If the browser still shows nothing,")
        print("the problem is the microphone or the page, not Deepgram.")
        return 0

    print("NOTHING CAME BACK. The audio format or the key is wrong.")
    return 1


if __name__ == "__main__":
    sentence = " ".join(sys.argv[1:]) or "Messi scored forty five goals last season."
    raise SystemExit(asyncio.run(main(sentence)))
