"""Session flow: saved-state round-trip, pre-stored delivery, attempt updates state."""
from sqlmodel import Session, SQLModel, create_engine, select

from app.agents import assessor, orchestrator
from app.models import Event, ProblemRecord, Student


def _mem() -> Session:
    eng = create_engine("sqlite://", connect_args={"check_same_thread": False})
    SQLModel.metadata.create_all(eng)
    return Session(eng, expire_on_commit=False)


def _session_row() -> Student:
    return Student(
        id="s", onboarded=True, current_context_id="space",
        current_skill="kinematics", current_difficulty=1,
        skill_vector=assessor.initial_skill_vector(),
    )


def test_saved_state_roundtrips():
    with _mem() as db:
        db.add(_session_row())
        db.commit()
        loaded = db.get(Student, "s")
        assert loaded.onboarded
        assert loaded.current_skill == "kinematics"
        assert loaded.current_context_id == "space"
        assert loaded.current_difficulty == 1


def test_pre_stored_delivers_instantly_and_logs_source():
    with _mem() as db:
        student = _session_row()
        db.add(student)
        db.commit()
        result = orchestrator.fetch_pre_stored(student, "kinematics", 1, context_id="space", session=db)
        assert result.accepted
        assert result.regen_count == 0
        assert result.problem.status == "delivered"
        # delivery logged with source=pre_stored
        deliver = db.exec(select(Event).where(Event.type == "deliver")).all()
        assert deliver and deliver[-1].payload.get("source") == "pre_stored"


def test_attempt_updates_skill_vector():
    with _mem() as db:
        student = _session_row()
        db.add(student)
        db.commit()
        result = orchestrator.fetch_pre_stored(student, "kinematics", 1, session=db)
        before = student.skill_vector["kinematics"]
        # grade a deliberately wrong answer -> mastery drops, state persists
        correct, _ = __import__("app.agents.grader", fromlist=["grade"]).grade(result.problem.task, "-999")
        student.skill_vector = assessor.update_mastery(student.skill_vector, "kinematics", correct)
        db.add(student)
        db.commit()
        assert db.get(Student, "s").skill_vector["kinematics"] != before
