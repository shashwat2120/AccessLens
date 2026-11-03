"""RFC 9457 ``application/problem+json`` responses with stable codes (TRD §7, SECURITY §7).

Messages are generic: no stack traces, internal paths or document content ever reach a client.
"""

import logging
from typing import Any

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from starlette.exceptions import HTTPException as StarletteHTTPException

from accesslens.errors import AccessLensError, InvalidRequestError, RateLimitedError

PROBLEM_JSON = "application/problem+json"
SECURITY_HEADERS = {
    "X-Content-Type-Options": "nosniff",
    "Referrer-Policy": "no-referrer",
    "X-Frame-Options": "DENY",
    "Strict-Transport-Security": "max-age=63072000; includeSubDomains",
    "Content-Security-Policy": "default-src 'none'; frame-ancestors 'none'",
    "Cache-Control": "no-store",
}
_TITLES = {
    "invalid_file": "Invalid file",
    "file_too_large": "File too large",
    "macro_enabled": "Macro-enabled documents are not accepted",
    "parse_failed": "Document could not be parsed",
    "rate_limited": "Too many requests",
    "unauthorized": "Unauthorized",
    "invalid_request": "Invalid request",
    "not_found": "Not found",
    "method_not_allowed": "Method not allowed",
    "timeout": "Request timed out",
    "internal_error": "Internal error",
}
logger = logging.getLogger(__name__)


def problem_response(
    status: int, code: str, detail: str | None = None, headers: dict[str, str] | None = None
) -> JSONResponse:
    body: dict[str, Any] = {
        "type": f"urn:accesslens:problem:{code}",
        "title": _TITLES.get(code, "Error"),
        "status": status,
        "code": code,
    }
    if detail:
        body["detail"] = detail
    return JSONResponse(
        body,
        status_code=status,
        media_type=PROBLEM_JSON,
        headers={**SECURITY_HEADERS, **(headers or {})},
    )


def register_handlers(app: FastAPI) -> None:
    @app.exception_handler(AccessLensError)
    async def _domain(request: Request, exc: AccessLensError) -> JSONResponse:
        headers = {"Retry-After": "60"} if isinstance(exc, RateLimitedError) else None
        return problem_response(exc.status, exc.code, str(exc), headers)

    @app.exception_handler(RequestValidationError)
    async def _validation(request: Request, exc: RequestValidationError) -> JSONResponse:
        error = InvalidRequestError()
        return problem_response(error.status, error.code, str(error))

    @app.exception_handler(StarletteHTTPException)
    async def _http(request: Request, exc: StarletteHTTPException) -> JSONResponse:
        code = {404: "not_found", 405: "method_not_allowed"}.get(exc.status_code, "invalid_request")
        return problem_response(exc.status_code, code)

    @app.exception_handler(Exception)
    async def _unexpected(request: Request, exc: Exception) -> JSONResponse:
        logger.error("unhandled_error error=%s", type(exc).__name__)  # type only, no content
        return problem_response(500, "internal_error", "An internal error occurred.")
