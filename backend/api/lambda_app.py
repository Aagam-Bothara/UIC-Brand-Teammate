"""AWS Lambda entrypoint for the integrated UIC Editorial Assistant API (behind API Gateway HTTP API).

Lambda handler: ``backend.api.lambda_app.handler``. Deploy with ``scripts/aws/deploy_rag_api.py``.

Serves ``backend.api.main.app`` (Task I.3): ``/api/rag/*`` (WS1), ``/api/rules*`` + ``/api/audiences``
(WS2), ``/api/analyze`` + ``/api/llm/refine`` (orchestrator), plus ``/docs``.

Allowed CORS origins come from ``UIC_CORS_ORIGINS`` (comma-separated, default ``*``).
"""

from __future__ import annotations

from mangum import Mangum

from backend.api.main import ENV_CORS_ORIGINS, app, cors_origins

__all__ = ["app", "handler", "cors_origins", "ENV_CORS_ORIGINS"]

handler = Mangum(app, lifespan="off")
