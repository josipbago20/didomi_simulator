"""Didomi API simulator. Run: uvicorn app.main:app"""
from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path

from fastapi import FastAPI, Request
from fastapi.responses import PlainTextResponse

from . import auth, errors
from .config import Settings, load_settings
from .population import GeneratedRepository
from .routers import consents, metadata

DOC_PATH = Path(__file__).resolve().parent.parent / "docs" / "didomi-api.md"


def create_app(settings: Settings | None = None) -> FastAPI:
    settings = settings or load_settings()
    app = FastAPI(title="Didomi API (simulator)", version="1.0",
                  description="Stand-in for https://api.didomi.io/v1. Reference: /docs/didomi-api.md")
    app.state.settings = settings
    app.state.repository = GeneratedRepository(settings)
    app.state.rate_limiter = auth.RateLimiter(settings.rate_limit, settings.rate_window_s)
    app.state.clock = (lambda: settings.now) if settings.now else (lambda: datetime.now(timezone.utc))
    errors.install(app)
    for router in (auth.router, consents.router, metadata.router):
        app.include_router(router, prefix="/v1")

    @app.get("/docs/didomi-api.md", include_in_schema=False)
    def reference(request: Request) -> PlainTextResponse:
        base_url = str(request.base_url).rstrip("/") + "/v1"
        text = DOC_PATH.read_text(encoding="utf-8").replace("{{BASE_URL}}", base_url)
        return PlainTextResponse(text, media_type="text/markdown; charset=utf-8")

    @app.get("/health", include_in_schema=False)
    def health() -> dict:
        return {"status": "ok"}

    return app


app = create_app()
