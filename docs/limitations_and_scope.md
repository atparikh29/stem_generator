# Limitations & Scope (state these proactively at SCCUR)

Pre-empting these in the talk turns "gaps" into deliberate, defensible scoping.

## 1. Physics: 1D + 2D + rotational (single-body, single-step)

The AP Physics 1 domain now ships **ten** deterministic templates:

- 1D mechanics: `kinematics`, `newton_friction`, `work_energy`, `impulse_momentum`,
  `circular_motion`
- 2D: `projectile_motion` (range/height/flight-time), `inclined_plane`
  (force decomposition `a = g(sinθ − μcosθ)`)
- Rotational: `torque` (`τ = rF sinθ`), `rotational_kinematics` (`ω = ω₀ + αt`),
  `rotational_dynamics` (`τ = Iα`)

Adding the 2D/rotational templates also **fills physics difficulty bins 4 and 5**,
which the 1D-only set could not reach — physics now spans difficulty 1–5
domain-wide (d1 kinematics/work/impulse, d2 newton/rotational-kinematics,
d3 circular/torque, d4 rotational-dynamics/inclined-plane, d5 projectile).

**Still future work** (honest): multi-body systems (pulleys, collisions between
two bodies), rotational energy/angular-momentum conservation, and genuinely
multi-step problems where a *single* template spans several difficulty bins on its
own. Each is additive via the "Adding a skill" playbook in `CLAUDE.md`.

> Framing: "The verification *architecture* is domain-general; we demonstrate it
> across 1D, 2D, and rotational single-body mechanics. Remaining topics are
> additive template work, not structural changes."

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
