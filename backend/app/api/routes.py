"""HTTP API for the agentic pipeline."""
from __future__ import annotations

import json
import queue
import random
import threading
import uuid
from datetime import datetime, timedelta, timezone
from typing import Optional

from fastapi import APIRouter, Depends, Header, HTTPException, Query
from fastapi.encoders import jsonable_encoder
from fastapi.responses import StreamingResponse
from pydantic import BaseModel
from sqlmodel import Session, select

from ..agents import assessor, grader, orchestrator
from ..auth import hash_password, new_reset_token, verify_password
from ..config import settings
from ..content import problem_bank
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


class RegisterBody(BaseModel):
    username: str
    password: str
    name: str = ""
    context_id: str = "generic"
    skill: str = ""
    difficulty: int = 0
    model: str = ""


class LoginBody(BaseModel):
    username: str
    password: str


class ForgotBody(BaseModel):
    username: str


class ResetBody(BaseModel):
    username: str
    token: str
    new_password: str


RESET_TOKEN_TTL_MINUTES = 30


class UiEventBody(BaseModel):
    action: str
    detail: dict = {}


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
    """Skill catalog for the UI, with the difficulties available per skill in the
    pre-stored bank (so the difficulty menu can be clamped to what exists)."""
    avail: dict[str, set] = {}
    for p in problem_bank.load():
        avail.setdefault(p["skill"], set()).add(p["difficulty"])
    return [{"id": s, "domain": m["domain"].value, "method": m["method"],
             "difficulties": sorted(avail.get(s)) or [1, 2, 3, 4, 5]}
            for s, m in SKILLS.items()]


def _resolve_skill(skill: Optional[str]) -> Optional[str]:
    if skill in (None, "", "auto"):
        return None                       # let the Planner choose
    if skill == "random":
        return random.choice(all_skills())
    if skill not in SKILLS:
        raise HTTPException(400, f"unknown skill '{skill}'")
    return skill


def _problem_stream(student_id: str, provider_override: Optional[str],
                    skill_override: Optional[str], difficulty: Optional[int],
                    session_id: Optional[str] = None,
                    log_prompt: bool = False,
                    semantic_llm: Optional[bool] = None) -> StreamingResponse:
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
                        "statement", "answer", "details", "failures", "feedback", "step")}})

            use_sem = settings.semantic_llm_check if semantic_llm is None else semantic_llm
            try:
                result = orchestrator.generate_next_problem(
                    student, get_provider(provider_override), session=session,
                    max_regenerations=settings.max_regenerations, progress=progress,
                    skill_override=skill_override, difficulty_override=difficulty,
                    session_id=session_id, log_prompt=log_prompt, use_llm_semantic=use_sem,
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
    session_id: Optional[str] = Query(None),  # EventSource can't set headers
    log_prompt: bool = Query(False),
    semantic_llm: Optional[bool] = Query(None),
):
    provider_override = None if provider in (None, "", "auto", "default") else provider
    return _problem_stream(student_id, provider_override, _resolve_skill(skill), difficulty,
                           session_id, log_prompt, semantic_llm)


# ---------- attempts (observe -> assessor -> save state) ----------

def _grade_and_record(student_id: str, body: AttemptBody, session: Session,
                      session_id: Optional[str] = None) -> dict:
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
    session.add(Event(student_id=student_id, session_id=session_id, type="attempt",
                      payload={"problem_id": body.problem_id, "answer": body.answer, "correct": correct,
                               "skill": problem.skill, "new_mastery": student.skill_vector.get(problem.skill)}))
    session.commit()
    return {"correct": correct, "detail": detail, "skill": problem.skill,
            "new_mastery": student.skill_vector.get(problem.skill)}


@router.post("/students/{student_id}/attempts")
def submit_attempt(student_id: str, body: AttemptBody, session: Session = Depends(get_session),
                   x_session_id: Optional[str] = Header(None)):
    return _grade_and_record(student_id, body, session, x_session_id)


