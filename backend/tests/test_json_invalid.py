"""json_invalid behavior.

`json_invalid` means the generator's output failed Pydantic validation against
GeneratorOutput (not JSON, broken JSON, missing fields, or out-of-range values).
It is decided in `llm/prompt.parse_generator_output` and handled by the
orchestrator, which logs it and regenerates. The mock provider never triggers it
(it builds valid objects directly), so we use small faulty providers here.
"""
import pytest
from sqlmodel import Session, SQLModel, create_engine, select

from app.agents import assessor, orchestrator
from app.llm.base import GenerationSpec
from app.llm.mock import MockProvider
from app.llm.prompt import parse_generator_output
from app.models import Event, Student


@pytest.mark.parametrize(
    "raw",
    [
        "Sure! Here is your problem.",                       # not JSON
        '{"skill": "limits", "difficulty_target":',          # truncated
        '{"skill": "limits"}',                               # missing required fields
        # valid JSON but difficulty_target out of the 1..5 range
        '{"skill":"limits","difficulty_target":9,"statement":"x","solution":"x",'
        '"task":{"domain":"math","kind":"limit","expression":"x","expected_answer":"0"}}',
    ],
)
def test_parse_rejects_malformed_output(raw):
    with pytest.raises(ValueError):
        parse_generator_output(raw)


def _memory_session() -> Session:
    engine = create_engine("sqlite://", connect_args={"check_same_thread": False})
    SQLModel.metadata.create_all(engine)
    return Session(engine)


class _FlakyProvider:
    """Emits malformed JSON (raises like the real parser) for the first N
    attempts, then delegates to the mock."""

    name = "flaky"

    def __init__(self, fail_first: int):
        self._fail_first = fail_first
        self._mock = MockProvider()
        self._calls = 0

    def complete(self, prompt):
        return self._mock.complete(prompt)

    def generate_problem(self, spec: GenerationSpec):
        self._calls += 1
        if self._calls <= self._fail_first:
            raise ValueError("invalid generator JSON: model returned prose, not an object")
        return self._mock.generate_problem(spec)


def _student():
    return Student(id="s", interests=["space"], skill_vector=assessor.initial_skill_vector())


def test_loop_logs_json_invalid_then_recovers():
    with _memory_session() as session:
        student = _student()
        session.add(student)
        session.commit()

        result = orchestrator.generate_next_problem(
            student, _FlakyProvider(fail_first=2), session=session, max_regenerations=5
        )

        # Recovered after the two bad attempts.
        assert result.accepted
        assert result.regen_count == 2
        assert [a["failures"] for a in result.attempts] == [["json_invalid"], ["json_invalid"]]

        # Recorded in the immutable event log.
        fails = session.exec(select(Event).where(Event.type == "fail")).all()
        assert len(fails) == 2
        assert all(e.payload["reason"] == "json_invalid" for e in fails)


def test_loop_reports_json_invalid_when_budget_exhausted():
    with _memory_session() as session:
        student = _student()
        session.add(student)
        session.commit()

        # Always fails -> never recovers within the budget.
        result = orchestrator.generate_next_problem(
            student, _FlakyProvider(fail_first=99), session=session, max_regenerations=3
        )

        assert not result.accepted
        assert result.report.failure_reasons == ["json_invalid"]
        assert result.problem.status == "failed"
