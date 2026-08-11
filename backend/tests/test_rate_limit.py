"""Rate limiting, both directions: inbound HTTP caps and outbound LLM pacing."""
import pytest
from fastapi.testclient import TestClient
from sqlalchemy.pool import StaticPool
from sqlmodel import Session, SQLModel, create_engine

from app.api import routes
from app.config import settings
from app.db import get_session
from app.llm.base import get_provider
from app.main import app
from app.ratelimit import (
    LLMRateLimitError, ProviderThrottle, RateLimiter, Rule, ThrottledProvider,
    limiter, throttle,
)


@pytest.fixture(autouse=True)
def _clean_buckets():
    """Buckets are process-global; a leftover one would leak between tests."""
    limiter.reset()
    throttle.reset()
    yield
    limiter.reset()
    throttle.reset()


class FakeClock:
    """Deterministic time. `sleep` advances it instead of blocking, so a test
    can exercise the wait-for-a-slot path without actually waiting."""

    def __init__(self) -> None:
        self.now = 1000.0

    def time(self) -> float:
        return self.now

    def sleep(self, seconds: float) -> None:
        self.now += seconds


# ---------- the bucket itself ----------

def test_bucket_allows_burst_then_refills_at_the_configured_rate():
    clock = FakeClock()
    rl = RateLimiter(time_fn=clock.time)
    rule = Rule("t", limit=3, window_seconds=60.0)

    assert [rl.check(rule, "ip").allowed for _ in range(3)] == [True, True, True]

    denied = rl.check(rule, "ip")
    assert not denied.allowed
    assert denied.retry_after == pytest.approx(20.0)  # 3/min -> one token per 20s

    clock.now += 20.0
    assert rl.check(rule, "ip").allowed
    assert not rl.check(rule, "ip").allowed

    clock.now += 60.0  # a full idle window restores the whole burst
    assert [rl.check(rule, "ip").allowed for _ in range(3)] == [True, True, True]


def test_buckets_are_isolated_per_client_and_per_rule():
    clock = FakeClock()
    rl = RateLimiter(time_fn=clock.time)
    cheap = Rule("cheap", limit=1)
    costly = Rule("costly", limit=1)

    assert rl.check(cheap, "a").allowed
    assert not rl.check(cheap, "a").allowed
    assert rl.check(cheap, "b").allowed      # a different client is unaffected
    assert rl.check(costly, "a").allowed     # a different class has its own budget


def test_raising_a_limit_applies_to_an_existing_bucket():
    """Capacity is supplied per call, so a bucket created under the old limit
    isn't stuck at it."""
    clock = FakeClock()
    rl = RateLimiter(time_fn=clock.time)

    assert rl.check(Rule("t", limit=1), "ip").allowed
    assert not rl.check(Rule("t", limit=1), "ip").allowed
    clock.now += 60.0
    assert [rl.check(Rule("t", limit=5), "ip").allowed for _ in range(5)] == [True] * 5


# ---------- inbound: user -> backend ----------

@pytest.fixture
def client(monkeypatch):
    """The real app, pointed at a throwaway in-memory database.

    StaticPool is required: FastAPI runs these sync endpoints on a worker
    thread, and SQLite's default pool would hand that thread its own (empty)
    in-memory database. The SSE route reaches for `routes.engine` directly
    rather than the injected session, so that is redirected too. No lifespan
    runs (TestClient only starts one as a context manager), so the on-disk dev
    database is never created.
    """
    eng = create_engine("sqlite://", connect_args={"check_same_thread": False},
                        poolclass=StaticPool)
    SQLModel.metadata.create_all(eng)

    def _session():
        with Session(eng, expire_on_commit=False) as s:
            yield s

    monkeypatch.setattr(routes, "engine", eng)
    app.dependency_overrides[get_session] = _session
    yield TestClient(app)
    app.dependency_overrides.clear()


def test_default_limit_applies_to_every_api_route(client, monkeypatch):
    monkeypatch.setattr(settings, "rate_limit_default_per_minute", 3)

    for _ in range(3):
        assert client.get("/api/skills").status_code == 200

    blocked = client.get("/api/skills")
    assert blocked.status_code == 429
    assert int(blocked.headers["Retry-After"]) >= 1
    assert "rate limit exceeded" in blocked.json()["detail"].lower()


