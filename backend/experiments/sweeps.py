"""Detailed multi-sweep runner (one provider per invocation).

Runs the closed loop at the FULL regeneration budget over a deterministic
skill x difficulty grid and logs *every* attempt (round index, skill, domain,
difficulty, failure codes, wall time). One such logged run per provider is
enough to reconstruct, offline, all of:

  1. regeneration-budget curve   validity@b for b = 0..max_regen (b=0 == single-shot)
  3. per-domain / per-skill validity
  4. failure-code trajectory across regeneration rounds
  5. per-difficulty validity
  7. bootstrap / Wilson confidence intervals and seed variance

and, across providers, the cross-model comparison (2) with a frontier anchor (6).

    python -m experiments.sweeps --provider openai --n 120 --max-regen 8 \
        --seed 0 --outdir experiments/results/sweeps_YYYYMMDD

Provider names match get_provider(): mock, openai(=local Llama), gemma, gemini,
deepseek, anthropic. Each problem uses an explicit skill+difficulty override so
the targeted cell is known even when the candidate is ultimately rejected.
Attempts stream to <outdir>/<provider>/attempts.jsonl as they happen, so a run
that is interrupted (rate limit, Ctrl-C) still leaves usable partial data.
"""
from __future__ import annotations

import argparse
import json
import re
import time
from pathlib import Path

from app.agents import assessor, orchestrator
from app.content.skills import all_skills, domain_of
from app.llm.base import get_provider
from app.models import Student

DIFFICULTIES = [1, 2, 3, 4, 5]

# Quota-aware retry policy for rate-limited providers (Gemini free tier, etc.).
# A per-minute 429 is worth waiting out; a per-day 429 is not — backoff can't
# refill a daily cap, so we circuit-break the whole run instead of grinding.
RUNNER_RETRIES = 2          # extra runner-level retries on a per-minute 429
MAX_WAIT_S = 90.0           # cap on how long we honor a retryDelay
DEFAULT_WAIT_S = 30.0       # wait when a per-minute 429 gives no retryDelay
DAILY_BREAK_AFTER = 8       # consecutive unlabeled 429s ⇒ treat as exhausted


class _DailyQuotaExhausted(Exception):
    """Raised to stop a run when the provider's daily quota is spent."""

    def __init__(self, scope: str, quota_id: str | None) -> None:
        super().__init__(f"daily quota exhausted ({quota_id or scope})")
        self.scope = scope
        self.quota_id = quota_id


def _err_blob(exc: Exception) -> str:
    """Best-effort full text of a provider error (message + JSON body + response)."""
    parts = [str(exc)]
    body = getattr(exc, "body", None)
    if body is not None:
        try:
            parts.append(json.dumps(body))
        except Exception:  # noqa: BLE001
            parts.append(str(body))
    resp = getattr(exc, "response", None)
    if resp is not None:
        try:
            parts.append(json.dumps(resp.json()))
        except Exception:  # noqa: BLE001
            parts.append(getattr(resp, "text", "") or "")
    return " ".join(p for p in parts if p)


def classify_quota(exc: Exception) -> tuple[str, float | None, str | None]:
    """Classify a 429 from its structured details.

    Returns (scope, retry_delay_seconds, quota_id) where scope is
    'per_day' | 'per_minute' | 'unknown'. Google's RESOURCE_EXHAUSTED carries a
    QuotaFailure violation whose quotaId names PerDay vs PerMinute, and a
    RetryInfo.retryDelay we honor verbatim.
    """
    blob = _err_blob(exc)
    low = blob.lower()
    scope = "unknown"
    if "perday" in low or "per_day" in low or "requestsperday" in low or "perdayper" in low:
        scope = "per_day"
    elif "perminute" in low or "per_minute" in low or "requestsperminute" in low:
        scope = "per_minute"
    m = re.search(r'retrydelay["\s:]+(\d+(?:\.\d+)?)s', low)
    retry_delay = float(m.group(1)) if m else None
    qm = re.search(r'"quotaId"\s*:\s*"([^"]+)"', blob)
    return scope, retry_delay, (qm.group(1) if qm else None)


