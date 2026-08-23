# Limitations & Scope (state these proactively at SCCUR)

Pre-empting these in the talk turns "gaps" into deliberate, defensible scoping.

## 1. Physics is a 1D-mechanics proof-of-concept

The AP Physics 1 domain is intentionally scoped to **single-step, one-dimensional
mechanics**. `content/skills.json` currently ships five deterministic templates:

`kinematics`, `newton_friction`, `work_energy`, `impulse_momentum`, `circular_motion`.

**Not yet covered** (honest future work): 2D vectors, inclined planes, torque and
rotational dynamics, and multi-body systems. Each is a real extension — one new
formula template in `verification/physics_verifier.py`, a `skills.json` entry, a
mock builder, and a test (the "Adding a skill" playbook in `CLAUDE.md`). The
architecture supports it; it simply hasn't been built.

> Framing: "The verification *architecture* is domain-general; we validated it on
> a tractable 1D-mechanics slice. Extending the template library is additive, not
> structural."

## 2. The Assessor is an EMA mastery tracer, not BKT/IRT

`agents/assessor.py` updates mastery with a one-parameter exponential moving
average (`assessor_alpha`). It is a lightweight *tracer*, chosen deliberately:
the research contribution is the neuro-symbolic **verifier**, and skill/difficulty
selection only needs a reasonable mastery signal. Bayesian Knowledge Tracing or
Item Response Theory would be a stronger student model and is a clean future
swap (the Assessor interface is isolated behind `update_mastery`).

## 3. Reliability numbers are model-dependent; mock is a pipeline check

The `mock` provider is a correct-by-construction oracle, so it reports ~100%
first-pass validity and zero failures. That validates the *harness*, not the
architecture's benefit. The interesting single-shot-vs-closed-loop gap only
appears with a real model (Llama/GPT/Claude/Gemini) that makes mistakes — always
report the `provider` and treat mock as a smoke test.

## 4. Learning-outcome claims are a designed protocol, not collected data

No human trials have run. See `docs/evaluation_protocol.md`; present the pilot as
planned work with an estimation (not confirmation) goal.

## Roadmap (priority order)

1. Run `experiments/ablation.py` + `experiments/benchmark.py` against a real model
   → real validity/regeneration/failure figures for slides 9–10.
2. Add 2D/rotational physics templates → broaden the physics claim.
3. Optional: BKT/IRT assessor behind the existing interface.
4. Execute the pilot study (IRB + instruments + participants).
