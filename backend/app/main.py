"""FastAPI application entrypoint.

Run: uvicorn app.main:app --reload  (from the backend/ directory)
"""
from __future__ import annotations

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from .api.routes import router
from .config import settings
from .db import init_db

app = FastAPI(
    title="Regenerate-Until-Valid: STEM Problem Generator",
    version="0.1.0",
    description="Neuro-symbolic agentic pipeline for reliable STEM problem generation.",
)

# Permissive CORS for local Next.js dev. Restrict in production.
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:3000"],
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.on_event("startup")
def _startup() -> None:
    init_db()


@app.get("/health")
def health() -> dict:
    return {"status": "ok", "llm_provider": settings.llm_provider}


app.include_router(router, prefix="/api")
