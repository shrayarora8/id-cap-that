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
# Claim extraction. Measured on the real sorter prompt:
#   openai/gpt-oss-20b   471ms median, passed every quality case
#   claude-haiku-4-5    1700ms
#
# So the open model runs it, and Claude catches it when Groq cannot. The free
# tier allows 8,000 tokens a minute and one sorter call costs about 2,000, so
# roughly three claims a minute before it starts refusing -- and a normal
# conversation produces more than that. The fallback is not a nicety, it is
# the thing that makes this usable at all.
#
# A rejection comes back in ~60ms, so switching costs the user nothing they
# could notice. Set SORTER_PROVIDER to "anthropic" to turn all of this off.
SORTER_PROVIDER = "groq"
# Measured on 18 cases with the paid tier, no rate limiting to corrupt it:
# the 120b gets 15/18 against the 20b's 14/18, catches all nine real factual
# claims, never returns a malformed schema, and costs $0.402 per thousand
# claims against $0.383 -- five per cent, because it answers more concisely
# (261 output tokens against 490) and claws most of the rate back.
#
# qwen3.8-27b was tested and rejected: 11/18, silently dropping six of the
# nine real claims. Losing a claim is the one failure this product cannot
# have, whatever it saves.
SORTER_GROQ_MODEL = "openai/gpt-oss-120b"
# The ceiling on a hang. A refusal is instant; only a stall could cost time.
GROQ_TIMEOUT_S = 4.0

SORTER_MODEL = "claude-haiku-4-5"   # the fallback, and the judge
JUDGE_MODEL = "claude-haiku-4-5"    # weighs evidence, returns the verdict

# The judge is 91% of the bill: it reads the claim AND four evidence
# passages (~2,700 tokens against the sorter's ~1,500), and Haiku charges
# ten times Groq's rate. Moving it takes $4.74 per thousand claims to $1.07.
#
# It is also the harder job. The judge must return a quote that our own code
# then verifies word for word, compare quantities, and write the correction.
# A weaker model fails that QUIETLY -- the quote stops matching, the rail
# downgrades it, and the product just gets vaguer rather than visibly broken.
#
# So this is measured against scripts/verify_fixes.py before it is trusted,
# and it is one line to put back.
JUDGE_PROVIDER = "groq"
JUDGE_GROQ_MODEL = "openai/gpt-oss-120b"

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
# Close a window once it holds this many phrases -- but only if the thought
# sounds finished. This used to close unconditionally, which cut sentences in
# half while someone was talking at pace: "Taylor Swift has won 28" closed as
# one window and "Grammys." became the next, a single word that the pre-filter
# then dropped as too short. The claim vanished with no explanation.
WINDOW_MAX_SENTENCES = 3
# ...and this many regardless, or a speaker who never pauses would never be
# checked at all.
WINDOW_HARD_MAX_SENTENCES = 6

# How many previous windows the sorter sees when resolving "it" and "they".
# One was not enough: in real speech the subject is often several sentences
# back, with asides in between, and an unresolvable pronoun means the claim is
# either dropped or searched for with no idea who it is about.
CONTEXT_WINDOWS = 4
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

# --- retrieval --------------------------------------------------------------
# Snippet-first. A search returns titles and descriptions that are already
# relevant and cost one credit; most claims are settled by them. Pages are
# fetched only when the judge says its evidence was too thin, which is what
# turns a 9-second verdict into a 4-second one and a 6-credit claim into a
# 1-credit one.
SEARCH_RESULTS = 6
PAGES_TO_FETCH = 3          # only on the escalation path
FETCH_TIMEOUT_S = 8.0
PASSAGES_FOR_JUDGE = 5
PRESELECT_PASSAGES = 15
PASSAGES_PER_SOURCE = 2
MAX_PAGE_CHARS = 60_000

# Firecrawl allows 10 requests a minute.
#
# This was set to 8 "to be safe" and it was the worst bug in the build. The
# limiter waits for a slot rather than failing, so once the bucket was empty
# a claim simply stopped for up to sixty seconds with nothing on screen
# explaining it. Measured live: 54 seconds for a Taylor Swift claim. Three
# things caused the bucket to empty that fast -- a speculative search on every
# window (now deleted, it never saved any time), a second search whenever the
# claim had an official domain (now conditional), and this being under the
# real limit for no reason.
FIRECRAWL_PER_MINUTE = 10

# How long to wait for a Firecrawl slot before giving up on a claim.
#
# Six seconds was too impatient. Reading a transcript at pace produces claims
# faster than ten requests a minute, so a queue of seven seconds is ordinary
# -- and giving up at six meant "Stripe has 8,000 employees" came back with
# no sources at all, on a run where every other claim worked. An answer after
# ten seconds is worth far more than no answer after six.
#
# It is still bounded, because the failure this replaced was a claim silently
# stalling for most of a minute.
MAX_RATE_LIMIT_WAIT_S = 20.0