def _grid(seed: int) -> list[tuple[str, int]]:
    """All (skill, difficulty) cells in DIFFICULTY-MAJOR (round-robin) order.

    Every skill appears once at difficulty 1 before any appears at 2, so a
    partial run of n < full still covers all skills (and both domains) — a
    skill-major order would spend the first ~45 cells entirely on math and never
    reach physics. Rotated by seed for varied sampling order.
    """
    skills = all_skills()
    cells = [(skills[i % len(skills)], DIFFICULTIES[(i // len(skills)) % len(DIFFICULTIES)])
             for i in range(len(skills) * len(DIFFICULTIES))]
    off = seed % len(cells)
    return cells[off:] + cells[:off]


def run(provider_name: str, n: int, max_regen: int, seed: int, outdir: Path,
        use_semantic: bool = True) -> dict:
    provider = get_provider(provider_name)
    prov_dir = outdir / provider_name
    prov_dir.mkdir(parents=True, exist_ok=True)
    log_path = prov_dir / "attempts.jsonl"
    logf = log_path.open("w")

    cells = _grid(seed)
    skills = all_skills()
    delivered = first_pass = usable = errors = 0
    consecutive_429 = 0
    circuit_broken: dict | None = None
    t0 = time.time()

    for i in range(n):
        skill, difficulty = cells[i % len(cells)]
        domain = domain_of(skill)
        # Skill vector is irrelevant here (we override the plan), but the loop
        # still reads it; make the targeted skill the weak one for realism.
        student = Student(id=f"sweep-{i}", interests=["sports", "space"],
                          skill_vector={k: (0.0 if k == skill else 0.85) for k in skills})
        print(f"  [{provider_name}] {i + 1}/{n}  {skill}@{difficulty} … ",
              end="", flush=True)
        rec: dict = {"i": i, "skill": skill, "domain": domain, "difficulty": difficulty}
        p0 = time.time()

        # Quota-aware call: honor a per-minute retryDelay (wait then retry), but
        # stop the whole run on a per-day cap — backoff can't refill it.
        result = None
        last_exc: Exception | None = None
        try:
            for tryno in range(RUNNER_RETRIES + 1):
                try:
                    result = orchestrator.generate_next_problem(
                        student, provider, session=None, max_regenerations=max_regen,
                        skill_override=skill, difficulty_override=difficulty,
                        use_llm_semantic=use_semantic,
                    )
                    consecutive_429 = 0
                    break
                except Exception as exc:  # noqa: BLE001
                    last_exc = exc
                    if type(exc).__name__ != "RateLimitError":
                        break  # a non-quota infra error: record and move on
                    consecutive_429 += 1
                    scope, retry_delay, quota_id = classify_quota(exc)
                    if scope == "per_day" or consecutive_429 >= DAILY_BREAK_AFTER:
                        raise _DailyQuotaExhausted(
                            scope if scope != "unknown" else "sustained", quota_id)
                    if tryno < RUNNER_RETRIES:
                        wait = min(retry_delay or DEFAULT_WAIT_S, MAX_WAIT_S)
                        print(f"⏳ per-minute 429, waiting {wait:.0f}s "
                              f"(retry {tryno + 1}/{RUNNER_RETRIES}) … ", end="", flush=True)
                        time.sleep(wait)
        except _DailyQuotaExhausted as q:
            circuit_broken = {"scope": q.scope, "quota_id": q.quota_id, "at_problem": i}
            (prov_dir / "quota_exhausted.json").write_text(json.dumps(circuit_broken, indent=2))
            print(f"\n⛔ {q} — circuit-breaking at {i}/{n}; backoff cannot refill a "
                  "daily cap. Enable API billing or resume after reset.", flush=True)
            break

        if result is None:  # non-quota error, or per-minute retries exhausted
            errors += 1
            scope, retry_delay, quota_id = classify_quota(last_exc) if last_exc else ("unknown", None, None)
            rec.update({"error": type(last_exc).__name__ if last_exc else "Unknown",
                        "detail": _err_blob(last_exc)[:1000] if last_exc else "",
                        "quota_scope": scope, "quota_id": quota_id, "retry_delay_s": retry_delay,
                        "wall_ms": round((time.time() - p0) * 1000)})
            logf.write(json.dumps(rec) + "\n"); logf.flush()
            print(f"⚠ error ({rec['error']})", flush=True)
            continue

        usable += 1
        # Per-round failure codes: attempts[r]["failures"] holds the codes that
        # sent round r back for regeneration (empty on the accepted round).
        rounds = [{"round": a.get("attempt", r), "failures": list(a.get("failures", []))}
                  for r, a in enumerate(result.attempts)]
        rec.update({
            "accepted": bool(result.accepted),
            "regen_count": result.regen_count,        # 0 == accepted first pass
            "n_attempts": len(result.attempts),
            "rounds": rounds,
            "final_failures": list(result.report.failure_reasons) if not result.accepted else [],
            "wall_ms": round((time.time() - p0) * 1000),
        })
        logf.write(json.dumps(rec) + "\n"); logf.flush()
        if result.accepted:
            delivered += 1
            if result.regen_count == 0:
                first_pass += 1
            print(f"✓ regen {result.regen_count}", flush=True)
        else:
            print(f"✗ [{','.join(result.report.failure_reasons) or '-'}]", flush=True)

    logf.close()
    attempted = usable + errors  # problems actually reached (short of n if circuit-broken)
    summary = {
        "provider": provider_name, "n": n, "max_regen": max_regen, "seed": seed,
        "total_requests": attempted, "requested_n": n, "errors": errors, "usable": usable,
        "delivered": delivered, "first_pass": first_pass,
        "first_pass_validity": round(first_pass / usable, 4) if usable else 0.0,
        "post_loop_validity": round(delivered / usable, 4) if usable else 0.0,
        "wall_seconds": round(time.time() - t0, 1),
        "attempts_log": str(log_path),
        "circuit_broken": circuit_broken,  # None, or {scope, quota_id, at_problem}
    }
    summary["use_semantic"] = use_semantic
    (prov_dir / "summary.json").write_text(json.dumps(summary, indent=2))
    print(f"\n[{provider_name}] usable={usable} first-pass={summary['first_pass_validity']:.0%} "
          f"post-loop={summary['post_loop_validity']:.0%} errors={errors} "
          f"in {summary['wall_seconds']}s -> {prov_dir}")
    return summary


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--provider", required=True)
    ap.add_argument("--n", type=int, default=120)
    ap.add_argument("--max-regen", type=int, default=8)
    ap.add_argument("--seed", type=int, default=0)
    ap.add_argument("--outdir", required=True)
    ap.add_argument("--no-semantic", action="store_true",
                    help="skip the advisory LLM clarity check (halves API calls per problem)")
    args = ap.parse_args()
    run(args.provider, args.n, args.max_regen, args.seed, Path(args.outdir),
        use_semantic=not args.no_semantic)


if __name__ == "__main__":
    main()
