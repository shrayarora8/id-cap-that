"""Every knob in one place, so nothing important is buried in a function."""

from __future__ import annotations

import os
from pathlib import Path

from dotenv import load_dotenv

ROOT = Path(__file__).parent.parent

# Load this project's .env no matter where the entry point lives. Plain
# load_dotenv() searches upward from the caller, so a script run from another
# directory would silently see no keys at all and fail in a confusing place.
load_dotenv(ROOT / ".env")

# --- models -----------------------------------------------------------------
SORTER_MODEL = "claude-haiku-4-5"   # finds claims in a window of speech
JUDGE_MODEL = "claude-haiku-4-5"    # weighs evidence, returns the verdict

# --- speech to text ---------------------------------------------------------
DEEPGRAM_MODEL = "nova-3"
DEEPGRAM_LANGUAGE = "en-US"

# Audio on the wire. Raw PCM, not a container: iOS Safari will not produce
# Opus, and a codec we cannot rely on is a silent failure on the device we
# most want this to work on. 16 kHz is what nova-3 wants and it is a quarter
# the bytes of 48 kHz for no accuracy loss on speech.
AUDIO_SAMPLE_RATE = 16000
AUDIO_CHANNELS = 1

# How long a gap counts as the end of a phrase.
DEEPGRAM_ENDPOINTING_MS = 300
# How long a silence before Deepgram calls the whole utterance finished.
#
# 1000 is DEEPGRAM'S FLOOR, not a preference. Anything lower is rejected at
# the handshake with HTTP 400 "beneath the configured step size", which kills
# the microphone entirely -- the connection never opens, so no audio is ever
# sent and the transcript stays empty with no clue why. Trying 700 here to
# save 300ms cost an hour. Do not lower it.
DEEPGRAM_UTTERANCE_END_MS_FLOOR = 1000
DEEPGRAM_UTTERANCE_END_MS = 1000

# Words Deepgram would otherwise guess wrong. Nova-3 boosts these ("keyterm
# prompting"), up to 100. Names of people, products and companies are exactly
# what a transcriber mangles and a search engine cannot recover from.
DEEPGRAM_KEYTERMS = [
    "Ballon d'Or", "Lionel Messi", "Cristiano Ronaldo", "Inter Miami",
    "Premier League", "Firecrawl", "Moss", "Deepgram", "Anthropic",
    "Claude", "Notion", "Shray",
]

# --- chunking ---------------------------------------------------------------
WINDOW_MAX_SENTENCES = 3
WINDOW_SILENCE_MS = 1000
# A real stop: close whatever is pending, however unfinished.
#
# This is the ONLY rule that can split a sentence, because it deliberately
# ignores is_closeable -- otherwise unpunctuated speech would sit on screen
# forever. 2500 was too aggressive: someone talking to a demo pauses for two
# and a half seconds mid-sentence all the time, and the split turned
# "revolutionize the market through | cross functional synergy." into two
# windows, the second of which was three words and got dropped as too short.
# The buzzwords then went unflagged, which is the entire point of the feature.
WINDOW_HARD_SILENCE_MS = 4000
WINDOW_MAX_MS = 12_000
WINDOW_MIN_SENTENCE_WORDS = 4
WINDOW_MAX_WORDS_UNPUNCTUATED = 25

# --- budget -----------------------------------------------------------------
# Three pools. The reserved one exists so that visitors poking at the demo can
# never starve the demo itself ten minutes before it is presented.
CLAIMS_PER_PUBLIC_SESSION = 12
CLAIMS_PER_RESERVED_SESSION = 200
MAX_LLM_CALLS_PER_SESSION = 120

# --- recording --------------------------------------------------------------
# Every session writes its message stream to disk. This is how the UI gets
# developed without talking, how a regression is reproduced exactly, and what
# scripts/replay.py plays back when the venue wifi dies.
RECORD_SESSIONS = os.getenv("RECORD_SESSIONS", "1") == "1"
RECORDINGS_DIR = ROOT / "recordings"

# --- logging ----------------------------------------------------------------
LOG_LEVEL = os.getenv("LOG_LEVEL", "INFO").upper()
LIBRARY_LOG_LEVEL = os.getenv("LIBRARY_LOG_LEVEL", "WARNING").upper()


def require(name: str) -> str:
    value = os.getenv(name, "").strip()
    if not value:
        raise RuntimeError(f"{name} is missing from .env")
    return value
