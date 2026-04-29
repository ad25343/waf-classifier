# Reusable Pitch Deck Prompt

Use this prompt to generate a leadership-grade capabilities deck for any internal product. It encodes the structure, design system, and copy rules used to produce `WAF_Classifier_Capabilities.pptx` (`make_deck.py`).

---

## How to use

1. Replace the **{PROJECT}** placeholders with details about the product you're pitching.
2. Paste the prompt into a Claude Code session that has read access to the codebase.
3. Claude will generate `make_deck.py` and run it to produce a `.pptx` in `static/` (or wherever you specify).

---

## The Prompt

```
Generate a leadership capabilities deck for {PROJECT_NAME} as a python-pptx
script (`make_deck.py`) plus the rendered .pptx. Run the script after writing
it so the deck is ready to open.

═══════════════════════════════════════════════════════════════════════════
1. SOURCE OF TRUTH
═══════════════════════════════════════════════════════════════════════════
Every claim in the deck must be grounded in the actual codebase. Before
writing copy:
  - Inventory the routes / blueprints / modules and count capabilities per
    module.
  - Grep for every LLM / AI call site and note which endpoint each lives in.
  - Confirm each capability is exposed in the UI (don't list dead endpoints).
Do NOT invent features. Do NOT round up counts. If a number appears in the
subtitle ("X of Y capabilities use AI"), the bars and the supporting list
must sum to the same X.

═══════════════════════════════════════════════════════════════════════════
2. STRUCTURE — 5 main + 1 divider + N appendix
═══════════════════════════════════════════════════════════════════════════
Main deck (5 slides — what leadership reads in the room):
  1. Title / Why + What       — one-line problem, one-line product
  2. The Problem               — 3–4 pain bullets, status-quo cost
  3. Modules at a Glance       — one card per module (3×N grid)
  4. What Leadership Gets      — 4 outcome chips + 6 decision-grade items
  5. Where AI Is Used          — governance slide: subtitle "X of Y use AI",
                                 horizontal bar per module showing AI/Total,
                                 right-side list of every AI call site

Appendix (1 divider + one slide per module):
  6. Appendix divider — mini-index A1…AN with module names
  7…N. One slide per module — capability cards (3-col or 3+2 grid),
       short verbs, no marketing fluff

Footer on every slide: "Slide X of TOTAL  ·  {PROJECT_NAME}"
TOTAL = 5 + 1 + (number of modules).

═══════════════════════════════════════════════════════════════════════════
3. DESIGN SYSTEM (light theme, executive-friendly)
═══════════════════════════════════════════════════════════════════════════
Slide size: 13.333 × 7.5 inches (16:9 widescreen).

Palette (RGB):
  BG          = (248, 250, 252)   slide background
  CARD        = (255, 255, 255)   card fill
  BORDER      = (226, 232, 240)   card stroke
  INK         = ( 15,  23,  42)   primary text
  MUTED       = (100, 116, 139)   secondary text
  ACCENT      = ( 37,  99, 235)   primary accent (blue)
  ACCENT_SOFT = (219, 234, 254)   accent fill for chips/bars
  GREEN       = ( 22, 163,  74)   "good" / outcome chip
  AMBER       = (217, 119,   6)   "watch" / mismatch
  RED         = (220,  38,  38)   "stop" / disputed

Typography:
  Title       — 32pt, bold, INK
  Eyebrow     — 11pt, ACCENT, uppercase, tracked
  Subtitle    — 14pt, MUTED
  Card title  — 13pt, semibold
  Card body   — 9–9.5pt, MUTED
  Footer      — 9pt, MUTED

Helpers to define in `make_deck.py`:
  new_slide(), rect(), rrect() (rounded rectangle),
  txt(), footer(sl, cur), slide_eyebrow(), slide_title(),
  slide_sub(), divider(), badge(), cap_card()

═══════════════════════════════════════════════════════════════════════════
4. COPY RULES
═══════════════════════════════════════════════════════════════════════════
  - No marketing adjectives (no "powerful", "seamless", "robust").
  - Verbs first on capability cards: "Classify a story", "Score readiness".
  - Numbers in copy must match what the code actually does.
  - Avoid "AI-powered" as a label — say what the AI does ("LLM scores DoR").
  - Outcome chips are one word: Aligned · Trusted · Consistent · Actionable
    (or project-specific equivalents).
  - Slide 4 lists 6 decision-grade items leadership gains visibility into.

═══════════════════════════════════════════════════════════════════════════
5. SLIDE 5 — THE GOVERNANCE SLIDE (most-scrutinised)
═══════════════════════════════════════════════════════════════════════════
This is the slide leadership will count. It MUST tie out:

  Subtitle:     "X of Y capabilities invoke the LLM"
  Left side:    one horizontal bar per module — fill width = AI count,
                track width = total count. Label: "Module — AI/Total"
  Right side:   one row per AI call site, with the route/file path,
                a one-line description, and the user-visible feature
                that triggers it.

Internal consistency check before saving:
  sum(bar fills) == X
  count(rows on right) == X
  subtitle X == both of the above

═══════════════════════════════════════════════════════════════════════════
6. APPENDIX MODULE SLIDES
═══════════════════════════════════════════════════════════════════════════
Each module slide has:
  - Eyebrow: "APPENDIX · A{n}"
  - Title: module name
  - Subtitle: one line — "{count} capabilities" + what the module is for
  - Capability cards in a 3-col grid (or 3+2 for 5 capabilities):
      card title (verb-led), one-line body
  - No screenshots, no logos, no clip art

═══════════════════════════════════════════════════════════════════════════
7. VERIFICATION CHECKLIST (run before declaring done)
═══════════════════════════════════════════════════════════════════════════
  [ ] Every capability card maps to a real route/handler/UI element
  [ ] Slide 5 subtitle == bar sum == AI calls list length
  [ ] Footer slide numbers go 1…TOTAL with no gaps
  [ ] Appendix mini-index A1…AN matches actual appendix slide order
  [ ] No placeholder text, no TODOs, no Lorem ipsum
  [ ] File saved to a stable path; size > 50KB (sanity check)
  [ ] Open in Keynote/PowerPoint and skim — nothing overflows the canvas

═══════════════════════════════════════════════════════════════════════════
8. DELIVERABLES
═══════════════════════════════════════════════════════════════════════════
  - `make_deck.py` (idempotent — re-runs produce the same deck)
  - `{PROJECT_NAME}_Capabilities.pptx` (or path you specify)
  - A short summary to the user: slide count, AI-call count,
    where the file lives.

═══════════════════════════════════════════════════════════════════════════
PROJECT-SPECIFIC INPUTS (fill these in before running the prompt)
═══════════════════════════════════════════════════════════════════════════
  PROJECT_NAME       : {e.g. "Foo Classifier"}
  ONE-LINE PROBLEM   : {what's broken today, in plain English}
  ONE-LINE PRODUCT   : {what this tool does, in one sentence}
  MODULES            : {list of modules / blueprints to feature}
  OUTCOME CHIPS      : {4 one-word outcomes for slide 4}
  DECISION ITEMS     : {6 things leadership gains visibility into}
  CODEBASE PATH      : {repo root so Claude can ground its claims}
  OUTPUT PATH        : {where to write the .pptx}
```

---

## Tips

- **Ground first, design second.** The biggest failure mode is inventing capabilities. Start every deck by counting routes and AI call sites in code.
- **Slide 5 is the trust slide.** If the numbers don't tie, leadership will stop reading. Verify the subtitle ↔ bars ↔ list triangle before saving.
- **5 main slides is the limit.** If a section feels essential but doesn't fit, push it to the appendix and reference the appendix slide number from the main deck.
- **Re-run idempotency matters.** When you iterate on copy, the script should produce the same deck — no random IDs, no timestamps in filenames.
