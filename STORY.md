# I'd Cap That

## Inspiration

I was talking to someone who was confidently, relentlessly wrong.

Three claims in a row. All said with total certainty. None of them true.

And I nodded. Because the alternative is pulling out your phone, googling three
things, and coming back to a conversation that's already moved on. Nobody does
that. It's easier to let it go.

Then it clicked that voice AI got good enough to not let it go. Live
transcription is fast and cheap enough to just leave running in a browser tab —
that's new.

Fact-checkers exist, but they're built for journalists and they work on
articles. Meeting tools exist, but they hand you notes after the fact. Neither
one tells you something is false **while the person is still talking**.

Neither one has a cap index.

## What it does

Hit listen. Talk.

It transcribes live, works out which sentences are actual claims, checks them
against real web pages, and marks the exact words:

**NO CAP** · **ABSOLUTE CAP** · **SOME CAP** · **COULD BE CAP** · **WORD SALAD**

Four seconds from the end of your sentence to a verdict with a real source
under it. Running tally at the top, so you watch someone's cap index climb in
real time. Runs in a browser, installs on a phone as an app.

Things I've thrown at it:

- "Mount Everest is nine thousand metres" → **ABSOLUTE CAP**
- "Notion costs eight dollars a seat" → **ABSOLUTE CAP**, actually $20
- "Snowflake is the best database in the world" → **WORD SALAD**
- "Usain Bolt ran 9.58" → **NO CAP**
- "How's it going?" → ignored, costs nothing

The buzzword one is my favourite. It doesn't argue with it. It just refuses to
take it seriously.

And the reason it works socially is that the screen says it and you don't have
to. You're not the guy fact-checking his friends any more. You just point at a
phone.

## How we built it

- **Deepgram** for live speech, streamed as raw audio so it works on a phone
- **Claude** twice: once to find the claim and work out who "they" refers to,
  once to weigh the evidence and return a verdict
- **Firecrawl** to search and read real pages
- **Moss** as memory — every page it reads gets indexed, so a related claim
  comes back in 15ms with no search at all
- Small talk gets thrown out in plain Python before anything costs money

The bit I'd defend: **code checks the AI's homework.** Every quote is verified
character-by-character against the page it came from. Numbers are compared by
arithmetic, not vibes.

## Challenges we ran into

Someone said "fifty seconds." It treated that as a claim, found a restaurant in
Lisbon **called Fifty Seconds**, found a real page saying a lift there takes
exactly fifty seconds, verified the quote, and returned a confident **NO CAP**.
Every step worked. The answer was nonsense. Nothing had asked whether the
evidence was about the same thing as the claim.

Years were being compared as percentages, so 1995 and 1991 are 0.2% apart and a
four-year error read as a rounding error.

On a Mac with an iPhone nearby, macOS silently hands the browser the phone's
microphone. The laptop goes deaf and nothing on screen explains why.

And the search API allows ten requests a minute, so reading a script out loud
produces claims faster than it will answer them.

## Accomplishments that we're proud of

**The model makes up quotes about one time in four.** It gets caught every
single time, and the code goes and finds the real sentence instead.

That's the whole thing. It's the difference between "an AI said so" and "here's
the sentence on the page that says so", and it's why I'm willing to put the
output in front of people.

Also: it holds a conversation in its head. Say "we're moving onto Notion",
then two sentences later "they raised at a ten billion valuation", and it knows
who "they" is.

## What we learned

A fact-checker that's confidently wrong is worse than no fact-checker at all.
One bad verdict and nobody trusts the good ones.

Almost every hard problem was that shape — not "can it find the answer" but
"can it tell when it hasn't". Being precise about *when to shut up* mattered
more than being clever.

The other lesson was cheaper and more annoying: twice I fixed something, tested
it, and found the browser had been serving cached JavaScript for hours. The bug
was in delivery, not in the code I was staring at.

## What's next for I'd Cap That

Speaker separation, so it knows who said what and the cap index becomes a
leaderboard.

A shareable receipt for the group chat.

And a mode that checks against your own documents instead of the open web —
same engine, pointed at a contract or a pitch deck.
