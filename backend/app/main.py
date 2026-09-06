from __future__ import annotations

import os

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api.routes import router

app = FastAPI(
    title="QuantPulse API",
    description="Regime-aware short-horizon systematic FX alpha research platform.",
    version="0.1.0",
)

# CORS origins are environment-driven so production deployments can restrict
# to their actual frontend domain(s) instead of "*". Set QUANTPULSE_CORS_ORIGINS
# to a comma-separated list (e.g. "https://app.example.com,https://staging.example.com").
# Falls back to "*" only when unset, preserving today's local-dev behavior.
_cors_env = os.environ.get("QUANTPULSE_CORS_ORIGINS", "").strip()
_cors_origins = [o.strip() for o in _cors_env.split(",") if o.strip()] if _cors_env else ["*"]

app.add_middleware(
    CORSMiddleware,
    allow_origins=_cors_origins,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(router, prefix="/api")


@app.get("/health")
def health():
    return {"status": "ok"}
