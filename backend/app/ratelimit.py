"""Rate limiting in both directions, over one shared mechanism (a token bucket).

* **Inbound** (user -> backend): a FastAPI dependency caps how often one client
  may call the API. Buckets are keyed by client IP *and* route class, so a burst
  of cheap telemetry can't starve the budget for an expensive generation. The
  `default` class is attached to every ``/api`` route; `auth` and `generate` are
  attached on top of it where the route deserves a tighter cap.

* **Outbound** (backend -> LLM vendor): `ThrottledProvider` paces every provider
  call so the regenerate-until-valid loop stays inside vendor quotas. One
  request can fire up to ``2 * (max_regenerations + 1)`` provider calls, so the
  inbound cap alone doesn't bound vendor traffic. The `mock` provider is never
  wrapped -- the offline pipeline and the test suite are unaffected.

A token bucket (rather than a fixed window) means a user who has been idle can
still act immediately, while sustained traffic converges on the configured rate.
Limits are read from `settings` on every call, so raising one takes effect
without a restart of the limiter's state.

**Scope:** buckets live in this process's memory. That is correct for the single
uvicorn worker this project runs; under multiple workers or replicas each gets
its own buckets and the effective limit multiplies. A shared store (Redis) is
the fix, and `RateLimiter` is the seam to put it behind.
"""
from __future__ import annotations

import math
import threading
import time
from collections.abc import Iterator
from contextlib import contextmanager
from dataclasses import dataclass
from typing import Callable, Optional

from fastapi import HTTPException, Request, Response

from .config import settings

# Stop the bucket table from growing without bound as IPs churn. Well above any
# plausible concurrent-client count, so a prune never evicts an active bucket.
_MAX_BUCKETS = 4096


class RateLimitExceeded(HTTPException):
    """HTTP 429 with a Retry-After header."""

    def __init__(self, rule: "Rule", retry_after: float) -> None:
        seconds = max(1, math.ceil(retry_after))
        super().__init__(
            status_code=429,
            detail=(f"Rate limit exceeded ({rule.limit} requests per "
                    f"{int(rule.window_seconds)}s for '{rule.name}'). "
                    f"Retry in {seconds}s."),
            headers={"Retry-After": str(seconds)},
        )
        self.rule = rule
        self.retry_after = float(retry_after)


class LLMRateLimitError(RuntimeError):
    """An outbound provider call could not get a slot within the wait budget.

    Deliberately *not* a ValueError: the orchestrator treats ValueError as
    `json_invalid` and would burn a regeneration on it. This propagates instead,
    so the caller reports throttling rather than a bad candidate.
    """


@dataclass(frozen=True)
class Rule:
    """A limit of `limit` events per `window_seconds`."""

    name: str
    limit: int
    window_seconds: float = 60.0

    @property
    def refill_per_second(self) -> float:
        return self.limit / self.window_seconds if self.window_seconds > 0 else 0.0


@dataclass
class Decision:
    allowed: bool
    remaining: int
    retry_after: float  # seconds until the next token; 0.0 when allowed


class TokenBucket:
    """Capacity and refill rate are passed in per call rather than stored, so a
    changed limit applies to existing buckets instead of being frozen at the
    value that happened to be live when the bucket was first created.

    Not thread-safe on its own; `RateLimiter` owns the lock.
    """

    __slots__ = ("tokens", "updated")

    def __init__(self, now: float, capacity: float) -> None:
        self.tokens = capacity
        self.updated = now

    def take(self, now: float, capacity: float, refill_per_second: float,
             amount: float = 1.0) -> tuple[bool, float]:
        """Spend `amount` tokens if available. Returns (allowed, retry_after)."""
        self.tokens = min(capacity, self.tokens + max(0.0, now - self.updated) * refill_per_second)
        self.updated = now
        if self.tokens >= amount:
            self.tokens -= amount
            return True, 0.0
        if refill_per_second <= 0:
            return False, float("inf")
        return False, (amount - self.tokens) / refill_per_second


