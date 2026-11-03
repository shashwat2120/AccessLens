"""API key authentication (SECURITY §7): keys exist only as SHA-256 hashes in configuration."""

import hashlib
import hmac

from fastapi import Request

from accesslens.errors import UnauthorizedError


def hash_key(key: str) -> str:
    return hashlib.sha256(key.encode("utf-8")).hexdigest()


class ApiKeyAuth:
    """FastAPI dependency; with no keys configured every request is refused (fail closed)."""

    def __init__(self, hashes_csv: str) -> None:
        self._hashes = [h.strip().lower() for h in hashes_csv.split(",") if h.strip()]

    def __call__(self, request: Request) -> str:
        candidate = hash_key(request.headers.get("x-api-key", ""))
        matched = False
        for known in self._hashes:  # no early exit: timing does not reveal which key matched
            matched |= hmac.compare_digest(candidate, known)
        if not matched:
            raise UnauthorizedError
        key_id = candidate[:12]
        request.state.key_id = key_id  # for per-key rate limiting; never the key itself
        return key_id
