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
from typing import Optional

from sqlmodel import Session

from ..content.skills import domain_of
from ..llm.base import GenerationSpec, LLMProvider
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


def generate_next_problem(
    student: Student,
    provider: LLMProvider,
    session: Optional[Session] = None,
    max_regenerations: int = 5,
) -> GenerationResult:
    # 1-2. Observe + student model (the skill vector is maintained on the Student).
    skill_vector = student.skill_vector or {}
    _log(session, student.id, "observe", {"skill_vector": skill_vector})

    # 3. Plan.
    skill, difficulty_target = planner.plan(skill_vector)
    _log(session, student.id, "plan", {"skill": skill, "difficulty_target": difficulty_target})

    # 4. Context.
    context = context_selector.select(student.interests or [], skill)
    _log(session, student.id, "context", {"context_id": context.get("id")})

    failure_feedback: list[str] = []
    attempts: list[dict] = []
    last_report = VerifierReport(accepted=False, failure_reasons=["json_invalid"])

    # 5-8. Generate -> verify -> accept/regenerate.
    for attempt in range(max_regenerations + 1):
        spec = GenerationSpec(skill, difficulty_target, context, failure_feedback)
        try:
            candidate = provider.generate_problem(spec)
        except ValueError as exc:  # invalid/un-parseable JSON
            failure_feedback = ["json_invalid"]
            attempts.append({"attempt": attempt, "failures": failure_feedback, "detail": str(exc)})
            _log(session, student.id, "fail", {"attempt": attempt, "reason": "json_invalid", "detail": str(exc)})
            last_report = VerifierReport(accepted=False, failure_reasons=["json_invalid"])
            continue

        _log(session, student.id, "generate", {"attempt": attempt, "statement": candidate.statement})

        report = engine.verify(candidate, provider)
        last_report = report
        if report.accepted:
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

    # Exhausted regenerations.
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