# --- Moss: what we have already read ------------------------------------
# Every passage we ever fetch goes into a Moss index and stays there. Before
# spending a Firecrawl request, a new claim asks Moss whether we already hold
# something that answers it.
#
# The rule this lives under is Shray's, and it is the right one: this must
# make things FASTER, never slower. A Moss query is in-process and takes
# milliseconds; a Firecrawl search takes well over a second. So a hit saves
# about a second and a credit, and a miss costs a few hundred milliseconds.
# The threshold is set high enough that a miss is the common outcome early in
# a session and a hit only happens when the passages genuinely match.
# OFF.
#
# Moss bills per MINUTE of open session, not per query. _moss_session() opens
# one and keeps it for the life of the process, so a server left running all
# day bills all day -- whether or not a single claim is checked. 216 of 250
# minutes went in an afternoon of development, heading for about $90 of
# overage, and almost none of it was doing any work.
#
# That is my mistake and it is a bad one: I treated a session like a
# connection pool. A per-minute resource must be opened for the work and
# closed after it, or not used at all.
#
# Everything still works with this off. recall() returns nothing, remember()
# does nothing, and every claim searches as it did before Moss existed. The
# only loss is the ~15ms shortcut on a repeated subject.
MOSS_ENABLED = False
# A remembered passage must score at least this to be trusted without a fresh
# search. Moss scores are cosine-like; this is deliberately strict, because a
# wrong shortcut costs a wrong verdict and a right one only saves a second.
MOSS_MIN_SCORE = 0.62
# ...and we need at least this many of them, so one lucky match cannot
# replace a search on its own.
MOSS_MIN_HITS = 3
# If Moss has not answered in this long, stop waiting and just search. It is
# an optimisation; it is never allowed to become the slow part.
MOSS_TIMEOUT_S = 1.2

# How many times one claim may escalate before we accept the evidence we have.
MAX_ESCALATIONS = 1

# --- budget -----------------------------------------------------------------
# Three pools. The reserved one exists so that visitors poking at the demo can
# never starve the demo itself ten minutes before it is presented.
# The total Firecrawl credits VISITORS may spend, ever, this month.
#
# The per-session cap below resets on every reconnect, so on its own it stops
# nobody: refresh the page and you get a fresh allowance. This is the ceiling
# that actually holds, it is counted on disk so a restart does not forget it,
# and it covers visitors only. The demo machine is on loopback and spends from
# its own reserve, so a room full of people trying it can never leave the demo
# itself unable to run.
#
# CHANGE THIS ONE NUMBER to decide how much of the month's allowance other
# people are allowed to use.
PUBLIC_CREDIT_CEILING = 300

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
# Postgres for the page and search cache. Unset is fine and normal: the store
# falls back to JSON files on disk, which is what local development uses.
# It matters on Render, which gives a free service no persistent disk, so
# every deploy currently throws away every page we have ever fetched.
DATABASE_URL = os.getenv("DATABASE_URL", "").strip()

# --- free evidence sources --------------------------------------------------
# Wikipedia and the subject's own website, fetched directly. Measured at 229ms
# for both in parallel, against ~1300ms and a credit for a search. Ten new
# claims settled ten of ten from these alone.
FREE_SOURCES_FIRST = True

# Answer the same question twice without doing the work twice.
#
# The page cache only ever stopped a second FETCH. An identical claim still ran
# both model calls and the whole search path, which is why the database looked
# like it was doing nothing. This remembers the evidence a claim was settled
# on, so a repeat skips every network leg -- and the judge's cache hits too,
# because its prompt contains those passages byte for byte.
#
# Verdicts are NOT stored. Guard rails run in code after the model answers, so
# a repeat claim is re-verified rather than replayed, and fixing a rail
# retroactively corrects everything already cached.
CLAIM_CACHE = True

# Evidence is about a SUBJECT, not a sentence. Passages fetched for "Bolt ran
# 9.58" answer any claim about Bolt's hundred metres, so they are filed under
# him too and a reworded claim reuses them instead of paying again. This is
# the job Moss did before it was turned off for billing by the session-minute.
SUBJECT_MEMORY = True
SUBJECT_MEMORY_MAX = 24        # passages held per subject
FREE_SOURCE_TIMEOUT_S = 6.0
# Below this many passages, the free sources have not found enough to be worth
# a judge call, so we go straight to search instead of paying to be told so.
FREE_EVIDENCE_MIN_PASSAGES = 3
# Under this many characters, a page returned HTML with no content in it --
# almost always JavaScript rendering, which our crawler cannot do. A miss, not
# an answer, and it must not be cached as one.
MIN_USEFUL_PAGE_CHARS = 600

# Wikipedia's API policy asks for a descriptive agent with contact details.
# Anonymous scrapers are throttled first, and Wikipedia signals a throttle by
# returning HTML instead of JSON rather than by erroring.
HTTP_USER_AGENT = (
    "IdCapThat/1.0 (https://github.com/shrayarora8/id-cap-that; shrayarora8@gmail.com)"
)

LOG_LEVEL = os.getenv("LOG_LEVEL", "INFO").upper()
LIBRARY_LOG_LEVEL = os.getenv("LIBRARY_LOG_LEVEL", "WARNING").upper()


def require(name: str) -> str:
    value = os.getenv(name, "").strip()
    if not value:
        raise RuntimeError(f"{name} is missing from .env")
    return value