# ---------- event log (immutable, comprehensive) ----------

@router.post("/students/{student_id}/ui-events")
def log_ui_event(student_id: str, body: UiEventBody, session: Session = Depends(get_session),
                 x_session_id: Optional[str] = Header(None)):
    """Record a front-end GUI action (button click, settings change, etc.) into the
    same append-only log, tagged with the user and the login session."""
    if not session.get(Student, student_id):
        raise HTTPException(404, "session not found")
    session.add(Event(student_id=student_id, session_id=x_session_id, type="ui",
                      payload={"action": body.action, **body.detail}))
    session.commit()
    return {"ok": True}


@router.get("/students/{student_id}/events")
def list_events(student_id: str, limit: int = 500, session_id: Optional[str] = Query(None),
                session: Session = Depends(get_session)):
    """Full structured log for a USER. Pass ?session_id=… to scope to one session."""
    q = select(Event).where(Event.student_id == student_id)
    if session_id:
        q = q.where(Event.session_id == session_id)
    rows = session.exec(q.order_by(Event.id.desc()).limit(limit)).all()
    return rows


# ---------- auth (username / password) ----------

@router.post("/auth/register")
def register(body: RegisterBody, session: Session = Depends(get_session)):
    """Create an account + its session. Password is stored only as a PBKDF2 hash."""
    username = body.username.strip()
    if not username or not body.password:
        raise HTTPException(400, "username and password are required")
    if session.exec(select(Student).where(Student.username == username)).first():
        raise HTTPException(409, "username already taken")
    student = Student(
        id=str(uuid.uuid4()),
        name=body.name,
        username=username,
        password_hash=hash_password(body.password),
        skill_vector=assessor.initial_skill_vector(),
        onboarded=True,
        current_context_id=body.context_id or "generic",
        current_skill=body.skill,
        current_difficulty=body.difficulty,
        current_model=body.model,
    )
    student.misconceptions = assessor.infer_misconceptions(student.skill_vector)
    sid = str(uuid.uuid4())
    session.add(student)
    session.add(Event(student_id=student.id, session_id=sid, type="register", payload={"username": username}))
    session.commit()
    session.refresh(student)
    return {**jsonable_encoder(student), "session_id": sid}


@router.post("/auth/login")
def login(body: LoginBody, session: Session = Depends(get_session)):
    """Verify credentials, start a new session, and return it (to resume saved state)."""
    student = session.exec(select(Student).where(Student.username == body.username.strip())).first()
    if not student or not verify_password(body.password, student.password_hash):
        raise HTTPException(401, "invalid username or password")
    sid = str(uuid.uuid4())
    session.add(Event(student_id=student.id, session_id=sid, type="login", payload={"username": student.username}))
    session.commit()
    return {**jsonable_encoder(student), "session_id": sid}


@router.post("/auth/forgot-password")
def forgot_password(body: ForgotBody, session: Session = Depends(get_session)):
    """Issue a short-lived reset token.

    This offline app has no mail server, so the token is returned directly
    (dev delivery) instead of emailed. Only the token's hash is stored. The
    response is generic whether or not the account exists (no user enumeration);
    the token is included only when it was actually issued.
    """
    resp = {"ok": True, "message": "If that account exists, a reset token has been issued."}
    student = session.exec(select(Student).where(Student.username == body.username.strip())).first()
    if not student:
        return resp
    token = new_reset_token()
    student.reset_token_hash = hash_password(token)
    student.reset_expires_at = datetime.now(timezone.utc) + timedelta(minutes=RESET_TOKEN_TTL_MINUTES)
    session.add(student)
    session.add(Event(student_id=student.id, type="forgot_password", payload={"username": student.username}))
    session.commit()
    resp.update({
        "reset_token": token,  # dev delivery: would be emailed in production
        "expires_in_minutes": RESET_TOKEN_TTL_MINUTES,
        "dev_note": "No mail server in this app — token returned directly instead of emailed.",
    })
    return resp


