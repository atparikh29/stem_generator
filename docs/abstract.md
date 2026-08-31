# SCCUR 2026 Abstract

**Regenerate-Until-Valid: A Neuro-Symbolic Agentic Framework for Reliable STEM Problem Generation**

Anay Parikh, Yuki Tanaka, Isabella Chen, Faiza Fatima, Ashna Munavalli · Advisor: Suresh Subramaniam

> Word count: 239 (limit 250). Learning-outcome claims are framed as a *planned*
> pilot protocol — no human data has been collected yet.

---

Intelligent tutoring systems improve STEM learning through mastery-based,
individualized practice—but authoring that practice by hand is labor-intensive and
hard to scale. Large language models can generate it instantly, yet remain
unreliable for exact symbolic and numerical reasoning, producing wrong answers,
inconsistent units, and ill-posed questions where even a 5% error rate risks
teaching incorrect concepts. We present Regenerate-Until-Valid, a
verification-first agentic framework in which the language model proposes but never
judges: it emits each problem as structured JSON, and a deterministic
neuro-symbolic verifier independently re-derives and checks it. SymPy validates
mathematics (equivalence, uniqueness, derivatives, integrals); dimensional-analysis
templates validate 1D, 2D, and rotational physics; and an advisory language-model
check flags only ambiguous wording. Every candidate is accepted or rejected against
a closed taxonomy of six failure codes, and rejected candidates are regenerated with
the explicit failure as feedback in a closed observe–plan–generate–verify loop,
enforcing correctness deterministically rather than predicting it probabilistically.
Across Precalculus, single-variable Calculus, and AP Physics 1 (twenty skills), a
controlled ablation on a local eight-billion-parameter model shows single-shot
generation delivering only 20% valid problems, while the closed loop more than
doubles validity to 47%, intercepting 190 distinct errors—78% mathematically
invalid—that would otherwise reach students. A three-model comparison shows the
loop's benefit grows as the base model weakens, confirming that reliability is
architectural, not a function of scale. Ongoing work includes a within-subject pilot
study estimating learning gains from verified, personalized practice.
