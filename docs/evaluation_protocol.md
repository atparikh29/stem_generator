# Evaluation Protocol & Pilot Study Design

**Status: DESIGN / PLANNED — no human data has been collected yet.**

This document reframes the Slide 4 contribution *"a within-subject pilot study
establishing feasibility and engagement while estimating effect sizes"* as a
**pre-registered evaluation protocol**. Present it as planned work. Do **not**
claim completed trials or report effect sizes until this study has actually run
(see the SCCUR review's "Defense Warning").

## 1. Research questions

- **RQ1 (Reliability, answered in code):** Does the closed loop raise delivered-problem
  validity over single-shot generation? → measured by `experiments/ablation.py`
  (first-pass vs post-loop validity). This is empirical *now*, model-dependent.
- **RQ2 (Learning, this protocol):** Does practice on verified, personalized problems
  improve short-term learning gains vs a generic/unverified baseline?
- **RQ3 (Engagement, this protocol):** Do students report higher engagement with
  interest-personalized contexts (context varied, skill/difficulty held fixed)?

## 2. Design

- **Within-subject**, counterbalanced. Each participant experiences both the
  personalized and the generic-context arm across matched skill sets, order
  counterbalanced to control for practice/fatigue effects.
- The **skill and difficulty are held identical** across arms (personalization
  changes context only — a core invariant of the system), so any difference is
  attributable to context, not content.

## 3. Participants & power

- Target **n = 20–30** undergraduates in a precalculus/calculus/AP-Physics course.
- This is explicitly a **feasibility pilot**: powered to *estimate* an effect size
  (Cohen's *d* with a confidence interval), not to confirm one. Report the CI, and
  use it to power a future confirmatory study.

## 4. Instruments & metrics

| Construct | Instrument | Metric |
|---|---|---|
| Learning gain | Isomorphic pre-test / post-test per skill | Normalized gain ⟨g⟩, paired *t* / Wilcoxon, Cohen's *d* + 95% CI |
| Engagement | Short Likert survey + on-task time | Mean rating; time-on-task from the event log |
| System reliability | Automatic, from the event log | First-pass & post-loop validity, mean regenerations, failure mix |

The event log already records everything needed for the reliability and
time-on-task metrics per user and per session (`GET /students/{id}/stats`,
`/events`).

## 5. Procedure

1. Consent + brief diagnostic (seeds the skill vector).
2. Pre-test (isomorphic items).
3. Practice block A, then block B (arms counterbalanced).
4. Post-test (isomorphic items) + engagement survey.
5. Export per-participant event log for analysis.

## 6. Threats to validity

- **Oracle/model confound:** reliability numbers depend on the generating model —
  always report which (`provider` column). Mock is an oracle (~100%) and is a
  pipeline check, not a result.
- **Isomorphic-item drift:** pre/post items must be verified-equivalent (use the
  same verifier to confirm matched difficulty).
- **Small n:** pilot estimates only; pre-register the confirmatory study.

## 7. What exists today vs what this needs

- **Exists:** the full pipeline, the reliability ablation (`experiments/`), the
  per-user/per-session logging and stats needed to compute every automatic metric.
- **Needed:** IRB/consent, the pre/post instruments, and human participants.