@router.post("/auth/reset-password")
def reset_password(body: ResetBody, session: Session = Depends(get_session)):
    """Consume a valid, unexpired reset token and set a new password.

    On success the token is cleared and a new login session is returned so the
    user is signed in immediately (same shape as /auth/login)."""
    if not body.new_password:
        raise HTTPException(400, "new password is required")
    student = session.exec(select(Student).where(Student.username == body.username.strip())).first()
    if not student or not student.reset_token_hash or not student.reset_expires_at \
            or not verify_password(body.token, student.reset_token_hash):
        raise HTTPException(400, "invalid or expired reset token")
    # SQLite may hand the datetime back tz-naive; treat stored times as UTC.
    exp = student.reset_expires_at
    if exp.tzinfo is None:
        exp = exp.replace(tzinfo=timezone.utc)
    if exp < datetime.now(timezone.utc):
        raise HTTPException(400, "invalid or expired reset token")

    student.password_hash = hash_password(body.new_password)
    student.reset_token_hash = None
    student.reset_expires_at = None
    sid = str(uuid.uuid4())
    session.add(student)
    session.add(Event(student_id=student.id, session_id=sid, type="password_reset",
                      payload={"username": student.username}))
    session.commit()
    session.refresh(student)
    return {**jsonable_encoder(student), "session_id": sid}


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
    sid = str(uuid.uuid4())
    session.add(student)
    session.add(Event(student_id=student.id, session_id=sid, type="onboard",
                      payload={"context_id": body.context_id, "skill": body.skill,
                               "difficulty": body.difficulty, "model": body.model}))
    session.commit()
    session.refresh(student)
    return {**jsonable_encoder(student), "session_id": sid}


@router.get("/sessions/{session_id}")
def get_session_state(session_id: str, session: Session = Depends(get_session)):
    """Returning-session branch: saved state for the frontend to restore.
    NB: the path {session_id} is the USER/account id."""
    student = session.get(Student, session_id)
    if not student:
        raise HTTPException(404, "session not found")
    return student


@router.post("/sessions/{session_id}/settings")
def adjust_settings(session_id: str, body: SettingsBody, session: Session = Depends(get_session),
                    x_session_id: Optional[str] = Header(None)):
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
    session.add(Event(student_id=session_id, session_id=x_session_id, type="adjust_settings",
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
    x_session_id: Optional[str] = Header(None),
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
        student, use_skill, use_diff, context_id=use_ctx, session=session, provider=provider,
        session_id=x_session_id)
    return {"accepted": result.accepted, "problem": result.problem,
            "regen_count": result.regen_count, "source": "pre_stored"}


@router.get("/sessions/{session_id}/next-problem/stream")
def session_next_problem_stream(
    session_id: str,
    skill: Optional[str] = Query(None),
    difficulty: Optional[int] = Query(None, ge=1, le=5),
    sid: Optional[str] = Query(None),  # login-session id (EventSource can't set headers)
    log_prompt: bool = Query(False),
    semantic_llm: Optional[bool] = Query(None),
    session: Session = Depends(get_session),
):
    """Stream the LLM loop with the session's model.

    With skill/difficulty query params -> generate at those settings (keeps the
    user's choice). Without -> the Planner picks (adaptive).
    """
    student = session.get(Student, session_id)
    if not student:
        raise HTTPException(404, "session not found")
    return _problem_stream(session_id, student.current_model or None, _resolve_skill(skill),
                           difficulty, sid, log_prompt, semantic_llm)


@router.post("/sessions/{session_id}/attempts")
def session_attempt(session_id: str, body: AttemptBody, session: Session = Depends(get_session),
                    x_session_id: Optional[str] = Header(None)):
    return _grade_and_record(session_id, body, session, x_session_id)