def test_successful_response_reports_the_remaining_budget(client, monkeypatch):
    monkeypatch.setattr(settings, "rate_limit_default_per_minute", 10)
    res = client.get("/api/skills")
    assert res.headers["X-RateLimit-Limit-default"] == "10"
    assert res.headers["X-RateLimit-Remaining-default"] == "9"


def test_auth_routes_are_capped_tighter_than_the_default(client, monkeypatch):
    """Credential guessing is throttled well before the default cap is reached."""
    monkeypatch.setattr(settings, "rate_limit_default_per_minute", 100)
    monkeypatch.setattr(settings, "rate_limit_auth_per_minute", 2)

    body = {"username": "nobody", "password": "guess"}
    assert client.post("/api/auth/login", json=body).status_code == 401  # wrong creds
    assert client.post("/api/auth/login", json=body).status_code == 401
    assert client.post("/api/auth/login", json=body).status_code == 429  # out of guesses

    # The tight auth bucket didn't consume the general budget for other routes.
    assert client.get("/api/skills").status_code == 200


def test_generation_routes_are_capped_tighter_than_the_default(client, monkeypatch):
    monkeypatch.setattr(settings, "rate_limit_default_per_minute", 100)
    monkeypatch.setattr(settings, "rate_limit_generate_per_minute", 1)

    # 404 (unknown session) still spends a token: the cost is in reaching the route.
    assert client.get("/api/students/ghost/next-problem/stream").status_code == 404
    assert client.get("/api/students/ghost/next-problem/stream").status_code == 429


def test_health_is_never_rate_limited(client, monkeypatch):
    monkeypatch.setattr(settings, "rate_limit_default_per_minute", 1)
    for _ in range(5):
        assert client.get("/health").status_code == 200


def test_disabling_the_limiter_lets_everything_through(client, monkeypatch):
    monkeypatch.setattr(settings, "rate_limit_enabled", False)
    monkeypatch.setattr(settings, "rate_limit_default_per_minute", 1)
    for _ in range(5):
        assert client.get("/api/skills").status_code == 200


def test_forwarded_for_is_ignored_unless_trusted(client, monkeypatch):
    """Otherwise a caller mints a fresh bucket per request just by varying a header."""
    monkeypatch.setattr(settings, "rate_limit_default_per_minute", 2)
    monkeypatch.setattr(settings, "rate_limit_trust_forwarded_for", False)

    assert client.get("/api/skills", headers={"X-Forwarded-For": "1.1.1.1"}).status_code == 200
    assert client.get("/api/skills", headers={"X-Forwarded-For": "2.2.2.2"}).status_code == 200
    assert client.get("/api/skills", headers={"X-Forwarded-For": "3.3.3.3"}).status_code == 429

    limiter.reset()
    monkeypatch.setattr(settings, "rate_limit_trust_forwarded_for", True)
    for ip in ("1.1.1.1", "2.2.2.2", "3.3.3.3"):  # now each proxied client is its own
        assert client.get("/api/skills", headers={"X-Forwarded-For": ip}).status_code == 200


# ---------- outbound: backend -> LLM vendor ----------

class FakeProvider:
    name = "fake"

    def __init__(self) -> None:
        self.calls = 0

    def complete(self, prompt: str) -> str:
        self.calls += 1
        return "ok"

    def generate_problem(self, spec):
        self.calls += 1
        return {"spec": spec}


def _throttled(clock: FakeClock, inner=None):
    pacer = ProviderThrottle(time_fn=clock.time, sleep_fn=clock.sleep)
    return ThrottledProvider(inner or FakeProvider(), pacer=pacer)


def test_outbound_calls_wait_for_a_slot_rather_than_failing(monkeypatch):
    monkeypatch.setattr(settings, "llm_rate_limit_per_minute", 2)
    monkeypatch.setattr(settings, "llm_rate_limit_wait_seconds", 60.0)
    clock = FakeClock()
    provider = _throttled(clock)

    provider.complete("a")
    provider.complete("b")
    start = clock.now
    provider.complete("c")  # budget spent -> waits for the bucket to refill

    assert provider._inner.calls == 3
    assert clock.now - start == pytest.approx(30.0)  # 2/min -> a token every 30s