class RateLimiter:
    """Thread-safe collection of token buckets, keyed by (rule name, client)."""

    def __init__(self, time_fn: Callable[[], float] = time.monotonic) -> None:
        self._time = time_fn
        self._lock = threading.Lock()
        self._buckets: dict[tuple[str, str], TokenBucket] = {}

    def check(self, rule: Rule, key: str) -> Decision:
        """Spend one token from (rule, key), reporting whether it was there."""
        capacity = float(rule.limit)
        now = self._time()
        with self._lock:
            if len(self._buckets) >= _MAX_BUCKETS:
                self._prune(now, rule.window_seconds)
            bucket = self._buckets.get((rule.name, key))
            if bucket is None:
                bucket = TokenBucket(now, capacity)
                self._buckets[(rule.name, key)] = bucket
            allowed, retry_after = bucket.take(now, capacity, rule.refill_per_second)
            return Decision(allowed, int(bucket.tokens), retry_after)

    def _prune(self, now: float, window_seconds: float) -> None:
        """Bound the bucket table. Caller holds the lock.

        A bucket untouched for a full window has necessarily refilled to
        capacity, so dropping it is equivalent to keeping it -- and it can't be
        used to escape a limit. If that frees nothing (a genuinely large client
        population, or forged X-Forwarded-For values), evict the least recently
        used half: those are the closest to full, so they forfeit the least.
        """
        for bucket_key, bucket in list(self._buckets.items()):
            if now - bucket.updated >= window_seconds:
                del self._buckets[bucket_key]
        if len(self._buckets) < _MAX_BUCKETS:
            return
        by_age = sorted(self._buckets, key=lambda k: self._buckets[k].updated)
        for bucket_key in by_age[: len(by_age) // 2]:
            del self._buckets[bucket_key]

    def reset(self) -> None:
        with self._lock:
            self._buckets.clear()


# ---------- inbound: user -> backend ----------

limiter = RateLimiter()

_RULE_SETTINGS = {
    "default": "rate_limit_default_per_minute",
    "auth": "rate_limit_auth_per_minute",
    "generate": "rate_limit_generate_per_minute",
}


def rule_for(name: str) -> Rule:
    """Build a Rule from current settings, so limits are re-read per request."""
    try:
        field = _RULE_SETTINGS[name]
    except KeyError:
        raise ValueError(f"unknown rate limit class '{name}'") from None
    return Rule(name=name, limit=int(getattr(settings, field)), window_seconds=60.0)


def client_key(request: Request) -> str:
    """Identify the caller. The socket peer by default; the left-most
    X-Forwarded-For entry only when the deployment says a trusted proxy sets it
    (otherwise a caller could rotate the header to get a fresh bucket each time).
    """
    if settings.rate_limit_trust_forwarded_for:
        forwarded = request.headers.get("x-forwarded-for", "")
        if forwarded.strip():
            return forwarded.split(",")[0].strip()
    return request.client.host if request.client else "unknown"


def limit(rule_name: str) -> Callable[[Request, Response], None]:
    """Dependency factory: ``dependencies=[Depends(limit("auth"))]``.

    Applied as a route/router dependency rather than a parameter, so endpoint
    signatures stay clean and tests that call the endpoint functions directly
    are unaffected.
    """

    def dependency(request: Request, response: Response) -> None:
        if not settings.rate_limit_enabled:
            return
        rule = rule_for(rule_name)
        decision = limiter.check(rule, client_key(request))
        if not decision.allowed:
            raise RateLimitExceeded(rule, decision.retry_after)
        # Informational; absent on endpoints that return a Response directly
        # (the SSE stream), which FastAPI passes through untouched.
        response.headers[f"X-RateLimit-Limit-{rule.name}"] = str(rule.limit)
        response.headers[f"X-RateLimit-Remaining-{rule.name}"] = str(decision.remaining)

    return dependency


# ---------- outbound: backend -> LLM vendor ----------

class ProviderThrottle:
    """Paces outbound calls to each LLM vendor.

    Two independent bounds, because they catch different failure modes: a
    requests-per-minute bucket for sustained rate, and a semaphore for how many
    calls may be in flight at once (each SSE generation runs in its own thread,
    so without it N simultaneous users burst straight past the vendor's limit).

    Callers wait for a slot rather than failing immediately -- a short wait is
    much better than a lost generation -- but the wait is bounded by
    `llm_rate_limit_wait_seconds`.
    """

    def __init__(self, time_fn: Callable[[], float] = time.monotonic,
                 sleep_fn: Callable[[float], None] = time.sleep) -> None:
        self._time = time_fn
        self._sleep = sleep_fn
        self._lock = threading.Lock()
        self._buckets: dict[str, TokenBucket] = {}
        self._semaphores: dict[str, threading.BoundedSemaphore] = {}

    def _semaphore(self, provider: str) -> threading.BoundedSemaphore:
        with self._lock:
            sem = self._semaphores.get(provider)
            if sem is None:
                sem = threading.BoundedSemaphore(max(1, int(settings.llm_max_concurrent_calls)))
                self._semaphores[provider] = sem
            return sem

    def _take_token(self, provider: str, capacity: float, refill: float) -> tuple[bool, float]:
        now = self._time()
        with self._lock:
            bucket = self._buckets.get(provider)
            if bucket is None:
                bucket = TokenBucket(now, capacity)
                self._buckets[provider] = bucket
            return bucket.take(now, capacity, refill)

    @contextmanager
    def slot(self, provider: str) -> Iterator[None]:
        """Hold a concurrency slot and one rate token for the duration of a call.

        The slot is taken first and held while waiting for a token, so the
        concurrency cap bounds waiting threads as well as active calls. That is
        the point: under load we want to shed requests, not accumulate threads
        parked on a bucket that is refilling slowly.
        """
        if not settings.rate_limit_enabled:
            yield
            return

        rule = Rule(name=provider, limit=int(settings.llm_rate_limit_per_minute))
        budget = float(settings.llm_rate_limit_wait_seconds)
        deadline = self._time() + budget
        concurrent = max(1, int(settings.llm_max_concurrent_calls))

        sem = self._semaphore(provider)
        if not sem.acquire(timeout=max(0.0, deadline - self._time())):
            raise LLMRateLimitError(
                f"{provider}: no free call slot within {budget:g}s "
                f"({concurrent} concurrent calls allowed)")
        try:
            while True:
                allowed, retry_after = self._take_token(provider, float(rule.limit),
                                                        rule.refill_per_second)
                if allowed:
                    break
                remaining = deadline - self._time()
                if retry_after > remaining:
                    raise LLMRateLimitError(
                        f"{provider}: local rate limit of {rule.limit}/min reached; "
                        f"a slot needs {retry_after:.1f}s but the wait budget is {budget:g}s")
                self._sleep(max(0.0, min(retry_after, remaining)))
            yield
        finally:
            sem.release()

    def reset(self) -> None:
        with self._lock:
            self._buckets.clear()
            self._semaphores.clear()


throttle = ProviderThrottle()


class ThrottledProvider:
    """Wraps an LLMProvider so both of its calls pass through `throttle`.

    Attribute access falls through to the wrapped provider, so `name` (used as
    the provider label in the event log) and anything added later behave as if
    the wrapper weren't there.
    """

    def __init__(self, inner, pacer: Optional[ProviderThrottle] = None) -> None:
        self._inner = inner
        self._throttle = pacer if pacer is not None else throttle

    def __getattr__(self, item: str):
        return getattr(self._inner, item)

    @property
    def name(self) -> str:
        return getattr(self._inner, "name", self._inner.__class__.__name__)

    def complete(self, prompt: str) -> str:
        with self._throttle.slot(self.name):
            return self._inner.complete(prompt)

    def generate_problem(self, spec):
        with self._throttle.slot(self.name):
            return self._inner.generate_problem(spec)
