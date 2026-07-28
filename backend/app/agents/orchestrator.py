"""Orchestrator: the closed-loop agent (Section III.B).

Implements observe -> plan -> act -> evaluate with regenerate-until-valid:

  1. Observe telemetry            (read recent attempts/events)
  2. Update student model         (Assessor)
  3. Plan next skill & difficulty (Planner)
  4. Select grounded context      (Context Selector)
  5. Generate structured candidate(Generator / LLM)
  6. Translate JSON -> symbolic   (Translation Layer)
  7. Verify deterministically + semantically (Neuro-Symbolic Verifier)
  8. Accept, or regenerate with an explicit failure reason

Every step appends to the immutable event log.
"""
from __future__ import annotations

import contextvars
import time
from dataclasses import dataclass
from typing import Callable, Optional

from sqlmodel import Session, select

from ..content import problem_bank
from ..content.skills import SKILLS, domain_of, method_of
from ..llm.base import GenerationSpec, LLMProvider
from ..llm.prompt import build_generation_prompt
from ..models import Event, ProblemRecord, Student
from ..schemas.generator import MathTask, PhysicsTask
from ..schemas.verifier import VerifierReport
from ..verification import engine
from . import context_selector, planner


def _task_matches_skill(skill: str, task) -> str | None:
    """Return a mismatch message if the generated task doesn't fit the skill.

    A "limits" skill must yield a math task with kind=limit; a physics skill must
    yield the right template. The LLM occasionally emits the wrong task shape
    (e.g. a physics kinematics task for a limits skill) -- that's a contract
    violation, treated as json_invalid so the loop regenerates.
    """
    method = method_of(skill)
    if method == "physics":
        if not isinstance(task, PhysicsTask):
            return f"skill '{skill}' needs a physics task, got domain '{getattr(task, 'domain', '?')}'"
        expected = SKILLS[skill].get("template")
        if task.template != expected:
            return f"skill '{skill}' needs template '{expected}', got '{task.template}'"
        return None
    if not isinstance(task, MathTask):
        return f"skill '{skill}' needs a math task, got domain '{getattr(task, 'domain', '?')}'"
    if task.kind != method:
        return f"skill '{skill}' needs kind '{method}', got '{task.kind}'"
    return None


@dataclass
class GenerationResult:
    accepted: bool
    problem: Optional[ProblemRecord]
    report: VerifierReport
    regen_count: int
    attempts: list[dict]  # per-attempt failure reasons, for diagnostics


# Current login/browser session id, tagged onto every event (set per request/thread).
_session_ctx: contextvars.ContextVar[Optional[str]] = contextvars.ContextVar("session_id", default=None)


def _log(session: Optional[Session], student_id: str, type_: str, payload: dict) -> None:
    if session is None:
        return
    session.add(Event(student_id=student_id, session_id=_session_ctx.get(),
                      type=type_, payload=payload))
    session.commit()


def _emit(progress: Optional[Callable[[dict], None]], **info) -> None:
    """Report live loop progress, if a callback was supplied (e.g. the CLI)."""
    if progress is not None:
        progress(info)


def _answer_str(task) -> str:
    """A short, human-readable form of a candidate's claimed answer."""
    d = task.model_dump()
    if d.get("domain") == "physics":
        ea = d.get("expected_answer", {})
        return f"{ea.get('value')} {ea.get('unit', '')}".strip()
    return str(d.get("expected_answer", ""))


