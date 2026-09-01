# AnomalEye — Hackathon Presentation Prep

**Format:** 20 min total → **10 min presentation + 10 min Q&A**
**Deck:** `AnomalEye.pptx` — 2 slides (Problem, Solution)

The deck is deliberately light on text so *you* carry the story. Below is a
tight script to hit ~10 minutes, plus the questions a recruiter or technical
reviewer is most likely to ask.

---

## Slide 1 — The Problem (≈3.5 min)

**Open with the stakes, not the tech.**

> "Every bank is legally required to catch money laundering and report it. But
> the true rate is a fraction of a percent, buried in millions of transactions —
> a needle in a haystack. The tools built to find it force an ugly trade-off."

Then walk the three cards:

1. **Rule engines drown analysts.** Legacy transaction-monitoring systems fire
   on up to ~95% false positives. Skilled investigators spend their day closing
   alerts that lead nowhere.
2. **Fixed rules miss the clever schemes.** Structuring, smurfing, layering,
   rapid cash-out — these evolve faster than someone can rewrite thresholds.
3. **A score you can't explain won't fly.** The obvious fix is "throw an AI model
   at it," but a bare risk score isn't defensible. A regulator — and a court —
   needs the evidence behind every flag.

**Land the gap:**

> "So today you pick *flexibility* or *auditability*. Compliance needs both.
> That's the gap AnomalEye closes."

---

## Slide 2 — The Solution (≈4.5 min)

**The one-liner:**

> "You ask a question in plain English, and AnomalEye runs the whole
> investigation — flags the accounts, scores the risk, and explains every
> decision."

**The key design decision (say this slowly — it's the whole pitch):**

> "The LLM decides *what* to analyse — never *what the answer is*. It reads your
> intent and builds a plan. But all the detection math is deterministic: rule
> detectors plus an Isolation Forest, every threshold anchored to real US law —
> the $10,000 CTR reporting line. **The model can pick the tools; it can never
> invent a number.** That's what makes the output reproducible and defensible."

Walk the pipeline strip left→right: question → LLM planner → tools → verdict.

Then the three points:
- **Deterministic core** — auditable, anchored to BSA/FinCEN.
- **Scores and acts** — bands every customer low/medium/high → monitor / review /
  report (SAR).
- **Explains and never goes down** — each flag quotes the exact figures that
  fired it; runs with or without an LLM key (deterministic fallback), so it never
  hard-depends on an external API.

**Close on proof:**

> "This isn't a mockup. 40,000+ transactions across 800 customers, all four
> typologies detected end-to-end, precision/recall/F1 measured against held-out
> ground truth, 41 backend tests, one Docker container — and a live demo you can
> open right now."

If time allows, open the live demo (anomaleye.onrender.com) and type one query,
e.g. *"Find structuring in the last 30 days."* (Warn them the free host may take
~30–50s to wake — start it loading before you present.)

---

## Likely Q&A (prepare these — 10 minutes is a lot)

**"If the LLM can be wrong, why trust the output?"**
> The LLM never produces the verdict. It only chooses which analyses to run. The
> flag, the score, and the reasons all come from deterministic code, so the same
> data always yields the same result — the LLM can't change a number.

**"What if the LLM hallucinates a bad plan?"**
> The plan is sanitised before it runs: `filter` is forced first, detectors always
> pull in classification and explanation, features are ensured before the ML step,
> and ML is stripped from single-entity queries. A partial or hallucinated tool
> list can't produce a broken run. And if the LLM is unreachable, it falls back to
> a deterministic rule-based parser.

**"Is this real data?"**
> No — it's synthetic, generated with deliberately injected laundering typologies
> that are labelled. That's actually a feature: because I hold out the labels, I
> can honestly measure precision/recall/F1. On real data I'd retune thresholds and
> add a supervised layer.

**"How does it scale / is it fast?"**
> The expensive pass (rolling-window features + Isolation Forest on 40k rows) is
> computed once at startup and cached, so a portfolio-wide query drops from ~5s to
> ~0.02s. Filtered queries recompute on their smaller slice so scoped answers are
> never stale.

**"How would you productionise this?"**
> Add authentication and per-analyst case ownership, replace hand-tuned risk
> weights with weights learned from labelled cases, add frontend tests, and wire it
> to a real transaction feed. The architecture already separates a pure-Python
> engine from the API and UI, so those are additive changes.

**"Why Isolation Forest and not a neural net / supervised model?"**
> Unsupervised catches novel anomalies without needing labelled fraud, and it's
> explainable — I can surface which features most exceeded the population. A
> supervised layer is the natural next step once labelled cases exist.

**"What's the hardest part you built?"**
> Making an LLM agent that's genuinely useful but can't compromise auditability —
> the planner/executor split with guard rails, and the caching trade-off that keeps
> broad queries instant while scoped queries stay correct.

**Weaknesses — own them, don't hide them:** synthetic data, no auth on the demo,
hand-tuned weights, no frontend tests yet, free host cold-starts. Naming these
first shows judgment.

---

## Delivery tips
- Pre-warm the live demo before you present (free host sleeps).
- Slide 1 is the "why should I care"; slide 2 is the "why it's hard and why mine
  is different." Spend your energy on the *one* key idea: **plan with the LLM,
  decide with deterministic code.**
- Speaker notes are embedded in each slide (View → Notes / Presenter View).
