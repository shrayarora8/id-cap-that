# I'd cap that — Design System

> **Status: being rewritten, decision by decision, with the user.**
>
> Everything below the "Superseded strawman" line was machine-written and was
> never agreed. It is kept only so that the reasoning behind individual calls
> can be raided where it is still useful. **Do not build from it.** The rules
> that hold are the decisions recorded here, and nothing else.
>
> `web/css/tokens.css` still encodes the strawman and is also being rewritten.

## The brief

1. **Stripe and Apple.** Minimal, clean, classy. The governing constraint.
2. **The transcript behaves like Spotify's lyric view** — line-level states on a
   flat colour field, the live line lit, older lines sunk back into the field.
   Line-level, not word-level, so the frozen contract already carries enough:
   one `transcript.final` phrase is one line.
3. **Red for ABSOLUTE CAP, green for NO CAP.** The other four are open.
4. **Hover or click a claim** to reach its card and go deeper.
5. **Sound.** Funny beeps on ABSOLUTE CAP and NO CAP.
6. **Cache where sensible.** Efficiency is part of the experience.

Audience, in priority order: the demo video (compressed, watched small), then a
stranger poking at the live app alone with nobody narrating, then a projected
live demo only if we place top 3. Compression eats 1px hairlines, 16% tints and
dotted rules, so every signal has to survive re-encoding.

## Decisions

### 1. Surface — the reactive colour field · agreed

The app is a **flat colour field with big tight type on it, and no chrome**.
Two line states only: the live line is lit, older lines sink back toward the
field colour. The dim state is the field pushed toward the ink, never grey.

**When a verdict lands, the whole field takes its colour** — deep red for
ABSOLUTE CAP, deep green for NO CAP — and settles back over ~1.5s.

Why this and not a sticker: nothing can out-shout the entire screen changing,
it survives video compression for free where a small badge does not, it reads
from across a room, and it needs no rubber stamp — which is what kept the
strawman's centrepiece incompatible with "Stripe and Apple".

Only the two loud verdicts move the field. The other four resolve quietly in
place, so the moment stays rare enough to mean something.

Rejected: a near-white paper world (Stripe-clean, but a white screen is hard to
make feel like an event on video); and a static colour field with no reaction
(correct, but it leaves the verdict doing all the work at small sizes).

Open inside this decision: the resting field hue (ink / moss / clay / sage) and
the exact flash colours. Board 01 carries all four.

### 2–10. Not yet taken

Video frame · lyric emphasis · the verdict mark · type · the other four
verdicts · claim-to-card · sound · cold start · chrome and motion budget.

## Constraints that carry over from the strawman

These survive because they are engineering, not taste:

- **Never rebuild the transcript.** Append, move, split, mutate in place.
  `replaceChildren` destroys text selection and scroll position.
- **Autoscroll only while pinned**, and `overflow-anchor` so a verdict landing
  on a line above the fold never moves the reader's place.
- **Verdicts arrive late and out of order.** A claim from eight seconds ago can
  resolve after two newer ones, so **a dim line must be able to light back up**
  when its verdict finally lands. Spans stay valid however far the transcript
  has scrolled.
- **Name the work, never spin.** `sifting 15 of 98 passages` is the latency
  pitch in words. A spinner throws it away.
- **Failure must be loud.** A dead transcription connection must never look the
  same as nobody talking — an hour was lost to exactly that.
- **Every verdict identifiable with colour removed.** Doubly so now that the two
  loudest are red and green.
- `100dvh`, safe-area insets, and no text input below 16px (iOS zooms and never
  unzooms).

---

# Superseded strawman

Everything below this line is the unagreed machine-written draft. Kept for
reference only.


**Version 1.0 · phone-first · dark-primary · vanilla CSS, no build step**

This document is the specification, not a mood board. Every value in it is a token
that already exists in `web/css/tokens.css`. If you are implementing and you find
yourself typing a raw hex value, a raw `px`, or a raw `cubic-bezier`, stop — the
value you want is already named.

---

## 0. How to use this

### File layout

```
web/
  index.html
  css/
    tokens.css      <- every colour, size, duration. Written. Do not edit casually.
    base.css        <- reset, body, focus, selection, scrollbars
    transcript.css  <- transcript, claim highlight, sticker
    evidence.css    <- sheet/rail, evidence card, source, confidence
    chrome.css      <- topbar, BS index, dock, listen button, status line, input
  app.js
```

```html
<link rel="stylesheet" href="/css/tokens.css">
<link rel="stylesheet" href="/css/base.css">
<link rel="stylesheet" href="/css/transcript.css">
<link rel="stylesheet" href="/css/evidence.css">
<link rel="stylesheet" href="/css/chrome.css">
```

Use `@layer` in this order so specificity never becomes a fight:

```css
@layer tokens, reset, layout, components, state, utilities;
```

`tokens.css` already declares `@layer tokens`. Every other file opens with
`@layer components { ... }` (or the appropriate layer). CSS nesting is allowed and
encouraged inside component blocks; it is supported in every browser that ships
in 2026 and needs no build step.

### Required `<head>`

```html
<meta name="viewport"
      content="width=device-width, initial-scale=1, viewport-fit=cover, interactive-widget=resizes-content">
<meta name="theme-color" content="#0B0D12">
<meta name="apple-mobile-web-app-capable" content="yes">
<meta name="apple-mobile-web-app-status-bar-style" content="black-translucent">
```

`viewport-fit=cover` is what makes `env(safe-area-inset-*)` return real numbers.
`interactive-widget=resizes-content` is what makes the on-screen keyboard shrink
the layout viewport instead of sliding it. Both are mandatory.

### Theme + mode attributes

| Attribute on `<html>` | Effect |
|---|---|
| *(none)* | dark theme, normal sizes — **the design target** |
| `data-theme="light"` | optional light theme |
| `data-present` | presentation mode (§8) |
| `data-reduced` | mirrors `prefers-reduced-motion` for JS-driven animation |

---

## 1. Design philosophy

Eight principles. Each states what it rules out, because a principle that rules
nothing out is decoration.

**1. The transcript is the product; everything else is furniture.**
Spoken words are the largest, brightest, highest-contrast thing on screen at all
times, and the only element allowed to use `--fs-transcript`.
*Rules out:* a dashboard where the transcript is one panel among several. There is
no three-column layout, ever.

**2. The highlighter is the metaphor, and it is literal.**
`--accent` is high-vis highlighter yellow and it means exactly one thing: "the
machine is working on these words right now." A claim highlight is drawn as a
stroke that wipes left-to-right across the words, like a marker.
*Rules out:* the accent as a link colour, a border colour, a brand flourish, or a
button fill anywhere other than the primary action. It also rules out a
fade-in-from-nothing highlight — highlights are *drawn*, not revealed.

**3. The verdict is a physical object landing on the words.**
A sticker has a tilt, an edge shadow, an overshoot on arrival, and a fill so solid
it reads as printed. It is placed *on the sentence*, not in a sidebar.
*Rules out:* the flat grey pill of v0. It rules out the verdict appearing only in a
detail panel. It rules out `opacity: 0 -> 1` as the whole arrival animation.

**4. Confidence, trust tier and verdict are three separate axes and must never
share a visual language.**
Verdicts own hue. Trust tiers own neutral fills plus border-style. Confidence owns
a filled-bar count and nothing else.
*Rules out:* a green "high confidence" badge next to a red CONTRADICTED verdict —
the single most confusing thing this UI could do.

**5. Latency is the feature, so progress must be visibly moving at all times.**
`claim.status` text changes every few hundred ms; the status line animates on every
change; the checking sweep loops; the elapsed-ms counter ticks live.
*Rules out:* an indeterminate spinner. A spinner says "waiting"; this product's
whole pitch is "look how fast, and look at what it's doing."

**6. The jokes live in the copy, never in the chrome.**
"ABSOLUTE CAP" is funny. The typography rendering it is a serious, tightly-tracked
display face with correct optical spacing.
*Rules out:* rounded bubbly type, emoji as UI, comic accents, gradients, neon
glows, stickers with drop shadows so heavy they look like a party invite.

**7. Colour is a bonus channel, never the only one.**
Every verdict is identifiable with the screen in greyscale and washed out by a
projector: distinct sticker *words*, distinct underline *style*, distinct sticker
*fill treatment*.
*Rules out:* verdict chips distinguished by hue alone. It also rules out reducing
the six verdicts to four colours (v0 collapsed PARTIALLY_SUPPORTED and DISPUTED
into one class — they are different answers and must look different).

**8. Nothing the user is reading may move under them.**
New transcript never yanks the scroll position. A verdict landing on an old claim
never reflows the line. Interim text never changes metrics when it becomes final.
*Rules out:* rebuilding the transcript DOM on every message (v0 did
`replaceChildren` + `scrollTop = scrollHeight` on every single event, which
destroys text selection and fights the reader). Mutate in place.

---

## 2. Colour

### 2.1 Rationale

The base `#0B0D12` is a cold near-black ink-blue, not neutral grey. Against it,
saturated pigment reads as *ink on paper*, which is the right association for a
receipts-and-evidence product; against neutral grey it reads as *dashboard chrome*,
which is what we are escaping.

The v0 accent (`#7f77dd`) is deleted. It had no argument behind it. The new accent
is highlighter yellow `#E4FF4F` because the core interaction of this product is
*a highlighter passing over transcribed speech*. It is also the highest-luminance
value in the system (17.32:1 on base), which means the one thing that must be
visible across a conference room — "it's working on this sentence right now" — is
literally the brightest thing on the screen.

### 2.2 Surfaces and text

| Token | Value | Use | Contrast |
|---|---|---|---|
| `--ink` | `#07090D` | text on any bright fill | — |
| `--bg-base` | `#0B0D12` | page, transcript | — |
| `--bg-raised` | `#141821` | cards, sheet, bars | 1.09:1 vs base |
| `--bg-inset` | `#0F131A` | input, quote wells | 1.04:1 vs base |
| `--hairline` | `#242A36` | dividers on base | 1.35:1 (non-text, decorative) |
| `--hairline-strong` | `#2C3342` | dividers on raised | 1.40:1 |
| `--text-primary` | `#F2F4F8` | transcript, headlines | **17.65** base · **16.13** raised · **16.90** inset |
| `--text-secondary` | `#A8B0C0` | summaries, labels | **8.92** base · **8.15** raised |
| `--text-tertiary` | `#828B9D` | meta, timestamps | **5.67** base · **5.18** raised |

Surface steps are intentionally almost invisible. Depth in this product comes from
hairlines and from verdict pigment — not from a staircase of greys. If you feel the
need for a fifth grey, you are building the wrong layout.

`--text-tertiary` is the dimmest text allowed anywhere. It is at the AA floor
(4.5:1) with margin on both surfaces. Do not add a `--text-quaternary`.

### 2.3 Accent

