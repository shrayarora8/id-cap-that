# I'd Cap That

## The idea

I was talking to someone who was confidently, relentlessly wrong.

Three claims in a row. All said with total certainty. None of them true.

And I nodded. Because the alternative is pulling out your phone, googling
three things, and coming back to a conversation that's already moved on.
Nobody does that. It's easier to let it go.

So I built the thing that doesn't let it go.

## Why now

Voice AI got good. Actually good — live transcription is fast and cheap enough
to just leave running in a browser tab. That's new.

Fact-checkers exist, but they're for journalists and they work on articles.
Meeting tools exist, but they give you notes after the fact.

Neither of them tells you something is false **while the person is still
talking**. Neither of them has a cap index.

## What it does

Hit listen. Talk.

It transcribes live, works out which sentences are actual claims, checks them
against real web pages, and marks the exact words:

**NO CAP** · **ABSOLUTE CAP** · **SOME CAP** · **COULD BE CAP** · **WORD SALAD**

Four seconds from the end of your sentence to a verdict with a source under
it. Running tally at the top, so you watch someone's cap index climb in real
time.

Runs in a browser, installs on a phone as an app.

## Why it's funny

Because the screen says it and you don't have to.

You're not the guy fact-checking his friends any more. You just point at a
phone. **"WORD SALAD"** landing on someone mid-sentence about synergy does more
damage than any argument I could make.

And it's funny because it's *specific*. It doesn't say "that seems doubtful",
it says **ABSOLUTE CAP** and then shows you the actual page.

## Things I tried on it

- "Mount Everest is nine thousand metres" → **ABSOLUTE CAP**
- "Snowflake is the best database in the world" → **WORD SALAD**
- "Notion costs eight dollars a seat" → **ABSOLUTE CAP**, actually $20
- "Usain Bolt ran 9.58" → **NO CAP**
- "How's it going?" → ignored, costs nothing

The buzzword one is my favourite. It doesn't argue with it. It just refuses to
take it seriously.

## What's under it

- **Deepgram** for live speech
- **Claude** twice: once to find the claim and work out what "they" refers to,
  once to weigh the evidence
- **Firecrawl** to search and read real pages
- **Moss** as memory — every page it reads is indexed, so a related claim comes
  back in 15ms with no search at all
- Small talk is thrown out in plain Python before anything costs money

## The part I care about

Code checks the AI's homework.

Every quote gets verified character-by-character against the page it came
from. Numbers are compared by arithmetic, not vibes.

**The model makes up quotes about one time in four.** It gets caught every
time, and the code goes and finds the real sentence instead.

That's the difference between "an AI said so" and "here's the sentence that
says so".

## Favourite bug

Someone said "fifty seconds." It treated that as a claim, found a restaurant in
Lisbon **called Fifty Seconds**, found a real page saying a lift there takes
exactly fifty seconds, verified the quote, and returned a confident **NO CAP**.

Every step worked. The answer was nonsense. Nothing had asked whether the
evidence was about the same thing as the claim.

## Next

Speaker separation, so the cap index becomes a leaderboard.
