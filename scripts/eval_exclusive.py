"""Can the judge refute a claim by elimination -- and ONLY when that is sound?

"Tom Holland is married to Zendaya" makes "Tom Holland and Taylor Swift are
dating" false, even though no passage mentions Taylor Swift. A human
fact-checker says so without hesitating. That is not guessing: some facts
can only have one value at a time, and a passage naming a different value
refutes the claim.

The danger is the same move applied where it does NOT hold. A company can
have several founders; naming two does not exclude a third. Someone can
speak several languages. Someone who is married now may have dated someone
else before. Every one of those, refuted by elimination, is a confident
ABSOLUTE CAP on a claim that may well be true.

So this set is half targets and half traps, with hand-written evidence so
it costs nothing but a judge call and cannot be skewed by what a search
happens to return. Run it before and after any change to the judge prompt.

    .venv/bin/python scripts/eval_exclusive.py
"""

import asyncio
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from server import llm  # noqa: E402
from server.judge import judge_claim  # noqa: E402
from server.retrieval import Evidence  # noqa: E402

# Every call is a real call: a cached answer from before a prompt change
# would make a regression look like a pass.
llm._cached = lambda *a, **k: None
llm._remember = lambda *a, **k: None


def ev(text: str, title: str, tier: int = 1) -> list[Evidence]:
    return [Evidence(evidence_id="E1", text=text, url=f"https://en.wikipedia.org/wiki/{title}",
                     title=title, tier=tier)]


HOLLAND = ev(
    "Holland describes himself as a private person. He has been in a relationship "
    "with actress Zendaya since 2021, and the couple married in August 2026.",
    "Tom_Holland",
)
DOGS = ev(
    "The Labrador Retriever topped the American Kennel Club's list of most popular "
    "breeds for 31 consecutive years, until the French Bulldog took the number one "
    "spot in 2022. The Golden Retriever ranked third.",
    "Dog_breed_popularity",
)

# (want, why, claim, evidence, shape)
CASES = [
    # --- targets: elimination is sound, the answer is ABSOLUTE CAP ----------
    ("CONTRADICTED", "one current spouse",
     "Tom Holland and Taylor Swift are dating.", HOLLAND, "other"),
    ("CONTRADICTED", "one current CEO",
     "Satya Nadella is the CEO of Google.",
     ev("Sundar Pichai has been the chief executive officer of Google since 2015.", "Google"),
     "other"),
    ("CONTRADICTED", "one number-one breed",
     "The Golden Retriever is the most popular dog breed in the US.", DOGS, "comparison"),
    ("CONTRADICTED", "one rank per position",
     "The Labrador is the third most popular dog breed in the US.", DOGS, "comparison"),
    ("CONTRADICTED", "one current club",
     "Cristiano Ronaldo currently plays for Real Madrid.",
     ev("Ronaldo plays as a forward for and captains the Saudi Pro League club Al-Nassr.",
        "Cristiano_Ronaldo"), "other"),

    # --- traps: elimination would be WRONG, must not say ABSOLUTE CAP -------
    ("NOT_CONTRADICTED", "past tense: he may have dated her before",
     "Tom Holland once dated Taylor Swift.", HOLLAND, "event"),
    ("NOT_CONTRADICTED", "companies have several founders",
     "Tesla was co-founded by JB Straubel.",
     ev("Tesla was founded in July 2003 by Martin Eberhard and Marc Tarpenning.", "Tesla,_Inc."),
     "event"),
    ("NOT_CONTRADICTED", "people speak several languages",
     "Lionel Messi speaks Italian.",
     ev("Messi's native language is Spanish, and he grew up in Rosario, Argentina.",
        "Lionel_Messi"), "other"),

    # --- controls: must keep working exactly as before ----------------------
    ("SUPPORTED", "direct statement",
     "Tom Holland is married to Zendaya.", HOLLAND, "event"),
    ("SUPPORTED", "rank stated outright",
     "The French Bulldog is the most popular dog breed in the US.", DOGS, "comparison"),
]


def passed(want: str, got: str) -> bool:
    if want == "NOT_CONTRADICTED":
        return got != "CONTRADICTED"
    return got == want


async def main(runs: int) -> int:
    failures = 0
    for want, why, claim, evidence, shape in CASES:
        got = []
        for _ in range(runs):
            j, checks = await judge_claim(claim, evidence, shape)
            got.append((j.verdict, [c["code"] for c in checks], j.correction))
        ok = all(passed(want, v) for v, _, _ in got)
        failures += not ok
        verdicts = " ".join(v for v, _, _ in got)
        print(f"{'PASS' if ok else 'FAIL'}  want={want:<16} got={verdicts:<30} {why}")
        if not ok:
            for v, codes, corr in got:
                print(f"        {v}  rails={codes}  correction={corr[:80]!r}")
    print(f"\n{len(CASES) - failures}/{len(CASES)} passed ({runs} run(s) each)")
    return failures


if __name__ == "__main__":
    runs = int(sys.argv[1]) if len(sys.argv) > 1 else 2
    sys.exit(1 if asyncio.run(main(runs)) else 0)
