"""Persistence models.

The `Event` table is an append-only, immutable event log: every observation,
generation attempt, verification result, and delivery is recorded as one row and
never updated or deleted. `Student` and `ProblemRecord` are convenience
projections derived from that log for fast reads.
"""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Optional

from sqlalchemy import Column
from sqlalchemy.types import JSON
from sqlmodel import Field, SQLModel


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


class Event(SQLModel, table=True):
    """Immutable append-only log entry. Never mutated after insert."""

    __tablename__ = "events"

    id: Optional[int] = Field(default=None, primary_key=True)
    ts: datetime = Field(default_factory=_utcnow, index=True)
    student_id: str = Field(index=True)
    type: str = Field(index=True)  # e.g. observe, plan, generate, verify, deliver, fail
    payload: dict[str, Any] = Field(default_factory=dict, sa_column=Column(JSON))


class Student(SQLModel, table=True):
    """A learner session. Identified by `id` (stored in the browser for returning
    sessions). Carries the saved state the flowchart restores on return."""

    __tablename__ = "students"

    id: str = Field(primary_key=True)
    name: str = ""
    # skill -> mastery in [0, 1]
    skill_vector: dict[str, float] = Field(default_factory=dict, sa_column=Column(JSON))
    misconceptions: list[str] = Field(default_factory=list, sa_column=Column(JSON))
    interests: list[str] = Field(default_factory=list, sa_column=Column(JSON))
    # Saved session state (restored for returning sessions; set at onboarding /
    # adjusted via settings changes).
    onboarded: bool = False
    current_context_id: str = ""
    current_skill: str = ""
    current_difficulty: int = 0
    current_model: str = ""
    created_at: datetime = Field(default_factory=_utcnow)


class ProblemRecord(SQLModel, table=True):
    __tablename__ = "problems"

    id: Optional[int] = Field(default=None, primary_key=True)
    student_id: str = Field(index=True)
    domain: str = ""
    skill: str = ""
    difficulty_target: int = 0
    difficulty_observed: Optional[int] = None
    context_id: str = ""
    statement: str = ""
    task: dict[str, Any] = Field(default_factory=dict, sa_column=Column(JSON))
    solution: str = ""
    status: str = "pending"  # delivered | failed
    failure_reasons: list[str] = Field(default_factory=list, sa_column=Column(JSON))
    regen_count: int = 0
    created_at: datetime = Field(default_factory=_utcnow)
