# SCCUR 2026 Abstract — v2 (updated with the full sweep results)

**Regenerate-Until-Valid: A Neuro-Symbolic Agentic Framework for Reliable STEM Problem Generation**

Anay Parikh, Yuki Tanaka, Isabella Chen, Faiza Fatima, Ashna Munavalli · Advisor: Suresh Subramaniam

> Numbers reflect the August 2026 sweep on the corrected generation prompts:
> Llama 3.1 8B and Gemini 3.6 Flash at n=95 (nineteen skills × five levels),
> Gemma 4 at n=40 (difficulty-balanced). Learning-outcome claims are a *planned*
> pilot protocol — no human data collected yet.

---

Intelligent tutoring systems improve STEM learning through mastery-based,
individualized practice—but authoring that practice by hand is labor-intensive and
hard to scale. Large language models can generate it instantly, yet remain
unreliable for exact symbolic and numerical reasoning, producing wrong answers,
inconsistent units, and ill-posed questions where a 5% error rate risks teaching
incorrect concepts. We present Regenerate-Until-Valid, a
verification-first agentic framework in which the language model proposes but never
judges: it emits each problem as structured JSON, and a deterministic
neuro-symbolic verifier independently re-derives and checks it. SymPy validates
mathematics (equivalence, uniqueness, derivatives, integrals); dimensional-analysis
templates validate 1D, 2D, and rotational physics; and an advisory language-model
check flags only ambiguous wording. Every candidate is accepted or rejected against
a closed taxonomy of six failure codes, and rejected candidates are regenerated with
the explicit failure as feedback in a closed observe–plan–generate–verify loop.
Across Precalculus, single-variable Calculus, and AP Physics 1 (nineteen skills), a
controlled ablation on a local eight-billion-parameter model (n=95) shows
single-shot generation delivering only 21% valid problems while the closed loop
lifts validity to 43%, intercepting 518 errors, 73% mathematically invalid. The
loop helps symbolic mathematics (24%→58%) more than physics (18%→30%), where
failures are genuine arithmetic errors the verifier catches. Across three models
the relative benefit is largest for the weakest (2.0×, 1.6×, 1.1×) while validity
rises 43%→82%→91% and physics tracks base-model competence (30%→70%→82%),
confirming reliability is architectural, not a function of scale. Ongoing work
estimates learning gains from verified, personalized practice.
