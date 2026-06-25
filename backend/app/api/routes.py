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


class CreateSession(BaseModel):
    name: str = ""
    context_id: str = "generic"
    skill: str = ""
    difficulty: int = 0
    model: str = ""
    interests: list[str] = []
    diagnostic: dict[str, bool] = {}


class SettingsBody(BaseModel):
    context_id: Optional[str] = None
    skill: Optional[str] = None
    difficulty: Optional[int] = None
    model: Optional[str] = None


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


def _problem_stream(student_id: str, provider_override: Optional[str],
                    skill_override: Optional[str], difficulty: Optional[int]) -> StreamingResponse:
    """SSE: run the LLM generate->verify->regenerate loop in a worker thread and
    stream each step (plan, generating, rejected, accepted) to the browser."""
    with Session(engine) as check:
        if not check.get(Student, student_id):
            raise HTTPException(404, "session not found")

    q: "queue.Queue[dict]" = queue.Queue()

    def run() -> None:
        with Session(engine, expire_on_commit=False) as session:
            student = session.get(Student, student_id)

            def progress(ev: dict) -> None:
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


@router.get("/students/{student_id}/next-problem/stream")
def next_problem_stream(
    student_id: str,
    provider: Optional[str] = Query(None),
    skill: Optional[str] = Query(None),
    difficulty: Optional[int] = Query(None, ge=1, le=5),
):
    provider_override = None if provider in (None, "", "auto", "default") else provider
    return _problem_stream(student_id, provider_override, _resolve_skill(skill), difficulty)


# ---------- attempts (observe -> assessor -> save state) ----------

def _grade_and_record(student_id: str, body: AttemptBody, session: Session) -> dict:
    student = session.get(Student, student_id)
    if not student:
        raise HTTPException(404, "session not found")
    problem = session.get(ProblemRecord, body.problem_id)
    if not problem or problem.student_id != student_id:
        raise HTTPException(404, "problem not found")

    correct, detail = grader.grade(problem.task, body.answer)
    # Observe -> Assessor -> Save State (skill vector persisted on the session row).
    student.skill_vector = assessor.update_mastery(student.skill_vector, problem.skill, correct)
    student.misconceptions = assessor.infer_misconceptions(student.skill_vector)
    session.add(student)
    session.add(Event(student_id=student_id, type="attempt",
                      payload={"problem_id": body.problem_id, "answer": body.answer, "correct": correct}))
    session.commit()
    return {"correct": correct, "detail": detail, "skill": problem.skill,
            "new_mastery": student.skill_vector.get(problem.skill)}


@router.post("/students/{student_id}/attempts")
def submit_attempt(student_id: str, body: AttemptBody, session: Session = Depends(get_session)):
    return _grade_and_record(student_id, body, session)


# ---------- event log (immutable) ----------

@router.get("/students/{student_id}/events")
def list_events(student_id: str, limit: int = 100, session: Session = Depends(get_session)):
    rows = session.exec(
        select(Event).where(Event.student_id == student_id).order_by(Event.id.desc()).limit(limit)
    ).all()
    return rows


# ---------- sessions (the new flowchart surface) ----------

@router.get("/contexts")
def list_contexts():
    """Curated context library for the onboarding context picker."""
    from ..agents.context_selector import _library

    return _library()


@router.post("/sessions")
def create_session(body: CreateSession, session: Session = Depends(get_session)):
    """Initial onboarding: create a session with chosen context/skill/difficulty."""
    student = Student(
        id=str(uuid.uuid4()),
        name=body.name,
        interests=body.interests,
        skill_vector=assessor.update_from_diagnostic(body.diagnostic)
        if body.diagnostic else assessor.initial_skill_vector(),
        onboarded=True,
        current_context_id=body.context_id or "generic",
        current_skill=body.skill,
        current_difficulty=body.difficulty,
        current_model=body.model,
    )
    student.misconceptions = assessor.infer_misconceptions(student.skill_vector)
    session.add(student)
    session.add(Event(student_id=student.id, type="onboard",
                      payload={"context_id": body.context_id, "skill": body.skill,
                               "difficulty": body.difficulty, "model": body.model}))
    session.commit()
    session.refresh(student)
    return student


@router.get("/sessions/{session_id}")
def get_session_state(session_id: str, session: Session = Depends(get_session)):
    """Returning-session branch: saved state for the frontend to restore."""
    student = session.get(Student, session_id)
    if not student:
        raise HTTPException(404, "session not found")
    return student


@router.post("/sessions/{session_id}/settings")
def adjust_settings(session_id: str, body: SettingsBody, session: Session = Depends(get_session)):
    """Adjust Settings (startup or midway): update saved context/skill/difficulty/model."""
    student = session.get(Student, session_id)
    if not student:
        raise HTTPException(404, "session not found")
    if body.context_id is not None:
        student.current_context_id = body.context_id
    if body.skill is not None:
        student.current_skill = body.skill
    if body.difficulty is not None:
        student.current_difficulty = body.difficulty
    if body.model is not None:
        student.current_model = body.model
    session.add(student)
    session.add(Event(student_id=session_id, type="adjust_settings",
                      payload={"context_id": student.current_context_id, "skill": student.current_skill,
                               "difficulty": student.current_difficulty, "model": student.current_model}))
    session.commit()
    session.refresh(student)
    return student


@router.get("/sessions/{session_id}/pre-stored")
def fetch_pre_stored(
    session_id: str,
    skill: Optional[str] = Query(None),
    difficulty: Optional[int] = Query(None, ge=1, le=5),
    context: Optional[str] = Query(None),
    session: Session = Depends(get_session),
):
    """Fetch a pre-stored, already-verified problem -- instant, no LLM loop."""
    student = session.get(Student, session_id)
    if not student:
        raise HTTPException(404, "session not found")
    use_skill = _resolve_skill(skill) or student.current_skill or random.choice(all_skills())
    use_diff = difficulty or student.current_difficulty or 1
    use_ctx = context or student.current_context_id
    provider = get_provider(student.current_model or None)
    result = orchestrator.fetch_pre_stored(
        student, use_skill, use_diff, context_id=use_ctx, session=session, provider=provider)
    return {"accepted": result.accepted, "problem": result.problem,
            "regen_count": result.regen_count, "source": "pre_stored"}


@router.get("/sessions/{session_id}/next-problem/stream")
def session_next_problem_stream(session_id: str, session: Session = Depends(get_session)):
    """Continue (no settings change): the Planner picks; stream the LLM loop."""
    student = session.get(Student, session_id)
    if not student:
        raise HTTPException(404, "session not found")
    # Planner chooses skill & difficulty -> no override here.
    return _problem_stream(session_id, student.current_model or None, None, None)


@router.post("/sessions/{session_id}/attempts")
def session_attempt(session_id: str, body: AttemptBody, session: Session = Depends(get_session)):
    return _grade_and_record(session_id, body, session)
