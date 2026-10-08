"""Standalone dev server for Workstream 1 (RAG) only.

NOT the production app. The real, integrated FastAPI app is ``backend/api/main.py``
(Task I.3), which mounts this same router alongside the other workstreams' routers.

This exists so the RAG endpoints can be run and tried independently at /docs:

    .venv/bin/uvicorn backend.api.dev_server:app --reload
    open http://127.0.0.1:8000/docs

With no ``UIC_KB_ID`` configured, the RAG service uses the local BM25 backend over
``data/guidelines/`` (run ``.venv/bin/python -m scripts.scrape_guidelines`` first) — no AWS needed.
"""

from __future__ import annotations

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import RedirectResponse

from backend.api.rag_routes import router as rag_router

app = FastAPI(
    title="UIC Editorial Assistant — RAG (dev)",
    description=(
        "Workstream 1 dev server: retrieval over the UIC brand guidelines. "
        "The integrated app lives in `backend/api/main.py` (Task I.3)."
    ),
    version="0.1.0",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "http://localhost:3000",
        "http://127.0.0.1:3000",
        "http://localhost:5173",
        "http://127.0.0.1:5173",
    ],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(rag_router)


@app.get("/", include_in_schema=False)
def root() -> RedirectResponse:
    return RedirectResponse(url="/docs")
