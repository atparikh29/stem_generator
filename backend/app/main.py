"""FastAPI application entrypoint.

Run: uvicorn app.main:app --reload  (from the backend/ directory)
"""
from __future__ import annotations

import math

from fastapi import Depends, FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from .api.routes import router
from .config import settings
from .db import init_db
from .ratelimit import LLMRateLimitError, limit

app = FastAPI(
    title="Regenerate-Until-Valid: STEM Problem Generator",
    version="0.1.0",
    description="Neuro-symbolic agentic pipeline for reliable STEM problem generation.",
)

# Permissive CORS for local Next.js dev (localhost OR 127.0.0.1, any port).
# Restrict in production.
app.add_middleware(
    CORSMiddleware,
    allow_origin_regex=r"http://(localhost|127\.0\.0\.1):\d+",
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.on_event("startup")
def _startup() -> None:
    init_db()


@app.exception_handler(LLMRateLimitError)
def _llm_rate_limited(request: Request, exc: LLMRateLimitError) -> JSONResponse:
    """Being throttled on the way *out* to a vendor is still a 429 for the
    caller, not a 500 -- the request was fine, we just have no capacity yet.

    Only reaches here on the non-streaming routes; the SSE endpoint catches it
    in its worker thread and reports it as an `error` event on the stream.
    """
    return JSONResponse(
        status_code=429,
        content={"detail": f"Model provider rate limit: {exc}"},
        headers={"Retry-After": str(max(1, math.ceil(settings.llm_rate_limit_wait_seconds)))},
    )


@app.get("/health")
def health() -> dict:
    """Deliberately outside the rate limiter so a probe can't be locked out."""
    return {"status": "ok", "llm_provider": settings.llm_provider}


# Every /api route gets the default per-client cap. Routes that are expensive
# (the LLM loop) or security-sensitive (auth) add a tighter one of their own.
app.include_router(router, prefix="/api", dependencies=[Depends(limit("default"))])