| Token | Value | Use | Contrast |
|---|---|---|---|
| `--accent` | `#E4FF4F` | checking state, listen button fill, focus ring | **17.32** on base |
| `--accent-ink` | `#07090D` | text on accent | **17.76** on accent |
| `--accent-tint` | `#2E341C` | the "checking" highlight wash (accent @16% over base, pre-composited) | text-primary on it **11.74** |
| `--accent-dim` | `#A8BD33` | idle mic ring, idle button border | **9.25** on base |
| `--accent-glow` | `rgba(228,255,79,.28)` | one-shot ring flash only | — |

### 2.4 The six verdicts

Each verdict has six colour tokens plus one non-colour token. `-tint` values are
**pre-composited opaque colours**, not `rgba()`, so overlapping claim spans can
never double-darken.

#### SUPPORTED — "NO CAP"

*Should feel like:* a receipt. Quiet vindication, not celebration.
*Hue:* cyan-leaning green `#2FD79A` — far from the amber of SOME CAP under both
deuteranopia and protanopia, and it never reads as "highlighter yellow".

| Token | Value | Contrast |
|---|---|---|
| `--v-supported-core` | `#2FD79A` | **10.46** on base · **9.56** on raised |
| `--v-supported-text` | `#5CE3B2` | **12.11** on base · **11.07** on raised · **8.74** on `-prov` |
| `--v-supported-tint` | `#112D28` | text-primary on it **13.34** |
| `--v-supported-tint-r` | `#183734` | text-primary on it **11.67** |
| `--v-supported-prov` | `#11312A` | provisional sticker fill |
| `--v-supported-ink` | `#07090D` | **10.73** on core (sticker text) |

**Non-colour signal:** a single **solid** 3px rule under the words. Sticker is a
**solid filled** stamp. Leading glyph `✓`.

#### CONTRADICTED — "ABSOLUTE CAP"

*Should feel like:* a klaxon and a rubber stamp at the same time. This is the
moment the product exists for. It must be the loudest pixel in the room.
*Hue:* hot signal red `#FF4A4A`, not blood red — blood red goes muddy on a cheap
projector; signal red stays alarming.

| Token | Value | Contrast |
|---|---|---|
| `--v-contradicted-core` | `#FF4A4A` | **5.86** on base · **5.35** on raised |
| `--v-contradicted-text` | `#FF8E8E` | **8.80** on base · **8.04** on raised · **7.26** on `-prov` |
| `--v-contradicted-tint` | `#32171B` | text-primary on it **14.97** |
| `--v-contradicted-tint-r` | `#3A2028` | text-primary on it **13.46** |
| `--v-contradicted-prov` | `#37181C` | |
| `--v-contradicted-ink` | `#07090D` | **6.01** on core |

**Non-colour signal:** a **double** rule under the words **plus a line-through on
the claim text itself**. Struck-through words are unmistakable in greyscale, at
3 metres, and to every form of colour blindness. This is the strongest non-colour
signal in the system and it belongs to the strongest verdict. Sticker is a **solid
filled** stamp with a 2px `--ink` outer keyline. Leading glyph `✕`.

#### PARTIALLY_SUPPORTED — "SOME CAP"

*Should feel like:* a caution strip. "True, but."
*Hue:* amber `#FF9E2C`, pushed orange specifically so it never collides with the
highlighter yellow of the checking state sitting a few words away.

| Token | Value | Contrast |
|---|---|---|
| `--v-partial-core` | `#FF9E2C` | **9.42** on base · **8.61** on raised |
| `--v-partial-text` | `#FFBC68` | **11.70** on base · **10.69** on raised · **8.63** on `-prov` |
| `--v-partial-tint` | `#322416` | text-primary on it **13.63** |
| `--v-partial-tint-r` | `#3A2D23` | text-primary on it **12.07** |
| `--v-partial-prov` | `#372717` | |
| `--v-partial-ink` | `#07090D` | **9.66** on core |

**Non-colour signal:** a **dashed** rule — the claim has gaps in it. Sticker is
**half-filled**: a hard-edged 50/50 `linear-gradient` split, solid core on the left
half, `-tint` on the right. Leading glyph `≈`.

#### DISPUTED — "SOURCES ARE FIGHTING"

*Should feel like:* a referee, not a judgement. This is the only verdict that is
about the *sources* rather than about the truth of the claim.
*Hue:* blue `#45B6FF` — the one hue nobody reads as good-or-bad, and the hue
maximally separated from red/green/amber for every common colour vision deficiency.

| Token | Value | Contrast |
|---|---|---|
| `--v-disputed-core` | `#45B6FF` | **8.69** on base · **7.94** on raised |
| `--v-disputed-text` | `#8AD0FF` | **11.61** on base · **10.61** on raised · **8.68** on `-prov` |
| `--v-disputed-tint` | `#142838` | text-primary on it **13.72** |
| `--v-disputed-tint-r` | `#1C3145` | text-primary on it **12.11** |
| `--v-disputed-prov` | `#152B3D` | |
| `--v-disputed-ink` | `#07090D` | **8.91** on core |

**Non-colour signal:** a **wavy** underline (`text-decoration: underline wavy`) —
two sides, squabbling. Sticker is **solid filled** and is the only sticker that
wraps to two lines on a phone (the string is 20 characters; see §6.2). Leading
glyph `⇄`.

#### INSUFFICIENT_EVIDENCE — "COULD BE CAP"

*Should feel like:* an honest shrug. An absence of evidence must *look* like an
absence — no pigment, no opinion.
*Hue:* cool desaturated slate `#99A3B8`.

| Token | Value | Contrast |
|---|---|---|
| `--v-insufficient-core` | `#99A3B8` | **7.67** on base · **7.01** on raised |
| `--v-insufficient-text` | `#BCC4D2` | **11.07** on base · **10.12** on raised · **8.40** on `-prov` |
| `--v-insufficient-tint` | `#22252D` | text-primary on it **13.92** |
| `--v-insufficient-tint-r` | `#292E39` | text-primary on it **12.35** |
| `--v-insufficient-prov` | `#252830` | |
| `--v-insufficient-ink` | `#07090D` | **7.86** on core |

**Non-colour signal:** a **dotted** rule — we couldn't join the dots. Sticker is
**outline-only**: transparent fill, 1.5px solid border in `-core`, text in `-text`.
Leading glyph `?`.

#### NOT_FACT_CHECKABLE — "WORD SALAD"

*Should feel like:* the joke that gets out of the way. This is the dimmest family
in the system by design.
*Hue:* near-neutral `#8A8A99`.

| Token | Value | Contrast |
|---|---|---|
| `--v-salad-core` | `#8A8A99` | **5.72** on base · **5.22** on raised |
| `--v-salad-text` | `#A5A8B6` | **8.21** on base · **7.51** on raised · **6.56** on `-prov` |
| `--v-salad-tint` | `#1F2128` | text-primary on it **14.60** |
| `--v-salad-tint-r` | `#272A34` | text-primary on it **13.00** |
| `--v-salad-prov` | `#22242A` | |
| `--v-salad-ink` | `#07090D` | **5.86** on core |

**Non-colour signal:** **no rule at all**, plus the sticker at `opacity: .78` and a
dotted 1px border. It is the only verdict with no underline; its absence is the
signal. Leading glyph `~`.

### 2.5 Non-colour signal summary

Print this table and check the UI against it in greyscale before the demo.

| Verdict | Sticker words | Underline style | Sticker fill | Glyph | Extra |
|---|---|---|---|---|---|
| SUPPORTED | NO CAP | solid 3px | solid | `✓` | — |
| CONTRADICTED | ABSOLUTE CAP | double 4px | solid + keyline | `✕` | **line-through on the words** |
| PARTIALLY_SUPPORTED | SOME CAP | dashed 3px | 50/50 split | `≈` | — |
| DISPUTED | SOURCES ARE FIGHTING | wavy | solid | `⇄` | two-line sticker on phone |
| INSUFFICIENT_EVIDENCE | COULD BE CAP | dotted 3px | outline only | `?` | — |
| NOT_FACT_CHECKABLE | WORD SALAD | none | ghost, dotted border, .78 opacity | `~` | — |

Four distinct border styles, four distinct fill treatments, six distinct strings,
six distinct glyphs, and one strike-through. A user who sees no colour at all can
still read every verdict.

### 2.6 Source trust tiers

Tiers use **neutral** colour plus **border style**, so a tier badge can never be
mistaken for a verdict. Only tier 4 borrows alarm colour, because only tier 4 is a
warning.

| Tier | Label | fg / bg / border | Border style | Glyph | Contrast |
|---|---|---|---|---|---|
| 1 | `PRIMARY` | `#07090D` on `#E6EBF5` | solid, filled | `◆` | **16.67** |
| 2 | `REPUTABLE` | `#B4BCCC` on transparent | solid | `◇` | **10.19** base · **9.31** raised |
| 3 | `UNKNOWN` | `#828B9D` on transparent | dashed | `◌` | **5.67** base · **5.18** raised |
| 4 | `LOW TRUST` | `#FF8E8E` on `#32171B` | dotted | `⚠` | **8.80** base · **8.04** raised |

### 2.7 Confidence

Confidence is **not** a verdict and must never be coloured like one. It renders as
three bars; the **filled count** is the entire signal.

| Level | Bars | Label | Colour |
|---|---|---|---|
| high | `▮▮▮` | `HIGH CONFIDENCE` | `--conf-fill` `#BCC4D2` (**11.07** on base) |
| medium | `▮▮▯` | `MEDIUM CONFIDENCE` | same fill, `--conf-empty` `#2C3342` for the empty bar |
| low | `▮▯▯` | `LOW CONFIDENCE` | same |

`--conf-label` `#A8B0C0` (**8.92** on base) for the word. `--conf-empty` is
structural non-text at 1.40:1 against raised, which is acceptable because the
*filled* bars carry the meaning, not the empty ones.

### 2.8 Light theme

Optional. All tokens are redefined under `:root[data-theme="light"]` in
`tokens.css`. The rules that make it work:

- Verdict `-core` values are darkened until **white** clears AA on them
  (SUPPORTED `#0A7A55` 5.35:1, CONTRADICTED `#C81E1E` 5.74:1, PARTIAL `#8F5100`
  6.28:1, DISPUTED `#0B6BAF` 5.62:1, INSUFFICIENT `#525A6B` 6.92:1, SALAD
  `#646472` 5.82:1). `--v-*-ink` becomes `#FFFFFF`.
- On a light tint, transcript text is **always** `--text-primary` (≥14.5:1 on every
  tint). Verdict-coloured text on a light tint is never used. The `-core` colour on
  its own tint measures 4.2–5.4:1, which satisfies the 3:1 non-text requirement for
  the underline but not body text — hence the rule.
- `--accent` stays `#E4FF4F`. It is a highlighter; it is supposed to glare. It is
  used only as a *fill* in light mode (1.12:1 against white — never as text).
  `--accent-dim` `#5A6B00` (5.49:1) is the light-theme focus ring and link colour.

---

## 3. Typography

### 3.1 The stack