def generate_next_problem(
    student: Student,
    provider: LLMProvider,
    session: Optional[Session] = None,
    max_regenerations: int = 5,
    progress: Optional[Callable[[dict], None]] = None,
    skill_override: Optional[str] = None,
    difficulty_override: Optional[int] = None,
    session_id: Optional[str] = None,
    log_prompt: bool = False,
) -> GenerationResult:
    _session_ctx.set(session_id)
    # 1-2. Observe + student model (the skill vector is maintained on the Student).
    skill_vector = student.skill_vector or {}
    _log(session, student.id, "observe", {"skill_vector": skill_vector})

    # 3. Plan (skip recently-served skills so a wrong answer doesn't pin us).
    #    Manual overrides (from the demo UI) bypass the planner's choice.
    recent_skills: list[str] = []
    if session is not None:
        recent_skills = list(
            session.exec(
                select(ProblemRecord.skill)
                .where(ProblemRecord.student_id == student.id, ProblemRecord.status == "delivered")
                .order_by(ProblemRecord.id.desc())
                .limit(3)
            ).all()
        )
    planned_skill, planned_difficulty = planner.plan(skill_vector, recent_skills)
    skill = skill_override or planned_skill
    difficulty_target = difficulty_override or planned_difficulty
    _log(session, student.id, "plan",
         {"skill": skill, "difficulty_target": difficulty_target,
          "manual": bool(skill_override or difficulty_override)})

    # 4. Context.
    context = context_selector.select(student.interests or [], skill)
    _log(session, student.id, "context", {"context_id": context.get("id")})

    failure_feedback: list[str] = []
    attempts: list[dict] = []
    last_report = VerifierReport(accepted=False, failure_reasons=["json_invalid"])

    # 5-8. Generate -> verify -> accept/regenerate. Every attempt is written to the
    # event log in full (generate_start -> candidate -> accept | reject) so the
    # entire regeneration trace is reconstructable per user and per session.
    provider_label = getattr(provider, "name", provider.__class__.__name__)
    _emit(progress, status="plan", skill=skill, difficulty_target=difficulty_target)
    for attempt in range(max_regenerations + 1):
        spec = GenerationSpec(skill, difficulty_target, context, failure_feedback)
        feedback_in = list(failure_feedback)  # what we fed back from the prior failure
        prompt = build_generation_prompt(spec)
        # The prompt grows each retry: the previous failure reasons are appended.
        _emit(progress, status="generating", attempt=attempt,
              feedback=feedback_in, prompt=prompt)
        # Logged BEFORE the (potentially slow) model call, so the log shows we're
        # waiting on the LLM rather than hung. `candidate`/`reject` report gen_ms.
        # The full prompt is logged only when explicitly requested (it's large).
        start_payload = {"attempt": attempt, "is_regeneration": attempt > 0, "skill": skill,
                         "difficulty_target": difficulty_target, "context_id": context.get("id"),
                         "provider": provider_label, "feedback_in": feedback_in,
                         "prompt_chars": len(prompt)}
        if log_prompt:
            start_payload["prompt"] = prompt
        _log(session, student.id, "generate_start", start_payload)

        t_gen = time.monotonic()
        try:
            candidate = provider.generate_problem(spec)
        except ValueError as exc:  # invalid/un-parseable JSON
            gen_ms = int((time.monotonic() - t_gen) * 1000)
            failure_feedback = ["json_invalid"]
            attempts.append({"attempt": attempt, "failures": failure_feedback, "detail": str(exc)})
            _log(session, student.id, "reject",
                 {"attempt": attempt, "phase": "parse", "gen_ms": gen_ms, "failure_codes": ["json_invalid"],
                  "failures": [{"code": "json_invalid", "label": "unparseable JSON", "detail": str(exc)}]})
            _emit(progress, status="rejected", attempt=attempt, failures=["json_invalid"], detail=str(exc))
            last_report = VerifierReport(accepted=False, failure_reasons=["json_invalid"])
            continue
        gen_ms = int((time.monotonic() - t_gen) * 1000)

        # Contract check: the task must match the planned skill (else json_invalid).
        mismatch = _task_matches_skill(skill, candidate.task)
        if mismatch:
            failure_feedback = [f"json_invalid ({mismatch})"]
            attempts.append({"attempt": attempt, "failures": ["json_invalid"], "detail": mismatch})
            _log(session, student.id, "reject",
                 {"attempt": attempt, "phase": "contract", "gen_ms": gen_ms, "failure_codes": ["json_invalid"],
                  "failures": [{"code": "json_invalid", "label": "task/skill mismatch", "detail": mismatch}],
                  "statement": candidate.statement})
            _emit(progress, status="rejected", attempt=attempt, failures=["json_invalid"], detail=mismatch)
            last_report = VerifierReport(accepted=False, failure_reasons=["json_invalid"])
            continue

        claimed = _answer_str(candidate.task)
        _log(session, student.id, "candidate",
             {"attempt": attempt, "gen_ms": gen_ms, "statement": candidate.statement,
              "claimed_answer": claimed, "solution": candidate.solution,
              "task": candidate.task.model_dump()})

        # Verification phase (SymPy / physics templates / clarity) -- also timed.
        _log(session, student.id, "verify_start", {"attempt": attempt, "statement": candidate.statement})
        _emit(progress, status="verifying", attempt=attempt, statement=candidate.statement)
        t_ver = time.monotonic()
        report = engine.verify(candidate, provider)
        verify_ms = int((time.monotonic() - t_ver) * 1000)
        last_report = report
        if report.accepted:
            _emit(progress, status="accepted", attempt=attempt,
                  statement=candidate.statement, answer=claimed)
            _log(session, student.id, "accept",
                 {"attempt": attempt, "gen_ms": gen_ms, "verify_ms": verify_ms,
                  "statement": candidate.statement, "claimed_answer": claimed,
                  "difficulty_observed": report.difficulty_observed, "regen_count": attempt})
            problem = ProblemRecord(
                student_id=student.id,
                domain=domain_of(skill).value,
                skill=skill,
                difficulty_target=difficulty_target,
                difficulty_observed=report.difficulty_observed,
                context_id=context.get("id", ""),
                statement=candidate.statement,
                task=candidate.task.model_dump(),
                solution=candidate.solution,
                status="delivered",
                failure_reasons=[],
                regen_count=attempt,
            )
            if session is not None:
                session.add(problem)
                session.commit()
                session.refresh(problem)
            _log(session, student.id, "deliver",
                 {"problem_id": problem.id, "skill": skill, "difficulty_target": difficulty_target,
                  "regen_count": attempt, "source": "llm"})
            return GenerationResult(True, problem, report, attempt, attempts)

        # Feed the SPECIFIC reason back to the model (not just the code) so it can
        # actually fix the issue and converge in fewer attempts.
        explained = engine.explain(report)
        failure_feedback = [f"{e['code']}: {e['detail']}" if e.get("detail") else e["code"]
                            for e in explained]
        attempts.append({"attempt": attempt, "failures": report.failure_reasons})
        _log(session, student.id, "reject",
             {"attempt": attempt, "phase": "verify", "gen_ms": gen_ms, "verify_ms": verify_ms,
              "failure_codes": report.failure_reasons,
              "failures": explained, "statement": candidate.statement,
              "claimed_answer": claimed, "difficulty_observed": report.difficulty_observed})
        _emit(progress, status="rejected", attempt=attempt, failures=report.failure_reasons,
              statement=candidate.statement, answer=claimed,
              details=explained)

    # Exhausted regenerations.
    _emit(progress, status="exhausted", failures=last_report.failure_reasons)
    _log(session, student.id, "exhausted",
         {"attempts": max_regenerations + 1, "failure_codes": last_report.failure_reasons})
    failed = ProblemRecord(
        student_id=student.id,
        domain=domain_of(skill).value,
        skill=skill,
        difficulty_target=difficulty_target,
        context_id=context.get("id", ""),
        status="failed",
        failure_reasons=last_report.failure_reasons,
        regen_count=max_regenerations,
    )
    if session is not None:
        session.add(failed)
        session.commit()
        session.refresh(failed)
    return GenerationResult(False, failed, last_report, max_regenerations, attempts)


