"""HTTP API for the agentic pipeline."""
from __future__ import annotations

import uuid
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlmodel import Session, select

from ..agents import assessor, grader, orchestrator
from ..config import settings
from ..db import get_session
from ..llm.base import get_provider
from ..models import Event, ProblemRecord, Student

router = APIRouter()


# ---------- request/response bodies ----------

class CreateStudent(BaseModel):
    name: str = ""
    interests: list[str] = []
    diagnostic: dict[str, bool] = {}  # skill -> correct


class DiagnosticBody(BaseModel):
    responses: dict[str, bool]


class AttemptBody(BaseModel):
    problem_id: int
    answer: str


# ---------- students ----------

@router.post("/students")
def create_student(body: CreateStudent, session: Session = Depends(get_session)):
    student = Student(
        id=str(uuid.uuid4()),
        name=body.name,
        interests=body.interests,
        skill_vector=assessor.update_from_diagnostic(body.diagnostic)
        if body.diagnostic
        else assessor.initial_skill_vector(),
    )
    student.misconceptions = assessor.infer_misconceptions(student.skill_vector)
    session.add(student)
    session.commit()
    session.refresh(student)
    return student


@router.get("/students/{student_id}")
def get_student(student_id: str, session: Session = Depends(get_session)):
    student = session.get(Student, student_id)
    if not student:
        raise HTTPException(404, "student not found")
    return student


@router.post("/students/{student_id}/diagnostic")
def submit_diagnostic(student_id: str, body: DiagnosticBody, session: Session = Depends(get_session)):
    student = session.get(Student, student_id)
    if not student:
        raise HTTPException(404, "student not found")
    student.skill_vector = assessor.update_from_diagnostic(body.responses)
    student.misconceptions = assessor.infer_misconceptions(student.skill_vector)
    session.add(student)
    session.commit()
    session.refresh(student)
    return student


# ---------- problem generation (the agent loop) ----------

@router.post("/students/{student_id}/next-problem")
def next_problem(student_id: str, session: Session = Depends(get_session)):
    student = session.get(Student, student_id)
    if not student:
        raise HTTPException(404, "student not found")
    result = orchestrator.generate_next_problem(
        student,
        provider=get_provider(),
        session=session,
        max_regenerations=settings.max_regenerations,
    )
    return {
        "accepted": result.accepted,
        "problem": result.problem,
        "report": result.report,
        "regen_count": result.regen_count,
        "attempts": result.attempts,
    }


# ---------- attempts (observe -> update student model) ----------

@router.post("/students/{student_id}/attempts")
def submit_attempt(student_id: str, body: AttemptBody, session: Session = Depends(get_session)):
    student = session.get(Student, student_id)
    if not student:
        raise HTTPException(404, "student not found")
    problem = session.get(ProblemRecord, body.problem_id)
    if not problem or problem.student_id != student_id:
        raise HTTPException(404, "problem not found")

    correct, detail = grader.grade(problem.task, body.answer)
    student.skill_vector = assessor.update_mastery(student.skill_vector, problem.skill, correct)
    student.misconceptions = assessor.infer_misconceptions(student.skill_vector)
    session.add(student)
    session.add(
        Event(
            student_id=student_id,
            type="attempt",
            payload={"problem_id": body.problem_id, "answer": body.answer, "correct": correct},
        )
    )
    session.commit()
    return {"correct": correct, "detail": detail, "skill": problem.skill,
            "new_mastery": student.skill_vector.get(problem.skill)}


# ---------- event log (immutable) ----------

@router.get("/students/{student_id}/events")
def list_events(student_id: str, limit: int = 100, session: Session = Depends(get_session)):
    rows = session.exec(
        select(Event).where(Event.student_id == student_id).order_by(Event.id.desc()).limit(limit)
    ).all()
    return rows