```css
--font-sans: -apple-system, BlinkMacSystemFont, "SF Pro Text", "Segoe UI Variable Text",
             "Segoe UI", Roboto, "Helvetica Neue", Arial, system-ui, sans-serif;
--font-display: "Archivo Black", -apple-system, BlinkMacSystemFont, "SF Pro Display",
             "Segoe UI Variable Display", "Segoe UI", Roboto, "Helvetica Neue", Arial,
             system-ui, sans-serif;
--font-mono: ui-monospace, "SF Mono", SFMono-Regular, Menlo, Consolas,
             "Liberation Mono", monospace;
```

This resolves to SF Pro on the demo device (an iPhone), Segoe UI Variable on
Windows 11, Roboto on Android. All three are variable fonts with genuine optical
sizing and a 100–900 weight range, which is why this design needs no download to
look intentional. `system-ui` is placed *after* the named faces deliberately: on
some Linux configurations `system-ui` resolves to something awful, and we only want
it as a late fallback.

**The one optional webfont:** Archivo Black, used *only* for stickers, BS-index
numerals, and the wordmark — the three places where the design wants a heavier,
wider, more printed voice than any system face provides.

```html
<link rel="stylesheet"
      href="https://fonts.googleapis.com/css2?family=Archivo+Black&display=swap">
```

If it does not load, `--font-display` falls through to the system stack at weight
900 with identical size and letter-spacing. **Nothing reflows and nothing breaks.**
`display=swap` means a failed load costs 0ms. Ship the venue demo without this line
and add it only if the wifi is proven; the design is complete without it.

Global settings in `base.css`:

```css
body {
  font: var(--type-transcript);
  font-synthesis-weight: none;          /* no fake bold; we have real weights */
  -webkit-font-smoothing: antialiased;
  text-rendering: optimizeLegibility;
  font-variant-numeric: tabular-nums;   /* counters and ms never jitter */
}
```

`tabular-nums` globally is not optional: the BS index counters and the live
elapsed-ms readout both change every frame, and proportional digits make them
visibly wobble.

### 3.2 The scale

Phone values first. Laptop values apply at `min-width: 900px`; presentation values
apply under `[data-present]`. All three sets live in `tokens.css`.

| Role | Token | Phone | Laptop | Present | Weight | LH | Tracking | Used for |
|---|---|---|---|---|---|---|---|---|
| Wordmark | `--type-wordmark` | 18 | 20 | 20 | 900 | 1.05 | `-0.02em` | "I'D CAP THAT" in the top bar |
| **Transcript** | `--type-transcript` | **22** | **26** | **38** | 400 | 1.45 | `-0.011em` | settled, pending and interim speech — all three at the same size |
| Sticker | `--type-sticker` | 12 | 13 | 20 | 900 | 1.05 | `0.04em` | the six verdict strings, uppercase |
| Counter number | `--type-counter-num` | 26 | 32 | 48 | 900 | 1.05 | `-0.02em` | BS index digits |
| Counter label | `--type-counter-lbl` | 10 | 11 | 13 | 700 | 1.25 | `0.06em` | `NO CAP`, `SOME CAP` … uppercase |
| Claim text | `--type-claim` | 16 | 17 | 22 | 600 | 1.25 | 0 | the normalized claim at the top of an evidence card |
| Correction | `--type-correction` | 16 | 17 | 22 | 600 | 1.45 | 0 | "actually: $20 per seat per month" |
| Summary | `--type-summary` | 15 | 16 | 20 | 400 | 1.55 | 0 | the one-sentence verdict summary |
| Quote | `--type-quote` | 14 | 15 | 18 | 400 | 1.55 | 0 | verbatim source quotes |
| Source | `--type-source` | 13 | 13 | 16 | 500 | 1.25 | 0 | mono — hostnames and evidence ids |
| Tier badge | `--type-tier` | 10 | 10 | 12 | 700 | 1.05 | `0.08em` | `PRIMARY` / `LOW TRUST` |
| Confidence | `--type-confidence` | 11 | 11 | 13 | 700 | 1.05 | `0.06em` | `HIGH CONFIDENCE` |
| Status line | `--type-status` | 13 | 14 | 18 | 500 | 1.25 | 0 | mono — "sifting 15 of 98 passages" |
| Button | `--type-button` | 16 | 16 | 16 | 700 | 1.25 | 0 | listen button |
| Text input | `--type-input` | 17 | 17 | 17 | 400 | 1.25 | 0 | the typed-claim fallback |
| Meta | `--type-meta` | 12 | 12 | 14 | 400 | 1.25 | 0 | mono — elapsed ms, claim kind, hedge |

Each `--type-*` is a `font:` shorthand. Letter-spacing cannot ride in the `font`
shorthand, so pair it:

```css
.sticker { font: var(--type-sticker); letter-spacing: var(--ls-sticker); }
```

**Why 22px for the transcript on a phone.** iOS body text is 17px. 22px is
`17 × 1.3` — comfortably above the OS default, so it reads as *the thing you came
for* rather than as body copy, while still fitting roughly 38 characters per line at
390px with a 16px gutter, which is inside the 35–45 character comfortable range.
At arm's length (~40cm) 22px subtends about 0.49° — above the 0.3° threshold for
effortless reading, with margin for a user glancing down from a conversation
rather than staring at the screen.

**Why 38px in presentation mode.** On a 2m-wide projected image from 6m back, a
38px glyph in a 1280px-wide viewport projects to roughly 59mm of cap height, which
subtends ~0.57° at 6m. That is above the 0.4° minimum for reliable reading of
unfamiliar text by an audience that is not concentrating. The three intermediate
ramps (22 → 26 → 38) exist so that nothing in the layout has to be re-authored; only
token values change.

**Interim text must not change metrics when it becomes final.** Interim, pending and
settled transcript are all `--fs-transcript` at `--fw-regular`. They differ only by
colour and by a trailing caret. Any size or weight difference causes the entire
paragraph to reflow at the exact moment the user is reading it, which violates
principle 8.

---

## 4. Layout

### 4.1 Phone — 390 × 844, the primary layout

```
┌──────────────────────────────────────┐  ← safe-area-inset-top
│ I'D CAP THAT        3  1  0  2  ● │  │  top bar, 52px, sticky, --bg-raised
├──────────────────────────────────────┤  1px --hairline
│                                      │
│  the transcript.                     │
│                                      │
│  it fills everything. words that     │
│  are ─────────── being checked       │
│  glow. words that turned out to      │
│  ══be wrong══ ⟨ABSOLUTE CAP⟩ get     │  ← the hero
│  struck through and stamped.         │
│                                      │
│  ▏ draft words appear here ▎         │  ← interim, --text-tertiary + caret
│                                      │
│                       ┌────────────┐ │
│                       │ ↓ 3 new    │ │  ← jump-to-live pill, only when unpinned
│                       └────────────┘ │
├──────────────────────────────────────┤
│ ▲ ABSOLUTE CAP · notion is $8/seat   │  ← sheet peek rail, 96px (incl. handle)
├──────────────────────────────────────┤
│ ◜ sifting 15 of 98 passages          │  ← status line, 28px
│      ┌────────────────────────────┐  │
│      │      ● LISTENING           │  │  ← dock, 84px
│      └────────────────────────────┘  │
└──────────────────────────────────────┘  ← safe-area-inset-bottom
```

**Structure.**

```css
body {
  min-height: 100dvh;          /* dvh, never vh — vh is wrong on iOS Safari */
  display: grid;
  grid-template-rows: auto 1fr auto;
  grid-template-areas: "topbar" "transcript" "dock";
  background: var(--bg-base);
  overscroll-behavior-y: none; /* kills rubber-band on the body */
}
```

| Region | Spec |
|---|---|
| Top bar | `position: sticky; top: 0; z-index: var(--z-topbar)`. Height `--topbar-h` (52px) **plus** `padding-top: var(--safe-top)`. `background: var(--bg-raised)`, `border-bottom: 1px solid var(--hairline)`. Wordmark left; BS index as a compact 6-cell tally right; a live dot at the far right. |
| Transcript | The only scroll container. `overflow-y: auto; overscroll-behavior: contain; -webkit-overflow-scrolling: touch`. Padding: `var(--sp-7) calc(var(--gutter) + var(--safe-left)) calc(var(--sheet-peek-h) + var(--sp-9)) calc(var(--gutter) + var(--safe-right))`. The bottom padding is what keeps the newest line clear of the sheet peek. |
| Sheet | `position: fixed; bottom: 0; left: 0; right: 0; z-index: var(--z-sheet)`. See §6.3. |
| Dock | `position: fixed; bottom: 0` inside the sheet's collapsed frame; height `--dock-h` plus `padding-bottom: var(--safe-bottom)`. `background: var(--bg-raised)`, `border-top: 1px solid var(--hairline)`. |

**Gutters.** `--gutter` is 16px on phone. Always add the safe-area inset so the
transcript does not slide under the rounded corner in landscape:
`padding-inline: calc(var(--gutter) + var(--safe-left)) calc(var(--gutter) + var(--safe-right))`.

**Every tap target is at least `--tap-min` (44px).** The listen button is 56px. The
sheet handle's hit area is 44px tall even though the visible handle is 4px. A claim
highlight is inline text and cannot be 44px tall — so the tap target is extended
with `padding-block: var(--sp-2)` and a transparent `::after` that reaches
±10px vertically; see §6.1.

### 4.2 Laptop — 900px and up

There is **one** structural breakpoint: `--bp-lap: 900px`.

```
┌───────────────────────────────────────────────────────────────────────┐
│ I'D CAP THAT                          BS INDEX  3 · 1 · 0 · 2 · 0 · 1 │  60px
├──────────────────────────────────────────────┬────────────────────────┤
│                                              │  EVIDENCE              │
│   the transcript, centred, max 720px         │  ┌──────────────────┐  │
│   of measure, 26px type                      │  │ ABSOLUTE CAP     │  │
│                                              │  │ notion is $8/... │  │
│   ══wrong words══ ⟨ABSOLUTE CAP⟩             │  │ actually: $20... │  │
│                                              │  │ "…quote…"        │  │
│                                              │  │ ◆ notion.com     │  │
│                                              │  │ ▮▮▮ HIGH   1.9s  │  │
│                                              │  └──────────────────┘  │
│                                              │  ┌──────────────────┐  │
│                                              │  │ (previous claim) │  │
├──────────────────────────────────────────────┤  └──────────────────┘  │
│ ◜ weighing the evidence    [● LISTENING]     │                        │  72px
└──────────────────────────────────────────────┴────────────────────────┘
                                                 380px, sticky, scrolls
```

```css
@media (min-width: 900px) {
  body {
    grid-template-columns: 1fr var(--rail-w);
    grid-template-rows: auto 1fr auto;
    grid-template-areas:
      "topbar topbar"
      "transcript rail"
      "dock rail";
  }
  .transcript-pane > .transcript { max-width: var(--measure); margin-inline: auto; }
  .rail {
    grid-area: rail;
    border-left: 1px solid var(--hairline);
    background: var(--bg-raised);
    overflow-y: auto;
    overscroll-behavior: contain;
  }
  .sheet { display: contents; }  /* the sheet's children become rail children */
}
```

