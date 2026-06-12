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

from dataclasses import dataclass
from typing import Callable, Optional

from sqlmodel import Session, select

from ..content.skills import domain_of
from ..llm.base import GenerationSpec, LLMProvider
from ..llm.prompt import build_generation_prompt
from ..models import Event, ProblemRecord, Student
from ..schemas.verifier import VerifierReport
from ..verification import engine
from . import context_selector, planner


@dataclass
class GenerationResult:
    accepted: bool
    problem: Optional[ProblemRecord]
    report: VerifierReport
    regen_count: int
    attempts: list[dict]  # per-attempt failure reasons, for diagnostics


def _log(session: Optional[Session], student_id: str, type_: str, payload: dict) -> None:
    if session is None:
        return
    session.add(Event(student_id=student_id, type=type_, payload=payload))
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
) -> GenerationResult:
    # 1-2. Observe + student model (the skill vector is maintained on the Student).
    skill_vector = student.skill_vector or {}
    _log(session, student.id, "observe", {"skill_vector": skill_vector})

    # 3. Plan (skip recently-served skills so a wrong answer doesn't pin us).
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
    skill, difficulty_target = planner.plan(skill_vector, recent_skills)
    _log(session, student.id, "plan", {"skill": skill, "difficulty_target": difficulty_target})

    # 4. Context.
    context = context_selector.select(student.interests or [], skill)
    _log(session, student.id, "context", {"context_id": context.get("id")})

    failure_feedback: list[str] = []
    attempts: list[dict] = []
    last_report = VerifierReport(accepted=False, failure_reasons=["json_invalid"])

    # 5-8. Generate -> verify -> accept/regenerate.
    _emit(progress, status="plan", skill=skill, difficulty_target=difficulty_target)
    for attempt in range(max_regenerations + 1):
        spec = GenerationSpec(skill, difficulty_target, context, failure_feedback)
        # The prompt grows each retry: the previous failure reasons are appended.
        _emit(progress, status="generating", attempt=attempt,
              feedback=list(failure_feedback), prompt=build_generation_prompt(spec))
        try:
            candidate = provider.generate_problem(spec)
        except ValueError as exc:  # invalid/un-parseable JSON
            failure_feedback = ["json_invalid"]
            attempts.append({"attempt": attempt, "failures": failure_feedback, "detail": str(exc)})
            _log(session, student.id, "fail", {"attempt": attempt, "reason": "json_invalid", "detail": str(exc)})
            _emit(progress, status="rejected", attempt=attempt, failures=["json_invalid"], detail=str(exc))
            last_report = VerifierReport(accepted=False, failure_reasons=["json_invalid"])
            continue

        _log(session, student.id, "generate", {"attempt": attempt, "statement": candidate.statement})

        report = engine.verify(candidate, provider)
        last_report = report
        if report.accepted:
            _emit(progress, status="accepted", attempt=attempt,
                  statement=candidate.statement, answer=_answer_str(candidate.task))
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
            _log(session, student.id, "deliver", {"problem_id": problem.id, "skill": skill, "regen_count": attempt})
            return GenerationResult(True, problem, report, attempt, attempts)

        failure_feedback = report.failure_reasons
        attempts.append({"attempt": attempt, "failures": failure_feedback})
        _log(session, student.id, "fail", {"attempt": attempt, "reasons": failure_feedback})
        # Per-failure, human-readable explanations (includes the verifier's own
        # computed answer inside the math_invalid detail).
        _emit(progress, status="rejected", attempt=attempt, failures=failure_feedback,
              statement=candidate.statement, answer=_answer_str(candidate.task),
              details=engine.explain(report))

    # Exhausted regenerations.
    _emit(progress, status="exhausted", failures=last_report.failure_reasons)
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
