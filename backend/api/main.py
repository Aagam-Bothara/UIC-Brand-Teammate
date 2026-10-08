"""Integrated FastAPI app for the UIC Editorial Assistant (Task I.3).

Mounts every workstream's router:

* ``/api/rag/*``                 Workstream 1 - guideline retrieval (rag_routes)
* ``/api/rules``, ``/api/rules/{id}``, ``/api/rules/check``, ``/api/audiences``
                                 Workstream 2 - rule engine + scoring (rules_routes)
* ``/api/analyze``, ``/api/llm/refine``
                                 Orchestrator + interim Bedrock rewrite (analyze_routes)

Local:  ``.venv/bin/uvicorn backend.api.main:app --reload`` then open http://127.0.0.1:8000/docs
Lambda: ``backend.api.lambda_app.handler`` serves this app (deploy: scripts/aws/deploy_rag_api.py).

Allowed CORS origins come from ``UIC_CORS_ORIGINS`` (comma-separated, default ``*``).
"""

from __future__ import annotations

import os

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import RedirectResponse

from backend.api.analyze_routes import router as analyze_router
from backend.api.rag_routes import router as rag_router
from backend.api.rules_routes import router as rules_router

ENV_CORS_ORIGINS = "UIC_CORS_ORIGINS"


def cors_origins() -> list[str]:
    raw = os.environ.get(ENV_CORS_ORIGINS, "").strip()
    if not raw:
        return ["*"]
    return [o.strip() for o in raw.split(",") if o.strip()]


def create_app() -> FastAPI:
    app = FastAPI(
        title="UIC Editorial Assistant API",
        description="Integrated backend: rule engine + scoring (WS2), guideline retrieval (WS1), and "
                    "Bedrock-powered rewrites/chat (`/api/analyze`, `/api/llm/refine`).",
        version="1.0.0",
    )
    origins = cors_origins()
    app.add_middleware(
        CORSMiddleware,
        allow_origins=origins,
        # Browsers reject credentials with a wildcard origin; the API uses no cookies anyway.
        allow_credentials="*" not in origins,
        allow_methods=["GET", "POST", "OPTIONS"],
        allow_headers=["*"],
    )
    app.include_router(rag_router)
    app.include_router(rules_router)
    app.include_router(analyze_router)

    @app.get("/", include_in_schema=False)
    def root() -> RedirectResponse:
        return RedirectResponse(url="/docs")

    @app.get("/api/health", tags=["meta"], summary="Liveness probe")
    def health() -> dict:
        return {"status": "ok"}

    return app


app = create_app()