Above 1440px the page does **not** keep widening: the whole grid is capped at
`1440px` and centred (`margin-inline: auto`). Wider than that, the transcript
measure stops being readable and the layout starts to look like a dashboard.

Differences from v0 that matter: the rail is `380px` and **it only exists above
900px**. It is not a 320px panel that stacks underneath on a phone. On a phone the
same content is a bottom sheet with drag-to-expand, because on a phone you want the
transcript filling the screen and evidence on demand — a fundamentally different
interaction, not a narrower column.

### 4.3 Scroll behaviour — read this twice

This is the easiest thing in the product to get wrong.

**Rule: autoscroll only while pinned.**

```js
const PIN_SLOP = 48;                     // px from the bottom that still counts as "at the bottom"
let pinned = true;
let unread = 0;

pane.addEventListener("scroll", () => {
  const atBottom = pane.scrollHeight - pane.scrollTop - pane.clientHeight <= PIN_SLOP;
  if (atBottom) { pinned = true; unread = 0; hideJumpPill(); }
  else if (pinned) { pinned = false; }   // the user scrolled away: stop following
}, { passive: true });

function afterNewContent(isVerdict) {
  if (pinned) {
    pane.scrollTo({ top: pane.scrollHeight, behavior: prefersReduced ? "auto" : "smooth" });
  } else {
    unread += 1;
    showJumpPill(unread);                // "↓ 3 new"
  }
}
```

**Rule: never rebuild the transcript.** v0 called `replaceChildren()` on every
message and then slammed `scrollTop = scrollHeight`. That destroys text selection,
destroys scroll anchoring, and yanks the page while the user is reading. Instead:

- `transcript.final` → **append** one `<span class="seg">` to the pending block.
- `window.ready` → **move** the named segment nodes into a new `<p class="win">`.
  Move the existing nodes, do not re-create them.
- `claim.detected` → **split** only the affected `.seg` node's text and wrap the
  range. Touch nothing else.
- `claim.verdict` → **mutate class and dataset** on the existing `<mark>`. No
  re-render.

**Rule: a verdict landing must not reflow the line.** The sticker is present from
`claim.detected` onward as a `checking` pill. Reserve its final width so the
upgrade does not re-wrap the paragraph:

```css
.sticker { min-width: var(--sticker-reserve, 0px); }
```

Set `--sticker-reserve` on the `<mark>` when the verdict arrives only if the new
label is *narrower*; if it is wider, let it grow and rely on `overflow-anchor`.

**Rule: anchor the scroll above the change.**

```css
.transcript { overflow-anchor: auto; }
.transcript .win { overflow-anchor: auto; }
.jump-pill, .interim { overflow-anchor: none; }  /* never anchor to moving chrome */
```

`overflow-anchor` is what keeps the reader's position stable when a verdict lands on
a claim that is *above* the viewport and changes that paragraph's height. Excluding
the interim line is essential: it changes on every speech frame and would otherwise
become the anchor.

**Rule: smooth only when pinned.** Never set `scroll-behavior: smooth` globally —
it makes the jump-pill tap feel laggy and fights `scrollIntoView` on the sheet. Pass
`behavior` per call as shown above.

**The jump-to-live pill.** `position: sticky; bottom: var(--sp-5)`, right-aligned
inside the transcript pane, `--r-pill`, `--bg-raised`, `1px solid --hairline-strong`,
`padding: var(--sp-3) var(--sp-5)`, `--type-status`. Text: `↓ {n} new`. If a
CONTRADICTED verdict lands while unpinned, the pill's border becomes
`--v-contradicted-core` and the text becomes `↓ {n} new · 1 cap` — the one case
where we actively pull the reader back.

### 4.4 iOS safe areas and the keyboard

**Safe areas.** Never write `env()` inline; use the aliases `--safe-top`,
`--safe-bottom`, `--safe-left`, `--safe-right` from `tokens.css`. Rules:

- Top bar: `padding-top: var(--safe-top)`, height `calc(var(--topbar-h) + var(--safe-top))`.
- Dock: `padding-bottom: var(--safe-bottom)`, height `calc(var(--dock-h) + var(--safe-bottom))`.
- Transcript pane: horizontal padding includes `--safe-left` / `--safe-right`.
- The sheet's expanded height is `calc(92dvh - var(--safe-top))`.
- Background colours must extend *through* the safe area: set the inset as padding
  on the bar itself, never as a margin on the page.

**Heights.** Use `100dvh`, never `100vh`. On iOS Safari `100vh` is the *largest*
viewport (URL bar hidden), so a `100vh` layout is permanently taller than the screen
and the dock sits below the fold. `dvh` tracks the live viewport.

**Keyboard.** `interactive-widget=resizes-content` in the viewport meta makes the
layout viewport shrink when the keyboard opens, so a `dvh`-based grid and a
`position: fixed` dock both move up correctly with no JavaScript. That is the
primary mechanism. For older iOS that ignores the hint, add the fallback:

```js
const vv = window.visualViewport;
if (vv) {
  const sync = () => {
    const overlap = Math.max(0, window.innerHeight - vv.height - vv.offsetTop);
    document.documentElement.style.setProperty("--kb", overlap + "px");
  };
  vv.addEventListener("resize", sync);
  vv.addEventListener("scroll", sync);
  sync();
}
```

```css
:root { --kb: 0px; }
.dock { bottom: var(--kb); }
.transcript-pane { padding-bottom: calc(var(--sheet-peek-h) + var(--sp-9) + var(--kb)); }
```

When the keyboard opens: the sheet collapses to peek, the dock lifts, and the
transcript stays pinned if it was pinned. Do **not** scroll the input into view with
`scrollIntoView` — the browser already did it and a second scroll causes a visible
double-jump.

`--fs-input` is 17px. Any value below 16px makes iOS Safari zoom the viewport on
focus, and it never zooms back out. This is not negotiable.

---

## 5. The verdict moment

This is the product's hero moment. Specced frame by frame.

### 5.1 `checking` — the highlighter sweep

Begins on `claim.detected` (when `checkable: true`), ends when a verdict arrives.

**What it looks like:** the claim's words sit on `--accent-tint`, and a brighter
band of `--accent` at 22% travels left-to-right across them, continuously — a
marker being dragged over the words, over and over.

```css
mark.claim.checking {
  background-color: var(--accent-tint);
  background-image: linear-gradient(100deg,
      transparent 0%,
      rgba(228, 255, 79, 0.22) 45%,
      rgba(228, 255, 79, 0.22) 55%,
      transparent 100%);
  background-size: 220% 100%;
  background-repeat: no-repeat;
  border-bottom: 3px solid var(--accent);
  animation: sweep var(--dur-sweep) linear infinite;
}
@keyframes sweep {
  from { background-position: -110% 0; }
  to   { background-position:  210% 0; }
}
```

- **Duration:** `--dur-sweep` 1400ms, `linear`, infinite. Linear because a marker
  stroke has constant speed; easing it would read as a "loading shimmer", which is
  the generic thing we are avoiding.
- The `checking` sticker is a pill in `--accent-tint` with a 1px `--accent` border
  and the text `CHECKING` followed by an animated three-dot ellipsis that steps
  every 400ms (`steps(4)` on a `width` animation over a `···` glyph run).

**Reduced motion:** `animation: none`. Keep the static `--accent-tint` fill and the
3px `--accent` bottom border. The sticker reads `CHECKING…` with a static ellipsis.
Progress remains visible because the status line (§6.8) is *text* changing every few
hundred ms, and text changes are not motion. This is exactly why latency is
communicated with words and not with a spinner.

### 5.2 The sticker landing — `--dur-land`

Fires when `claim.verdict` arrives with the final verdict. Four things happen at
once, all keyed to the same 0ms.

**(a) The highlight tint wipes in, left to right.** 260ms (`--dur-base`),
`--ease-out`. The tint is *drawn on*, matching the highlighter metaphor.

```css
mark.claim[data-verdict] {
  background-image: linear-gradient(var(--v-tint), var(--v-tint));
  background-repeat: no-repeat;
  background-size: 0% 100%;
  animation: wipe var(--dur-base) var(--ease-out) forwards;
}
@keyframes wipe { to { background-size: 100% 100%; } }
```

`--v-tint` is set on the element by JS from the verdict enum
(`el.style.setProperty("--v-tint", `var(--v-${slug}-tint)`)`).

