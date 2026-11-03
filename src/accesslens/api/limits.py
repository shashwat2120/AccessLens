"""Request size limits and rate limits (SECURITY §3, §7).

Rate limiting uses the ``limits`` library (the engine behind slowapi) as plain FastAPI
dependencies. The per-IP check runs before authentication, so failed logins are throttled too.
"""

from collections.abc import Callable
from typing import Any

from fastapi import Request
from limits import parse
from limits.storage import MemoryStorage
from limits.strategies import MovingWindowRateLimiter

from accesslens.api.problems import problem_response
from accesslens.errors import FileTooLargeError, RateLimitedError

_MULTIPART_OVERHEAD = 1024 * 1024


class RateLimiter:
    """Moving-window limiter, in memory (the service is stateless and holds nothing durable)."""

    def __init__(self, rate: str) -> None:
        self._item = parse(rate)
        self._strategy = MovingWindowRateLimiter(MemoryStorage())

    def check(self, scope: str, key: str) -> None:
        if not self._strategy.hit(self._item, scope, key):
            raise RateLimitedError


def ip_guard(limiter: RateLimiter) -> Callable[[Request], None]:
    """Dependency counting every ``/v1`` request per client IP, before auth runs.

    Behind a proxy, run uvicorn with ``--proxy-headers`` and a trusted ``--forwarded-allow-ips``
    so ``request.client`` is the real caller, not the proxy.
    """

    def guard(request: Request) -> None:
        limiter.check("ip", request.client.host if request.client else "unknown")

    return guard


class _TooLarge(Exception):
    pass


class BodyLimitMiddleware:
    """Reject over-size bodies from Content-Length, and stop reading streamed ones at the cap."""

    def __init__(self, app: Any, limit_for: Callable[[str], int]) -> None:
        self.app = app
        self.limit_for = limit_for

    async def __call__(self, scope: Any, receive: Any, send: Any) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return
        limit = self.limit_for(scope["path"])
        declared = dict(scope["headers"]).get(b"content-length", b"")
        if declared.isdigit() and int(declared) > limit:
            await self._reject(scope, receive, send)
            return

        received = 0

        async def counting_receive() -> Any:
            nonlocal received
            message = await receive()
            if message["type"] == "http.request":
                received += len(message.get("body", b""))
                if received > limit:
                    raise _TooLarge
            return message

        try:
            await self.app(scope, counting_receive, send)
        except _TooLarge:
            await self._reject(scope, receive, send)

    @staticmethod
    async def _reject(scope: Any, receive: Any, send: Any) -> None:
        error = FileTooLargeError()
        await problem_response(error.status, error.code, str(error))(scope, receive, send)


def body_limit_for(max_upload_mb: int, max_batch_files: int) -> Callable[[str], int]:
    single = max_upload_mb * 1024 * 1024 + _MULTIPART_OVERHEAD

    def limit_for(path: str) -> int:
        if path.rstrip("/").endswith("/audits/batch"):
            return max_upload_mb * max_batch_files * 1024 * 1024 + _MULTIPART_OVERHEAD
        return single

    return limit_for
