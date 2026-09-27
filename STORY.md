# I'd Cap That

## Where it came from

I was in a conversation with someone who was confidently, relentlessly wrong.

Not lying — just *sure*. Three claims in a row, all stated with the kind of
certainty you don't argue with, and not one of them true. And I did what
everybody does: I nodded. Because the alternative is pulling out my phone,
googling three separate things, and coming back thirty seconds later to a
conversation that has already moved on. Nobody does that. The social cost of
being the person who fact-checks their friends is higher than the cost of
just letting it go.

So the false thing sits there, unchallenged, and everyone moves on.

That bothered me more than it should have.

## Why now

Voice AI got good. Not "good for a demo" good — *actually* good. Live
transcription is fast, accurate and cheap enough that you can run it
continuously in a browser tab. That's new. Five years ago this idea would have
been a research project.

And there's an obvious gap. Fact-checking tools exist — they're built for
journalists, they work on articles, and they take minutes. Meeting
transcription exists — Otter, Granola, all of them — they give you notes and
summaries and action items.

But none of them will tell you, while someone is still talking, that what they
just said isn't true.

**None of them have a cap index.**

That felt underserved in a way that was both genuinely useful and genuinely
funny, which is a rare combination.

## What it is

You open it, you hit listen, and you talk.

It transcribes the conversation live, works out which sentences are actually
*claims*, checks each one against pages it fetches from the live web, and
marks the exact words on screen:

**NO CAP** · **ABSOLUTE CAP** · **SOME CAP** · **COULD BE CAP** · **WORD SALAD**

About four seconds from the end of your sentence to a verdict with a real
source under it. There's a running tally at the top, so you can watch someone's
cap index climb in real time.

It runs in a browser and installs on a phone as an app.

## Who it's for

Honestly? It started as a gag and I've stopped apologising for that.

It's for couples settling an argument. It's for the group chat that has
migrated to a pub table. It's for the friend who says "Everest is nine
thousand metres" with total conviction and now has to look at a screen that
says otherwise.

And it's for the version of this that isn't a joke at all — a meeting, an
interview, a pitch, anywhere someone is asserting things with confidence and
nobody in the room has the time or the nerve to check.

The gag and the tool are the same product. That's the bit I like.

## How it works

Audio goes to Deepgram as raw PCM and comes back as text. The system waits for
a finished thought rather than reacting to every phrase, because people pause
mid-sentence constantly.

Small talk gets thrown away in plain Python before anything costs money — a
regex against stock phrases, a word count, and 163 filler words stripped out.
Most of a conversation is this, and establishing that costs nothing.

What survives goes to Claude, which pulls out the claim, resolves the pronouns
("*they* raised at ten billion" only means something if you know who "they" is),
and writes a search query.

Then it asks its own memory first. Every passage it has ever read goes into a
Moss semantic index, so a related claim is answered in about fifteen
milliseconds with no web request at all. On a miss, Firecrawl searches, and the
results go into Moss for next time.

A second Claude call weighs the evidence and returns a verdict plus the exact
sentences it relied on.

## The part I'd actually defend

And then code checks its homework.

Every quote the model produces is verified character-by-character against the
page it claims to come from. Numbers are compared by arithmetic, not by the
model's judgement. Years have to match exactly; measurements get three per
cent. If the passage isn't genuinely about the claim, the verdict is thrown
out.

**The model invents quotes about one time in four.** It gets caught every
time, and the code goes and finds the real sentence instead.

That's the whole difference between "an AI said so" and "here is the sentence
on the page that says so", and it's why I trust the output enough to put it in
front of people.

## What went wrong

Plenty.

Somebody said the fragment "fifty seconds." The system treated it as a claim,
found a restaurant in Lisbon *called* Fifty Seconds, found a real page saying a
lift there takes exactly fifty seconds, verified the quote — and returned a
confident **NO CAP**. Every single step worked correctly and the answer was
nonsense, because nothing had ever asked whether the evidence was about the
same subject.

Years were being compared as percentages, so 1995 and 1991 are 0.2% apart and
the system called a four-year error a rounding error.

On a Mac with an iPhone nearby, macOS quietly hands the browser the phone's
microphone, so the laptop goes deaf and nothing on screen explains why.

And twice I fixed something, tested it, and discovered the browser had been
serving cached JavaScript for hours. The bug was in delivery, not in the code
either of us was staring at.

Most of the work wasn't building the pipeline. It was making it **trustworthy**
— because a fact-checker that is confidently wrong is worse than no
fact-checker at all. One bad verdict and nobody believes the good ones.

There are 186 tests. Nearly every one of them is a bug that shipped once and
now can't come back.

## What I'd do next

Speaker separation, so it knows who said what and the cap index becomes a
leaderboard. A shareable receipt for the group chat. And a mode that runs
against your own documents rather than the open web.

But the core thing already works, and it's funnier than I expected it to be.