**(b) The underline draws in.** `border-bottom-width: 0 -> 3px` (4px for
CONTRADICTED's `double`) over 200ms, `--ease-out`, delayed 60ms so it lands just
behind the wipe. `border-bottom-style` is set instantly to the verdict's
`--v-*-line` value.

**(c) The sticker lands.** 420ms (`--dur-land`), `--ease-back`
`cubic-bezier(0.2, 1.4, 0.35, 1)`.

| Time | transform | opacity |
|---|---|---|
| 0% | `translateY(-6px) scale(0.72) rotate(-7deg)` | 0 |
| 55% | `translateY(0) scale(1.08) rotate(var(--sticker-tilt-alt))` | 1 |
| 78% | `translateY(0) scale(0.97) rotate(var(--sticker-tilt))` | 1 |
| 100% | `translateY(0) scale(1) rotate(var(--sticker-tilt))` | 1 |

```css
@keyframes sticker-land {
  0%   { transform: translateY(-6px) scale(.72) rotate(-7deg); opacity: 0; }
  55%  { transform: translateY(0) scale(1.08) rotate(var(--sticker-tilt-alt)); opacity: 1; }
  78%  { transform: translateY(0) scale(.97) rotate(var(--sticker-tilt)); opacity: 1; }
  100% { transform: translateY(0) scale(1) rotate(var(--sticker-tilt)); opacity: 1; }
}
.sticker[data-verdict] {
  animation: sticker-land var(--dur-land) var(--ease-back) both;
  will-change: transform;
}
```

The `--ease-back` overshoot is why it reads as a *physical object landing* rather
than an element appearing. The final resting tilt (`-1.5deg`, alternating to
`+1.5deg` on odd-indexed claims) is what stops a column of stickers looking like
form chips.

**(d) A one-shot ring flash.** 520ms, `ease-out`, `forwards`, no repeat. The ring is
the verdict colour, not the accent.

```css
@keyframes verdict-ring {
  0%   { box-shadow: 0 0 0 0 var(--v-core-a40); }
  60%  { box-shadow: 0 0 0 7px transparent; }
  100% { box-shadow: 0 0 0 0 transparent; }
}
```

Composite with `--shadow-sticker` so the sticker keeps its printed edge throughout.

**(e) CONTRADICTED only — the extra beat.** This verdict, and only this verdict,
gets two additions:

1. **A shake.** 180ms, `--ease-in-out`, on the `<mark>`:
   `translateX(0) -> -3px -> 3px -> -2px -> 0`, delayed 120ms so it lands *after*
   the sticker has already appeared. Exactly one cycle. Never loops.
2. **The strike draws.** The `line-through` is not `text-decoration` (which cannot
   animate). It is a 2px `--v-contradicted-core` bar as a `::before` on the `<mark>`
   at `top: 52%`, `width: 0 -> 100%`, 200ms, `--ease-out`, delayed 140ms.

Total elapsed for a CONTRADICTED landing: 0ms wipe starts → 420ms sticker settles →
520ms ring gone → 340ms strike complete. Everything is finished inside 540ms.

**Reduced motion, all of the above:**

```css
@media (prefers-reduced-motion: reduce) {
  mark.claim[data-verdict] { animation: none; background-size: 100% 100%; }
  .sticker[data-verdict] {
    animation: verdict-fade 120ms linear both;
    transform: none;                      /* no tilt either — tilt is motion-adjacent
                                             and some vestibular users report it */
  }
  @keyframes verdict-fade { from { opacity: 0 } to { opacity: 1 } }
  mark.claim.contradicted::before { animation: none; width: 100%; }
  mark.claim.contradicted { animation: none; }   /* no shake */
}
```

The verdict still *arrives* — it cross-fades over 120ms — so the change is still
perceptible. All transform, overshoot, shake and looping motion is removed, not
slowed. Slowing a shake is still a shake.

### 5.3 `provisional -> confirmed`

The fast verdict (~3.5s from search snippets) must be visibly, honestly marked as a
quick read, and the upgrade to the confirmed verdict (~8s) must be legible as an
event.

**Provisional appearance.** Same words, same glyph, same underline style. Different
*material*:

| Property | provisional | confirmed |
|---|---|---|
| sticker background | `--v-*-prov` (core @18%) | `--v-*-core` (solid) |
| sticker text | `--v-*-text` | `--v-*-ink` |
| sticker border | `1.5px dashed var(--v-*-core)` | `none` |
| shadow | `none` | `var(--shadow-sticker)` |
| prefix | `~` before the glyph | — |
| tag | `QUICK READ` in `--type-tier`, `--text-tertiary`, directly under the sticker | — |
| underline | `opacity: .6` on the border colour | full |

All provisional contrast ratios are measured and pass: NO CAP 8.74:1, ABSOLUTE CAP
7.26:1, SOME CAP 8.63:1, SOURCES ARE FIGHTING 8.68:1, COULD BE CAP 8.40:1, WORD
SALAD 6.56:1.

**Case A — same verdict confirmed (the common case).** 320ms (`--dur-slow`),
`--ease-out`:

```css
.sticker { transition:
  background-color var(--dur-slow) var(--ease-out),
  color            var(--dur-slow) var(--ease-out),
  border-color     var(--dur-slow) var(--ease-out),
  box-shadow       var(--dur-slow) var(--ease-out); }
```

- `background-color`: `--v-*-prov` → `--v-*-core`
- `color`: `--v-*-text` → `--v-*-ink`
- `border-color`: `--v-*-core` → `transparent`; `border-style` flips
  `dashed -> solid` at the 50% mark via a `transitionstart` + `setTimeout(160)`
  class swap (border-style is not interpolable — flip it at the midpoint where it
  is least visible).
- Simultaneously a 180ms `--ease-back` scale bump `1 -> 1.04 -> 1`.
- The `QUICK READ` tag collapses: `opacity 1 -> 0` over 140ms, then
  `height -> 0` over 140ms. Reserve its space from the start so the line does not
  re-wrap.

**Case B — the verdict CHANGED between provisional and confirmed.** This is a
different event and must not look like a colour transition. Use a card flip:

```css
@keyframes verdict-flip {
  0%   { transform: rotateX(0) scale(1); }
  50%  { transform: rotateX(90deg) scale(.96); }
  100% { transform: rotateX(0) scale(1) rotate(var(--sticker-tilt)); }
}
.sticker.upgrading { animation: verdict-flip var(--dur-slow) var(--ease-in-out) both; }
```

320ms, `--ease-in-out`. **Swap the label text and all colour tokens exactly at the
50% keyframe** (`setTimeout(160)`), when the sticker is edge-on and invisible. The
highlight tint cross-fades from the old `-tint` to the new one over the same 320ms.
If the new verdict is CONTRADICTED, fire the §5.2(e) shake and strike after the flip
completes.

The flip is the honest signal for "we changed our mind with better evidence", and it
is the one animation in the product that a judge will remember.

**Reduced motion:** both cases collapse to a 120ms cross-fade of
`background-color`, `color` and `border-color`. No flip, no scale, no rotate. In
case B, additionally add a `⟳ UPDATED` tag in `--type-tier` / `--text-tertiary` next
to the sticker for 4s, because without the flip there is no other signal that the
verdict changed.

---

## 6. Component specs

### 6.1 Claim highlight — `<mark class="claim">`

Wraps an arbitrary character range inside a `.seg`. A claim's `spans` can straddle
two segments (see `claim_detected` in `server/messages.py`), so **one claim can
produce several `<mark>` elements.** Rules:

- All fragments of one claim share `data-claim-id` and get the same tint and
  underline.
- **Only the last fragment carries the sticker.**
- `border-radius` is applied only to the outer edges:
  first fragment `--r-xs 0 0 --r-xs`, last `0 --r-xs --r-xs 0`, middle `0`.
  Use `box-decoration-break: clone` so a fragment that line-wraps keeps its padding
  on both lines.

```css
mark.claim {
  background: transparent;
  color: inherit;                       /* never recolour transcript text — it must stay
                                           --text-primary at 17.65:1 on every tint */
  padding: 2px 1px;
  border-radius: var(--r-xs);
  border-bottom: 0 solid transparent;
  box-decoration-break: clone;
  -webkit-box-decoration-break: clone;
  cursor: pointer;
  transition: background-color var(--dur-base) var(--ease-out);
}
/* 44px-tall tap target without changing line height */
mark.claim::after {
  content: ""; position: absolute; inset-block: -11px; inset-inline: 0;
}
mark.claim { position: relative; }
```

| State | Background | Border-bottom | Text | Other |
|---|---|---|---|---|
| `.detected` (pre-check, `checkable:false`) | `--v-salad-tint` | none | inherit | 0.85 opacity |
| `.checking` | `--accent-tint` + sweep | `3px solid --accent` | inherit | §5.1 |
| `.provisional` | `--v-*-tint` | `3px var(--v-*-line) var(--v-*-core)` at `opacity:.6` | inherit | dashed sticker |
| `.confirmed` | `--v-*-tint` | `3px var(--v-*-line) var(--v-*-core)`; `4px double` for CONTRADICTED | inherit | full sticker |
| `.confirmed.contradicted` | as above | `4px double` | inherit | animated strike bar |
| `.error` | `--v-insufficient-tint` | `3px dotted --v-insufficient-core` | inherit | sticker reads `COULDN'T CHECK` |
| `:hover` / `:focus-visible` | tint + `--hairline-strong` inset ring | — | — | `outline: var(--focus-ring-width) solid var(--focus-ring); outline-offset: var(--focus-ring-offset)` |
| `[aria-expanded="true"]` (its card is open) | tint + `inset 0 0 0 1px var(--v-*-core)` | — | — | — |

**Transcript text stays `--text-primary` on every tint** — 13.3:1 to 15.0:1
measured. Never tint the words themselves; tint the paper behind them.

**Accessibility markup:**

```html
<mark class="claim confirmed" data-claim-id="c7" data-verdict="CONTRADICTED"
      tabindex="0" role="button" aria-expanded="false"
      aria-label="Claim: Notion is eight dollars per seat. Verdict: absolute cap, contradicted. Confirmed.">
  eight dollars a seat<span class="sticker" aria-hidden="true">✕ ABSOLUTE CAP</span>
</mark>
```

The sticker is `aria-hidden` because its text is already in the `aria-label`;
without this a screen reader reads the claim twice. Verdict changes are announced
via a single `aria-live="polite"` region, not by re-announcing the mark.

### 6.2 Sticker pill

The single most important visual moment in the product.

```css
.sticker {
  display: inline-flex;
  align-items: center;
  gap: var(--sp-2);
  margin-left: var(--sp-3);
  padding: 3px var(--sp-3) 4px;          /* 3/6/4/6 — optically centred for 900-weight caps */
  border-radius: var(--r-sm);            /* 6px: a stamp, not a lozenge */
  font: var(--type-sticker);
  letter-spacing: var(--ls-sticker);
  text-transform: uppercase;
  white-space: nowrap;
  vertical-align: 0.05em;
  transform: rotate(var(--sticker-tilt));
  box-shadow: var(--shadow-sticker);
  user-select: none;
}
```

Per verdict:

| Verdict | Fill | Text | Border | Glyph |
|---|---|---|---|---|
| SUPPORTED | `--v-supported-core` | `--v-supported-ink` (10.73:1) | none | `✓` |
| CONTRADICTED | `--v-contradicted-core` | `--v-contradicted-ink` (6.01:1) | `2px solid var(--ink)` keyline | `✕` |
| PARTIALLY_SUPPORTED | `linear-gradient(90deg, var(--v-partial-core) 50%, var(--v-partial-tint) 50%)` | `--v-partial-ink` on the left half; add `text-shadow: 0 0 6px var(--v-partial-tint)` so the right-half characters stay legible — or simpler and preferred: keep the whole label on the solid half by padding the gradient stop to 62% | `1px solid var(--v-partial-core)` | `≈` |
| DISPUTED | `--v-disputed-core` | `--v-disputed-ink` (8.91:1) | none | `⇄` |
| INSUFFICIENT_EVIDENCE | transparent | `--v-insufficient-text` (11.07:1 on base) | `1.5px solid var(--v-insufficient-core)` | `?` |
| NOT_FACT_CHECKABLE | `--v-salad-tint` | `--v-salad-text` (8.21:1 on base) | `1px dotted var(--v-salad-core)` | `~` |

**`SOURCES ARE FIGHTING` is 20 characters** and will not fit inline at 12px beside a
claim on a 390px screen. Handle it deterministically, not by wrapping:

```css
.sticker[data-verdict="DISPUTED"] { white-space: normal; max-width: 9ch; line-height: 1.02; }
@media (min-width: 900px) { .sticker[data-verdict="DISPUTED"] { max-width: none; white-space: nowrap; } }
```

Two stacked lines — `SOURCES` / `ARE FIGHTING` — on phone; one line on laptop. Never
truncate a sticker string with an ellipsis: the words are the accessibility signal.

**CONTRADICTED gets one extra gram of weight everywhere:** 4px horizontal padding
instead of 6px feels wrong here — instead give it `padding-inline: var(--sp-4)` and
the `--ink` keyline. It should be perceptibly the chunkiest object on the screen.

**Checking sticker:** `background: var(--accent-tint)`, `1px solid var(--accent)`,
`color: var(--accent)` (17.32:1 on base), label `CHECKING`, no tilt, no shadow —
it is not yet an object, it is a placeholder.

### 6.3 Evidence detail — bottom sheet (phone) / card (laptop)

**Phone: a three-snap bottom sheet.**

| Snap | Height | Shows |
|---|---|---|
| `peek` (default) | `--sheet-peek-h` 96px + `--safe-bottom` | grab handle, the most recent verdict's sticker, and the first 40 chars of its normalized claim |
| `half` | `46dvh` | the full most-recent evidence card |
| `full` | `calc(92dvh - var(--safe-top))` | scrollable stack of all claims, newest first |

```css
.sheet {
  position: fixed; inset-inline: 0; bottom: 0; z-index: var(--z-sheet);
  background: var(--bg-sheet);
  border-top: 1px solid var(--hairline-strong);
  border-radius: var(--r-xl) var(--r-xl) 0 0;
  box-shadow: var(--shadow-sheet);
  transition: height var(--dur-slow) var(--ease-snap);
  padding-bottom: var(--safe-bottom);
}
.sheet-handle { width: 36px; height: 4px; border-radius: var(--r-pill);
                background: var(--hairline-strong); margin: var(--sp-4) auto; }
.sheet-handle-hit { min-height: var(--tap-min); }   /* 44px invisible hit area */
```

- Open: drag the handle, or tap any claim highlight (which opens to `half` and
  scrolls that claim's card into view).
- Close: drag down, tap the scrim, or press Escape.
- `--ease-snap` (`cubic-bezier(0.16, 1, 0.3, 1)`, expo-out) at `--dur-slow` is what
  makes it feel native rather than like a CSS transition.
- **The sheet never auto-expands.** The peek rail updates to the newest verdict; the
  sheet stays where the user put it. An auto-expanding sheet during a live demo will
  cover the transcript at the worst moment.
- While `full`, the scrim (`--bg-scrim`, `--z-scrim`) fades in over `--dur-base` and
  the transcript behind it gets `inert`.
- Reduced motion: `transition-duration: 120ms`, `--ease-snap` is `linear`.

**Laptop:** the same cards render in the 380px rail, newest first, `--sp-5` gap. No
sheet, no scrim, no snaps.

**The evidence card itself:**

```css
.card {
  background: var(--bg-raised);
  border: 1px solid var(--hairline-strong);
  border-left: 3px solid var(--v-core);   /* the one place a card carries verdict colour */
  border-radius: var(--r-lg);
  padding: var(--sp-6);
  box-shadow: var(--shadow-card);         /* none — cards do not float */
}
```

Vertical order and spacing, top to bottom:

| Element | Type | Colour | Margin-bottom |
|---|---|---|---|
| Sticker (full size, no tilt) + elapsed `1.9s` right-aligned | `--type-sticker` / `--type-meta` | per verdict / `--text-tertiary` | `--sp-5` |
| Normalized claim | `--type-claim` | `--text-primary` | `--sp-4` |
| Summary (one sentence) | `--type-summary` | `--text-secondary` | `--sp-5` |
| Correction — `actually: $20 per seat per month` | `--type-correction` | `--v-partial-text` | `--sp-5` |
| Quotes (0–3) | `--type-quote` | `--text-secondary` | `--sp-4` each |
| Sources (0–4) | `--type-source` | see §6.4 | `--sp-3` each |
| Footer: confidence bars + `kind · hedge` | `--type-confidence` / `--type-meta` | `--conf-label` / `--text-tertiary` | 0 |

**The correction block** is the most valuable text in the card and gets a container
so it cannot be skimmed past:

```css
.correction {
  background: var(--v-partial-tint-r);            /* #3A2D23 — text-primary on it 12.07:1 */
  border-left: 3px solid var(--v-partial-core);
  border-radius: 0 var(--r-md) var(--r-md) 0;
  padding: var(--sp-4) var(--sp-5);
}
.correction b { color: var(--v-partial-text); font-weight: var(--fw-bold); }
```

The literal word `actually:` is set in `--text-tertiary`; the corrected value in
`--text-primary` at `--fw-bold`. Amber, not red: a correction is information, not an
accusation — the accusation is already on the sticker.

**Quotes** are verbatim and must look verbatim:

```css
.quote {
  background: var(--bg-inset);
  border-left: 2px solid var(--hairline-strong);
  border-radius: 0 var(--r-md) var(--r-md) 0;
  padding: var(--sp-4) var(--sp-5);
  font: var(--type-quote);
  color: var(--text-secondary);          /* 8.54:1 on --bg-inset */
}
.quote::before { content: "\201C"; }
.quote::after  { content: "\201D"; }
```

Never truncate a quote with CSS `line-clamp` — truncating evidence is a credibility
failure. Truncate on the server, at a word boundary, with a real `…`.

### 6.4 Source link with tier indicator

```html
<a class="source" data-tier="1" href="…" target="_blank" rel="noopener noreferrer">
  <span class="tier" aria-label="Tier 1, primary source">◆ PRIMARY</span>
  <span class="host">notion.com</span>
  <span class="eid">E3</span>
</a>
```

```css
.source {
  display: flex; align-items: center; gap: var(--sp-3);
  min-height: var(--tap-min);
  padding: var(--sp-3) var(--sp-4);
  border-radius: var(--r-md);
  background: var(--bg-inset);
  border: 1px solid transparent;
  font: var(--type-source);
  color: var(--text-secondary);
  text-decoration: none;
  transition: background-color var(--dur-instant) var(--ease-out),
              border-color     var(--dur-instant) var(--ease-out);
}
.source:hover  { background: var(--bg-raised); border-color: var(--hairline-strong); }
.source:focus-visible { outline: var(--focus-ring-width) solid var(--focus-ring);
                        outline-offset: var(--focus-ring-offset); }
.source:active { background: var(--bg-base); }

.tier {
  font: var(--type-tier); letter-spacing: var(--ls-tier); text-transform: uppercase;
  padding: 2px var(--sp-3); border-radius: var(--r-xs); border-width: 1px;
  white-space: nowrap;
}
.source[data-tier="1"] .tier { color: var(--tier-1-fg); background: var(--tier-1-bg);
                               border: 1px var(--tier-1-style) var(--tier-1-border); }
.source[data-tier="2"] .tier { color: var(--tier-2-fg); background: var(--tier-2-bg);
                               border: 1px var(--tier-2-style) var(--tier-2-border); }
.source[data-tier="3"] .tier { color: var(--tier-3-fg); background: var(--tier-3-bg);
                               border: 1px var(--tier-3-style) var(--tier-3-border); }
.source[data-tier="4"] .tier { color: var(--tier-4-fg); background: var(--tier-4-bg);
                               border: 1px var(--tier-4-style) var(--tier-4-border); }
```

`.host` is `--text-primary` at `--fw-medium`; `.eid` (the `evidence_id`, e.g. `E3`)
is `--text-tertiary`, right-aligned with `margin-left: auto`, and is what lets a
judge match a quote to its source. Strip `www.` from hostnames; never show a full
URL — it destroys the line length.

The non-colour signal for tier is the **border style and the glyph**
(`◆ ◇ ◌ ⚠`) plus the word. Tier 1 is the only filled badge.

### 6.5 Confidence indicator

```html
<span class="conf" data-level="medium" aria-label="Medium confidence">
  <i></i><i></i><i></i> MEDIUM CONFIDENCE
</span>
```

```css
.conf { display: inline-flex; align-items: center; gap: var(--sp-2);
        font: var(--type-confidence); letter-spacing: var(--ls-label);
        text-transform: uppercase; color: var(--conf-label); }
.conf i { width: 4px; height: 12px; border-radius: 1px; background: var(--conf-empty); }
.conf[data-level="high"]   i:nth-child(-n+3),
.conf[data-level="medium"] i:nth-child(-n+2),
.conf[data-level="low"]    i:nth-child(-n+1) { background: var(--conf-fill); }
.conf i + i { margin-left: 0; }
.conf { gap: 3px; }
```

Deliberately neutral. **Confidence must never be green/amber/red** — a green
"high confidence" beside a red ABSOLUTE CAP is the single most confusing thing this
UI could show. Confidence describes *how sure we are*, the verdict describes *what
we found*, and they are allowed to disagree.

When `confidence === "none"` the element is omitted entirely, not rendered empty.

### 6.6 BS index counter

Six cells. Phone: a single horizontal row in the top bar, right-aligned, scrollable
if needed. Laptop: a row at the top of the rail with labels.

```css
.bs-index { display: flex; gap: var(--sp-3); align-items: baseline; }
.bs-cell {
  display: flex; flex-direction: column; align-items: center; gap: 1px;
  min-width: 28px;
  border-top: 2px solid var(--v-core);     /* the verdict's colour, as a cap rule */
  padding-top: var(--sp-2);
}
.bs-num   { font: var(--type-counter-num); letter-spacing: var(--ls-display);
            color: var(--text-primary); font-variant-numeric: tabular-nums; }
.bs-label { font: var(--type-counter-lbl); letter-spacing: var(--ls-label);
            text-transform: uppercase; color: var(--text-tertiary); }
.bs-cell[data-count="0"] { opacity: .45; }
```

Phone (`< 900px`): `.bs-label` is `display: none` and the cap rule carries the
identity; laptop and presentation mode show labels. The cap rule is 2px so the six
counters read as a *tally strip*, which is also the non-colour signal — cell order
is fixed (SUPPORTED, CONTRADICTED, PARTIALLY_SUPPORTED, DISPUTED,
INSUFFICIENT_EVIDENCE, NOT_FACT_CHECKABLE) and never re-sorted by count.

**Tick animation:** on increment, `--dur-fast` 140ms `--ease-out`,
`transform: translateY(-3px) -> 0` plus `color: var(--v-*-text) -> var(--text-primary)`.
The CONTRADICTED cell additionally scales `1 -> 1.15 -> 1` over `--dur-base`.
Reduced motion: colour flash only, no translate, no scale.

### 6.7 Listen button

The primary action. Phone: full-width inside the dock, 56px tall. Laptop: auto width
in the dock, 44px tall.

```css
.listen {
  display: flex; align-items: center; justify-content: center; gap: var(--sp-3);
  width: 100%; min-height: 56px;
  border-radius: var(--r-pill);
  border: 2px solid transparent;
  font: var(--type-button);
  cursor: pointer;
  transition: background-color var(--dur-fast) var(--ease-out),
              border-color     var(--dur-fast) var(--ease-out),
              transform        var(--dur-instant) var(--ease-out);
}
.listen:active { transform: scale(.98); }
.listen:focus-visible { outline: var(--focus-ring-width) solid var(--focus-ring);
                        outline-offset: var(--focus-ring-offset); }
```

| State | Fill | Text | Border | Label | Motion |
|---|---|---|---|---|---|
| **idle** | `transparent` | `--accent` (17.32:1) | `2px solid var(--accent-dim)` | `● START LISTENING` | none |
| **listening** | `--accent` | `--accent-ink` (17.76:1) | `2px solid var(--accent)` | `● LISTENING — TAP TO STOP` | the `●` pulses `opacity 1 -> .35 -> 1`, 1400ms `--ease-in-out` infinite; a 2px `--accent-glow` ring breathes `0 -> 6px -> 0` over the same period |
| **connecting** | `transparent` | `--text-secondary` | `2px dashed var(--hairline-strong)` | `CONNECTING…` | ellipsis steps, `disabled` |
| **error** | `--v-contradicted-tint` | `--v-contradicted-text` (7.47:1 on that tint) | `2px solid var(--v-contradicted-core)` | `MIC BLOCKED — TAP TO RETRY` | one 180ms shake, then static |

The listening state is the only place besides `checking` where `--accent` appears as
a large fill. That is intentional and it is the visual rhyme of the product: the
button is yellow while the highlighter is yellow.

**Reduced motion:** the `●` stops pulsing and instead becomes solid `--v-contradicted-core`
(a static red record dot — the universal non-motion signal for "recording"); the ring
is removed; the error shake is removed.

`aria-pressed` reflects the listening state. The state change is announced through
the same `aria-live="polite"` region as verdicts.

### 6.8 Status line

Latency is the headline feature, so this element must never be still.

```css
.status {
  display: flex; align-items: center; gap: var(--sp-3);
  min-height: 28px;
  font: var(--type-status);
  color: var(--text-secondary);          /* 8.15:1 on --bg-raised */
  white-space: nowrap; overflow: hidden; text-overflow: ellipsis;
}
.status-spinner { /* a 4-frame ASCII rotor: ◜ ◝ ◞ ◟ */
  width: 1ch; color: var(--accent);
  animation: rotor 480ms steps(4) infinite;
}
```

Mono (`--font-mono`) on purpose: stage strings like `sifting 15 of 98 passages`
change their digits constantly, and a monospace face keeps the line from shifting
sideways on every update. This is also why `font-variant-numeric: tabular-nums` is
global.

**Text updates** (`claim.status`, `server.note`) animate with a 140ms `--dur-fast`
vertical roll: outgoing text `translateY(0 -> -6px)` + fade out over 70ms, incoming
`translateY(6px -> 0)` + fade in over 70ms. The roll makes progress feel *mechanical
and fast*; a cross-fade makes it feel soft and slow.

Connection states (`not connected`, `disconnected, retrying…`) render in
`--text-tertiary` with the rotor replaced by a static `◌`. A hard error renders in
`--error-text` (8.80:1 on base) with a `⚠`.

**Never use a spinning circle here.** A spinner means "waiting, indefinitely". The
whole pitch is that the machine is doing *specific, nameable work* right now, and
naming the work is the design.

**Reduced motion:** the rotor becomes a static `◜` and the roll becomes an instant
text swap. The *words* still change every few hundred ms, which is the actual
progress signal.

### 6.9 Text input (the no-mic fallback)

```css
.say {
  width: 100%;
  min-height: var(--tap-min);
  padding: var(--sp-4) var(--sp-5);
  border-radius: var(--r-md);
  background: var(--bg-inset);
  border: 1px solid var(--hairline-strong);
  color: var(--text-primary);            /* 16.90:1 on --bg-inset */
  font: var(--type-input);               /* 17px — below 16px iOS zooms and never unzooms */
  caret-color: var(--accent);
  transition: border-color var(--dur-fast) var(--ease-out);
}
.say::placeholder { color: var(--text-tertiary); }   /* 4.13:1 on inset — placeholder
                                                        is non-essential by WCAG, and the
                                                        real label is the <label> above */
.say:focus { outline: none; border-color: var(--accent); box-shadow: 0 0 0 3px var(--accent-glow); }
```

Placeholder: `type a claim instead — no mic needed`. There is a visually-hidden
`<label>` for screen readers; a placeholder is never the only label.

On phone the input lives inside the dock, **collapsed by default** to a 44px
`⌨ TYPE INSTEAD` ghost button beside the listen button, expanding to full width when
tapped (`--dur-base`, `--ease-out`, animating `flex-grow`). On laptop it is always
visible at full width in the dock. Rationale: on a phone the listen button must be
unmissable and the keyboard fallback must not compete with it.

On submit: clear the field, keep focus, and immediately render an optimistic pending
segment in the transcript so the user sees their words land before the server
answers.

### 6.10 Transcript text states

| State | Source message | Colour | Extra |
|---|---|---|---|
| **interim** | `transcript.interim` | `--text-tertiary` (5.67:1) | trailing `▎` caret, `opacity 1 -> .3` blink at 1000ms `steps(2)`; sits in its own node that is replaced wholesale (it is the one element allowed to be re-rendered every frame) |
| **pending** | `transcript.final`, not yet in a window | `--text-secondary` (8.92:1) | no other treatment |
| **settled** | `window.ready` | `--text-primary` (17.65:1) | claims may be highlighted inside |
| **skipped** | `window.skipped` | `--text-secondary` at `opacity .7` | a `--type-meta` chip in `--text-tertiary` with a 1px `--hairline` border and `--r-pill`: `skipped: {reason}` |

Settled windows are `<p class="win">` with `margin-block-end: var(--sp-6)`. Paragraph
spacing — not indentation, not rules — is what separates windows; the transcript
should read like a transcript, not like a log.

The `window.reason` debug chip stays behind the dev toggle exactly as in v0, but
restyled to the `.chip` spec above. Hide it in presentation mode.

### 6.11 Error state — `claim.error`

Not a verdict. Never styled as one, because the six verdict strings are fixed and
"COULDN'T CHECK" is not among them.

Sticker: `--bg-raised` fill, `1px dashed var(--hairline-strong)`,
`--text-secondary` text (8.15:1), glyph `⚠`, label `COULDN'T CHECK`, no tilt, no
shadow, no landing animation — a 120ms fade only. The highlight gets
`--v-insufficient-tint` with a dotted underline. The card shows `msg.message` in
`--error-text` and a `RETRY` text button. It is excluded from the BS index.

---

## 7. Motion and easing

Five durations, four curves. If a component needs a sixth of either, the component
is wrong.

| Token | Value | Used by |
|---|---|---|
| `--dur-instant` | 90ms | source-link hover, button `:active` scale, mark hover tint |
| `--dur-fast` | 140ms | focus ring, listen-button state change, BS counter tick, status-line text roll |
| `--dur-base` | 220ms | highlight tint wipe, evidence card enter, sheet snap-back, underline draw, input expand |
| `--dur-slow` | 320ms | sheet open/close, `provisional → confirmed` (both cases), scrim fade |
| `--dur-land` | 420ms | **the sticker landing, and nothing else** |
| `--dur-sweep` | 1400ms | the checking sweep, the listening-dot pulse |

| Curve | Value | Character | Used by |
|---|---|---|---|
| `--ease-out` | `cubic-bezier(0.22, 0.61, 0.36, 1)` | arrives fast, settles gently | the default; everything not listed below |
| `--ease-in-out` | `cubic-bezier(0.65, 0, 0.35, 1)` | symmetric, deliberate | the `provisional → confirmed` flip, the CONTRADICTED shake, the listening pulse |
| `--ease-back` | `cubic-bezier(0.2, 1.4, 0.35, 1)` | overshoots past the target | **stickers only** — the landing, and the confirmed scale bump. Using this anywhere else makes the whole UI feel bouncy and cheap, and it steals the one moment that is supposed to be special. |
| `--ease-snap` | `cubic-bezier(0.16, 1, 0.3, 1)` | expo-out, very fast then very slow | the bottom sheet, and only the bottom sheet |
| `linear` | — | constant speed | the checking sweep and the status rotor — both are *machines running*, not things arriving |

**Global reduced-motion contract.** `tokens.css` already collapses the durations.
That is necessary but **not sufficient** — every component must also drop to its
named fallback:

| Component | Reduced-motion fallback |
|---|---|
| checking sweep | removed; static `--accent-tint` + solid accent underline |
| sticker landing | 120ms opacity cross-fade; no scale, no rotate, no tilt, no ring |
| CONTRADICTED shake + strike | removed; strike rendered at full width immediately |
| provisional → confirmed | 120ms colour cross-fade; no flip, no bump; add `⟳ UPDATED` tag for 4s if the verdict changed |
| sheet | 120ms linear height change |
| status line | instant text swap; rotor static |
| listening dot | static red record dot, no pulse, no ring |
| BS counter tick | colour flash only |
| autoscroll | `behavior: "auto"` instead of `"smooth"` |

Detect it once and mirror it for JS:

```js
const mq = matchMedia("(prefers-reduced-motion: reduce)");
const sync = () => document.documentElement.toggleAttribute("data-reduced", mq.matches);
mq.addEventListener("change", sync); sync();
```

---

## 8. Demo considerations

90 seconds, projected, judges 3–8 metres away, a room with the lights up.

### 8.1 What must be legible from the back of the room

In priority order. Everything else is allowed to be unreadable from 6m.

1. **The sticker words.** A judge who reads nothing else must read `ABSOLUTE CAP`.
2. **The struck-through claim text.** Strike-through survives projector washout when
   colour does not.
3. **The BS index numerals.** One glance tells the story of the whole demo.
4. **The status line.** `sifting 15 of 98 passages` is the latency pitch, in words.
5. **The transcript.** They should be able to follow it, not study it.

Everything in items 1–4 is at `--fs-sticker` 20px, `--fs-counter-num` 48px and
`--fs-status` 18px under `[data-present]`. Item 5 is `--fs-transcript` 38px.

### 8.2 What should be visually loudest

Strict order, and the design must enforce it:

1. A **CONTRADICTED** sticker landing (solid hot red, `--ink` keyline, overshoot,
   shake, strike). Nothing else in the product is permitted this much energy.
2. The **checking sweep** — highlighter yellow, the brightest value in the system,
   moving.
3. The **listen button** while listening — the same yellow, large, pulsing.
4. The **transcript**.
5. Everything else.

Items 1 and 3 must never be on screen in the same visual weight: when a
CONTRADICTED verdict lands, the listening button's ring animation pauses for
`--dur-land` + 200ms so nothing competes with the hero moment. This is one line of
JS and it is worth it.

### 8.3 Presentation mode — yes, build it

One attribute on `<html>`, no separate stylesheet, no build step. Toggle with
`Shift+P` (and a long-press on the wordmark, for the phone).

```js
addEventListener("keydown", e => {
  if (e.key === "P" && e.shiftKey) document.documentElement.toggleAttribute("data-present");
});
```

`:root[data-present]` in `tokens.css` already does the type ramp and raises every
verdict tint from 16% to ~26% opacity-equivalent, because a projector's black level
is grey and a 16% tint disappears into it. On top of the token changes,
`chrome.css` should add:

```css
:root[data-present] .dev-toggle,
:root[data-present] .chip.why,
:root[data-present] .eid            { display: none; }
:root[data-present] .transcript     { --measure: 980px; }
:root[data-present] .win:not(:nth-last-child(-n+4)) { display: none; }
:root[data-present] .sticker        { box-shadow: 0 2px 0 rgba(7,9,13,.6), 0 4px 12px rgba(7,9,13,.5); }
```

What presentation mode does, in one list:

- Transcript 22 → **38px**, stickers 12 → **20px**, counters 26 → **48px**, status
  13 → **18px**.
- Verdict tints raised ~10 percentage points so they survive a washed-out projector.
- **Only the last four windows render.** Old transcript is hidden, so the live text
  always sits in the vertical middle of the frame instead of scrolling off the top
  of a projected image where nobody can see it.
- Dev chips, `window.reason` chips, and evidence ids are hidden — they are noise to
  an audience.
- The sticker shadow doubles so the sticker still reads as a physical object after
  the projector eats the low-contrast edge.
- The sheet stays at `half` so the newest evidence card is always visible without a
  gesture.

**Have it bound before you walk up.** Toggling it live is a 200ms moment that reads
as competence; discovering on stage that 22px is unreadable from row 4 is the
failure this section exists to prevent.

### 8.4 Demo-day hygiene

- Test at **exactly 1280×720** as well as on the phone: many projectors are 720p and
  many laptops mirror at that resolution.
- Turn **Night Shift / True Tone off**. They shift `--accent` toward orange, which
  is the one thing that would make the checking state collide with SOME CAP.
- Ship **without** the Archivo Black `<link>` unless the venue wifi is proven. The
  fallback is designed and tested; a blocked font request that hangs for 3s is not.
- Check the whole UI in greyscale once (macOS: Accessibility → Display → Color
  Filters → Grayscale) against the §2.5 table. If you can still name every verdict,
  the projector cannot hurt you.
- `prefers-reduced-motion` should be tested at least once. A judge with it enabled
  will otherwise see a product where nothing appears to happen.

---

## 9. Anti-patterns

Explicitly forbidden. Each of these is a direction the implementation will drift
toward if left alone.

**Layout**

- ❌ A fixed-width right rail on a phone. The rail exists only ≥900px; below that it
  is a bottom sheet with different interaction rules.
- ❌ A third column, ever. Two regions maximum: words, and evidence about words.
- ❌ `100vh`. Use `100dvh`. `100vh` is wrong on iOS and hides the dock.
- ❌ Cards inside cards. One border depth, maximum.
- ❌ `position: fixed` elements without `env(safe-area-inset-*)` padding.
- ❌ Letting the page widen past 1440px.

**Colour**

- ❌ Raw hex anywhere outside `tokens.css`.
- ❌ Reintroducing a generic purple/indigo accent. The accent is a highlighter and
  it has a reason.
- ❌ Collapsing PARTIALLY_SUPPORTED and DISPUTED into one colour class, the way v0
  did. Six verdicts, six treatments.
- ❌ Colouring confidence green/amber/red. Confidence is neutral bars.
- ❌ Colouring trust tiers with verdict hues (except tier 4's borrowed red).
- ❌ Recolouring the transcript text itself inside a highlight. Tint the paper, not
  the ink.
- ❌ `rgba()` verdict tints on the transcript — overlapping spans double-darken and
  silently break contrast. The `-tint` tokens are pre-composited for this reason.
- ❌ Gradients as decoration. The only gradients in the system are the checking sweep
  and the SOME CAP split fill, and both encode meaning.
- ❌ Glows, neon, glassmorphism, `backdrop-filter` on anything except the sheet
  scrim.

**Typography**

- ❌ Any size not in the §3.2 table.
- ❌ A required webfont. One optional font, display use only, with a designed
  fallback.
- ❌ Different sizes or weights for interim vs pending vs settled transcript — it
  reflows the paragraph under the reader.
- ❌ `text-transform: lowercase` as a "style" (v0 did this on headings). Lowercase
  chrome is a 2019 side-project tell. Use real case, and reserve uppercase for
  stickers, labels and tier badges.
- ❌ Proportional numerals anywhere a number changes.
- ❌ An input smaller than 16px.
- ❌ Truncating a sticker string, a source quote, or a verdict label with an
  ellipsis. Those words *are* the accessibility layer.

**Motion**

- ❌ A spinner. Name the work instead.
- ❌ `--ease-back` on anything except a sticker.
- ❌ Any looping animation other than the checking sweep, the listening pulse and
  the status rotor. Three looping things on screen is already the ceiling.
- ❌ An animation longer than `--dur-land` (420ms). A demo is 90 seconds; nothing
  may take half a second to tell the user something.
- ❌ Only zeroing durations for `prefers-reduced-motion` and calling it done. Every
  transform-based animation needs its named opacity fallback (§7).
- ❌ Auto-expanding the sheet on a new verdict. It will cover the transcript at the
  worst possible second of the demo.

**Behaviour**

- ❌ `replaceChildren()` on the transcript, or `scrollTop = scrollHeight`
  unconditionally. Both are in v0 and both must go.
- ❌ Scrolling to the bottom while the user is reading older text.
- ❌ Reflowing a paragraph when a verdict lands on a claim above the fold.
- ❌ Re-announcing an entire claim to a screen reader on every status update. One
  `aria-live="polite"` region, verdict transitions only.
- ❌ `outline: none` without an equally visible replacement. `--focus-ring` is
  17.32:1 on base; there is no excuse.

---

## Appendix A — message type → UI effect

The full contract lives in `server/messages.py`. This is what each message changes
on screen.

| Message | UI effect |
|---|---|
| `server.note` | status line text, `--text-secondary`, roll transition |
| `transcript.interim` | replace the interim node; `--text-tertiary` + caret |
| `transcript.final` | clear interim; **append** a `.seg` to the pending block, `--text-secondary` |
| `window.ready` | **move** the named `.seg` nodes into a new `<p class="win">`; recolour to `--text-primary` over `--dur-base` |
| `window.skipped` | append a `skipped: {reason}` chip; dim the window to `opacity: .7` |
| `claim.detected` | wrap `spans` in `<mark class="claim">`; if `checkable` → `.checking` + sweep + `CHECKING` sticker; else → `.detected` at `--v-salad-tint` |
| `claim.status` | status line roll; if that claim's card is open, update its inline stage text |
| `claim.evidence` | render source rows with tier badges *before* the verdict arrives — this is what makes the wait feel productive |
| `claim.verdict` (provisional) | §5.3 provisional treatment; `QUICK READ` tag |
| `claim.verdict` (confirmed) | §5.2 landing, or §5.3 upgrade if a provisional is already showing; BS index cell ticks |
| `claim.error` | §6.11 error state; excluded from the BS index |

## Appendix B — verdict slug mapping

JS sets one attribute; CSS does everything else.

```js
const SLUG = {
  SUPPORTED:            "supported",
  CONTRADICTED:         "contradicted",
  PARTIALLY_SUPPORTED:  "partial",
  DISPUTED:             "disputed",
  INSUFFICIENT_EVIDENCE:"insufficient",
  NOT_FACT_CHECKABLE:   "salad",
};

function paint(el, verdict) {
  const s = SLUG[verdict];
  el.dataset.verdict = verdict;
  el.style.setProperty("--v-core", `var(--v-${s}-core)`);
  el.style.setProperty("--v-text", `var(--v-${s}-text)`);
  el.style.setProperty("--v-tint", `var(--v-${s}-tint)`);
  el.style.setProperty("--v-tint-r", `var(--v-${s}-tint-r)`);
  el.style.setProperty("--v-prov", `var(--v-${s}-prov)`);
  el.style.setProperty("--v-ink",  `var(--v-${s}-ink)`);
  el.style.setProperty("--v-line", `var(--v-${s}-line)`);
}
```

Components then reference only the generic `--v-*` names, so every verdict-aware
component is written exactly once:

```css
mark.claim.confirmed {
  background-color: var(--v-tint);
  border-bottom: 3px var(--v-line) var(--v-core);
}
.sticker[data-verdict] { background: var(--v-core); color: var(--v-ink); }
.card                  { border-left-color: var(--v-core); }
.bs-cell               { border-top-color: var(--v-core); }
```

The six per-verdict exceptions from §2.5 (CONTRADICTED's double rule, keyline,
strike and shake; SOME CAP's split fill; COULD BE CAP's outline-only sticker; WORD
SALAD's absent rule) are the only `[data-verdict="…"]` selectors allowed in the
codebase. Everything else uses the generic tokens.

## Appendix C — contrast summary

Every text/background pair used in the product, measured. AA requires 4.5:1 for
body text and 3:1 for large text and non-text UI. The lowest value in this system
is 4.13:1, and it is a placeholder, which WCAG classifies as non-essential.

| Pair | Ratio | Passes |
|---|---|---|
| `--text-primary` on `--bg-base` | 17.65 | AAA |
| `--text-primary` on `--bg-raised` | 16.13 | AAA |
| `--text-primary` on `--bg-inset` | 16.90 | AAA |
| `--text-secondary` on `--bg-base` | 8.92 | AAA |
| `--text-secondary` on `--bg-raised` | 8.15 | AAA |
| `--text-tertiary` on `--bg-base` | 5.67 | AA |
| `--text-tertiary` on `--bg-raised` | 5.18 | AA |
| `--accent` on `--bg-base` | 17.32 | AAA |
| `--accent-ink` on `--accent` | 17.76 | AAA |
| `--text-primary` on `--accent-tint` | 11.74 | AAA |
| `--text-primary` on each verdict `-tint` | 13.34 / 14.97 / 13.63 / 13.72 / 13.92 / 14.60 | AAA |
| `--text-primary` on each verdict `-tint-r` | 11.67 / 13.46 / 12.07 / 12.11 / 12.35 / 13.00 | AAA |
| each verdict `-ink` on its `-core` (sticker) | 10.73 / 6.01 / 9.66 / 8.91 / 7.86 / 5.86 | AA (AAA except CONTRADICTED & SALAD) |
| each verdict `-text` on `--bg-base` | 12.11 / 8.80 / 11.70 / 11.61 / 11.07 / 8.21 | AAA |
| each verdict `-text` on its `-prov` (provisional sticker) | 8.74 / 7.26 / 8.63 / 8.68 / 8.40 / 6.56 | AAA |
| each verdict `-core` on its `-prov` (provisional border) | 7.56 / 4.83 / 6.95 / 6.50 / 5.81 / 4.56 | AA / non-text ✓ |
| `--tier-1-fg` on `--tier-1-bg` | 16.67 | AAA |
| `--tier-2-fg` on `--bg-raised` | 9.31 | AAA |
| `--tier-3-fg` on `--bg-raised` | 5.18 | AA |
| `--tier-4-fg` on `--tier-4-bg` | 7.47 | AAA |
| `--conf-fill` on `--bg-base` | 11.07 | AAA |
| `--focus-ring` on `--bg-base` | 17.32 | AAA |
| `--error-text` on `--bg-base` | 8.80 | AAA |
| `--text-tertiary` on `--bg-inset` (placeholder only) | 4.13 | non-essential |
| **Light theme** — `--text-primary` on base / raised / inset | 17.61 / 19.03 / 16.36 | AAA |
| **Light theme** — white on each verdict `-core` | 5.35 / 5.74 / 6.28 / 5.62 / 6.92 / 5.82 | AA |
| **Light theme** — `--text-primary` on each `-tint` | 14.96 / 14.51 / 14.83 / 14.88 / 14.82 / 15.02 | AAA |
| **Light theme** — `--accent-dim` on base | 5.49 | AA |

If you change a colour, re-measure the pair. Ratios were computed with the WCAG 2.1
relative-luminance formula against pre-composited opaque values, not against
`rgba()` guesses.