def test_outbound_call_gives_up_when_the_wait_exceeds_the_budget(monkeypatch):
    monkeypatch.setattr(settings, "llm_rate_limit_per_minute", 1)
    monkeypatch.setattr(settings, "llm_rate_limit_wait_seconds", 5.0)
    clock = FakeClock()
    provider = _throttled(clock)

    provider.complete("first")
    with pytest.raises(LLMRateLimitError, match="rate limit of 1/min"):
        provider.complete("second")     # next token is 60s away, budget is 5s
    assert provider._inner.calls == 1   # the vendor was never called


def test_concurrent_outbound_calls_are_capped(monkeypatch):
    monkeypatch.setattr(settings, "llm_max_concurrent_calls", 1)
    monkeypatch.setattr(settings, "llm_rate_limit_wait_seconds", 0.0)
    clock = FakeClock()
    pacer = ProviderThrottle(time_fn=clock.time, sleep_fn=clock.sleep)

    with pacer.slot("fake"):
        with pytest.raises(LLMRateLimitError, match="no free call slot"):
            with pacer.slot("fake"):
                pass
    with pacer.slot("fake"):  # the slot is released again on the way out
        pass


def test_each_provider_gets_its_own_budget(monkeypatch):
    monkeypatch.setattr(settings, "llm_rate_limit_per_minute", 1)
    monkeypatch.setattr(settings, "llm_rate_limit_wait_seconds", 0.0)
    clock = FakeClock()
    pacer = ProviderThrottle(time_fn=clock.time, sleep_fn=clock.sleep)

    with pacer.slot("openai"):
        pass
    with pacer.slot("anthropic"):  # a separate vendor quota
        pass
    with pytest.raises(LLMRateLimitError):
        with pacer.slot("openai"):
            pass


def test_throttling_is_transparent_to_callers(monkeypatch):
    """The wrapper must not change the provider's identity or its exceptions --
    the orchestrator reads `.name` for the event log and maps ValueError to
    json_invalid."""
    monkeypatch.setattr(settings, "llm_rate_limit_per_minute", 60)
    clock = FakeClock()

    class Unparseable(FakeProvider):
        def generate_problem(self, spec):
            raise ValueError("not JSON")

    assert _throttled(clock).name == "fake"
    with pytest.raises(ValueError, match="not JSON"):
        _throttled(clock, Unparseable()).generate_problem(None)


def test_disabling_the_limiter_skips_outbound_pacing(monkeypatch):
    monkeypatch.setattr(settings, "rate_limit_enabled", False)
    monkeypatch.setattr(settings, "llm_rate_limit_per_minute", 1)
    monkeypatch.setattr(settings, "llm_rate_limit_wait_seconds", 0.0)
    clock = FakeClock()
    provider = _throttled(clock)

    for _ in range(5):
        provider.complete("x")
    assert provider._inner.calls == 5


def test_mock_provider_is_not_wrapped():
    """Offline-first: the mock path must stay free of any pacing."""
    assert not isinstance(get_provider("mock"), ThrottledProvider)


def test_semantic_check_is_skipped_when_throttled_not_treated_as_ambiguous(monkeypatch):
    """The clarity check is advisory. Being throttled must not turn into a
    semantic_ambiguity rejection that burns a regeneration."""
    from app.verification import semantic

    class Rater(FakeProvider):
        def complete(self, prompt: str) -> str:
            self.calls += 1
            return '{"ambiguity": 0.1, "feedback": "clear"}'

    monkeypatch.setattr(settings, "llm_provider", "openai")  # take the LLM path
    monkeypatch.setattr(settings, "llm_rate_limit_per_minute", 1)
    monkeypatch.setattr(settings, "llm_rate_limit_wait_seconds", 0.0)
    clock = FakeClock()
    provider = _throttled(clock, Rater())

    assert semantic.verify("Find the derivative of x^2.", provider, use_llm=True).passed
    result = semantic.verify("Find the derivative of x^3.", provider, use_llm=True)
    assert result.passed                      # not a rejection
    assert result.data.get("mode") == "skipped"
