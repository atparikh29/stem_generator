"""HTTP API for the agentic pipeline."""
from __future__ import annotations

import json
import queue
import random
import threading
import uuid
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.encoders import jsonable_encoder
from fastapi.responses import StreamingResponse
from pydantic import BaseModel
from sqlmodel import Session, select

from ..agents import assessor, grader, orchestrator
from ..config import settings
from ..content.skills import SKILLS, all_skills
from ..db import engine, get_session
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


@router.get("/skills")
def list_skills():
    """Skill catalog for the demo UI's dropdown."""
    return [{"id": s, "domain": m["domain"].value, "method": m["method"]} for s, m in SKILLS.items()]


def _resolve_skill(skill: Optional[str]) -> Optional[str]:
    if skill in (None, "", "auto"):
        return None                       # let the Planner choose
    if skill == "random":
        return random.choice(all_skills())
    if skill not in SKILLS:
        raise HTTPException(400, f"unknown skill '{skill}'")
    return skill


@router.get("/students/{student_id}/next-problem/stream")
def next_problem_stream(
    student_id: str,
    provider: Optional[str] = Query(None, description="mock | openai | anthropic (default: .env)"),
    skill: Optional[str] = Query(None, description="a skill id, 'random', or 'auto' (planner)"),
    difficulty: Optional[int] = Query(None, ge=1, le=5),
):
    """Server-Sent Events: stream each loop step (plan, generating, rejected,
    accepted) to the browser so a slow real-model run shows live progress.

    Optional overrides (from the demo UI): provider/model, skill, difficulty.
    The loop runs in a worker thread with its own DB session; progress events
    flow through a thread-safe queue to the SSE generator.
    """
    with Session(engine) as check:
        if not check.get(Student, student_id):
            raise HTTPException(404, "student not found")

    provider_override = None if provider in (None, "", "auto", "default") else provider
    skill_override = _resolve_skill(skill)
    q: "queue.Queue[dict]" = queue.Queue()

    def run() -> None:
        with Session(engine, expire_on_commit=False) as session:
            student = session.get(Student, student_id)

            def progress(ev: dict) -> None:
                # Forward a compact subset (drop the bulky per-attempt prompt).
                q.put({"type": "progress", **{k: ev.get(k) for k in
                       ("status", "attempt", "skill", "difficulty_target",
                        "statement", "answer", "details", "failures", "feedback")}})

            try:
                result = orchestrator.generate_next_problem(
                    student, get_provider(provider_override), session=session,
                    max_regenerations=settings.max_regenerations, progress=progress,
                    skill_override=skill_override, difficulty_override=difficulty,
                )
                q.put({"type": "result", "accepted": result.accepted,
                       "regen_count": result.regen_count,
                       "problem": jsonable_encoder(result.problem)})
            except Exception as exc:  # noqa: BLE001 - surface to the client
                q.put({"type": "error", "message": str(exc)})
            finally:
                q.put({"type": "__end__"})

    threading.Thread(target=run, daemon=True).start()

    def event_stream():
        while True:
            ev = q.get()
            if ev.get("type") == "__end__":
                break
            yield f"data: {json.dumps(ev, default=str)}\n\n"

    return StreamingResponse(
        event_stream(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )


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
