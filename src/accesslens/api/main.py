"""FastAPI application factory (TRD §7, SECURITY §7).

Run with ``uvicorn --factory accesslens.api.main:app_factory`` (``make run-api``).
"""

import asyncio
from collections.abc import Awaitable, Callable

from fastapi import FastAPI, Request, Response
from fastapi.middleware.cors import CORSMiddleware

from accesslens.api.auth import ApiKeyAuth
from accesslens.api.limits import BodyLimitMiddleware, RateLimiter, body_limit_for, ip_guard
from accesslens.api.problems import SECURITY_HEADERS, problem_response, register_handlers
from accesslens.api.routes import build_routers, new_request_id
from accesslens.config import Settings, get_settings
from accesslens.logging import configure_logging
from accesslens.service import AuditService


def _origins(settings: Settings) -> list[str]:
    origins = [o.strip() for o in settings.cors_origins.split(",") if o.strip()]
    if settings.app_env == "prod" and "*" in origins:
        raise ValueError("CORS_ORIGINS must not contain '*' in production")
    return origins


def create_app(service: AuditService | None = None, settings: Settings | None = None) -> FastAPI:
    cfg = settings or get_settings()
    origins = _origins(cfg)
    docs_enabled = cfg.app_env != "prod"
    app = FastAPI(
        title="AccessLens",
        version="1.0",
        docs_url="/docs" if docs_enabled else None,
        redoc_url=None,
        openapi_url="/openapi.json" if docs_enabled else None,
    )
    register_handlers(app)

    # Per client IP (before auth, so failed logins count) and per API key (after auth).
    key_limiter = RateLimiter(cfg.rate_limit)
    auth_keys = ApiKeyAuth(cfg.api_keys_sha256)

    def authenticate(request: Request) -> str:
        key_id = auth_keys(request)
        key_limiter.check("key", key_id)
        return key_id

    v1, ops = build_routers(
        service or AuditService(cfg), cfg, ip_guard(RateLimiter(cfg.rate_limit)), authenticate
    )
    app.include_router(v1)
    app.include_router(ops)

    @app.middleware("http")
    async def request_context(
        request: Request, call_next: Callable[[Request], Awaitable[Response]]
    ) -> Response:
        request.state.request_id = new_request_id()
        try:
            response = await asyncio.wait_for(call_next(request), cfg.request_timeout_s)
        except TimeoutError:
            response = problem_response(504, "timeout", "The request took too long.")
        for name, value in SECURITY_HEADERS.items():
            response.headers.setdefault(name, value)
        response.headers["X-Request-ID"] = request.state.request_id
        return response

    if origins:
        app.add_middleware(
            CORSMiddleware,
            allow_origins=origins,
            allow_methods=["GET", "POST"],
            allow_headers=["X-API-Key", "Content-Type", "Accept"],
        )
    # Added last, so it is the outermost layer and sees the raw request first.
    app.add_middleware(
        BodyLimitMiddleware,
        limit_for=body_limit_for(cfg.max_upload_mb, cfg.max_batch_files),
    )
    return app


def app_factory() -> FastAPI:
    """Entry point for ``uvicorn --factory accesslens.api.main:app_factory``.

    Switches on JSON logging (one object per line, never document content) before building the
    app; ``create_app`` itself leaves logging alone so tests and embedding stay in control.
    """
    configure_logging()
    return create_app()