def fetch_pre_stored(
    student: Student,
    skill: str,
    difficulty: int,
    context_id: str = "",
    session: Optional[Session] = None,
    provider: Optional[LLMProvider] = None,
    session_id: Optional[str] = None,
) -> GenerationResult:
    """Deliver an already-verified problem from the bank -- instant, no LLM loop.

    Used for onboarding and after a settings change. Falls back to the full LLM
    loop only if the bank has nothing for the skill (so the UI never dead-ends).
    """
    _session_ctx.set(session_id)
    _log(session, student.id, "observe", {"skill_vector": student.skill_vector or {}})
    entry = problem_bank.fetch(skill, difficulty, context_id or None)
    if entry is None:
        if provider is not None:
            return generate_next_problem(student, provider, session=session,
                                         skill_override=skill, difficulty_override=difficulty,
                                         session_id=session_id)
        # No bank entry and no provider: report an empty failure rather than crash.
        return GenerationResult(False, None, VerifierReport(accepted=False), 0, [])

    problem = ProblemRecord(
        student_id=student.id,
        domain=domain_of(skill).value,
        skill=skill,
        difficulty_target=entry["difficulty"],
        difficulty_observed=entry["difficulty"],
        context_id=entry.get("context_id", context_id),
        statement=entry["statement"],
        task=entry["task"],
        solution=entry["solution"],
        status="delivered",
        failure_reasons=[],
        regen_count=0,
    )
    if session is not None:
        session.add(problem)
        session.commit()
        session.refresh(problem)
    _log(session, student.id, "deliver",
         {"problem_id": problem.id, "skill": skill, "difficulty_target": problem.difficulty_target,
          "context_id": problem.context_id, "regen_count": 0, "source": "pre_stored"})
    return GenerationResult(True, problem, VerifierReport(accepted=True), 0, [])
