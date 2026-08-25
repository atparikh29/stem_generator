"""The SSE generation stream: it should emit progress events then a final result,
and 404 for an unknown session. Runs on the offline mock provider."""
import json

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.pool import StaticPool
from sqlmodel import Session, SQLModel, create_engine

from app.api import routes
from app.db import get_session
from app.main import app


@pytest.fixture
def client(monkeypatch):
    # Throwaway in-memory DB. StaticPool shares the one connection across the
    # worker thread the SSE loop runs on; the stream route uses routes.engine
    # directly, so redirect that too.
    eng = create_engine("sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool)
    SQLModel.metadata.create_all(eng)

    def _session():
        with Session(eng, expire_on_commit=False) as s:
            yield s

    monkeypatch.setattr(routes, "engine", eng)
    app.dependency_overrides[get_session] = _session
    yield TestClient(app)
    app.dependency_overrides.clear()


def _events(text: str) -> list[dict]:
    return [json.loads(line[6:]) for line in text.splitlines() if line.startswith("data: ")]


def test_stream_emits_progress_then_accepted_result(client):
    sid = client.post("/api/sessions", json={"skill": "derivative_rules", "difficulty": 3, "model": "mock"}).json()["id"]
    r = client.get(f"/api/sessions/{sid}/next-problem/stream?skill=derivative_rules&difficulty=3")
    assert r.status_code == 200

    evs = _events(r.text)
    types = [e["type"] for e in evs]
    assert "progress" in types           # live loop steps were streamed
    assert types[-1] == "result"         # the stream ends with a verdict
    result = evs[-1]
    assert result["accepted"] is True
    assert result["problem"]["skill"] == "derivative_rules"


def test_stream_unknown_session_returns_404(client):
    r = client.get("/api/sessions/does-not-exist/next-problem/stream")
    assert r.status_code == 404
