"""HTTP client for the AccessLens API. The UI never runs the pipeline itself (ADR-005)."""

from typing import Any

import httpx

TIMEOUT_S = 90.0


class ApiError(Exception):
    """A problem+json error from the API; the message is already safe to show."""

    def __init__(self, code: str, message: str) -> None:
        super().__init__(message)
        self.code = code


class AccessLensClient:
    def __init__(self, base_url: str, api_key: str, http: httpx.Client | None = None) -> None:
        self._http = http or httpx.Client(base_url=base_url, timeout=TIMEOUT_S)
        self._headers = {"X-API-Key": api_key}

    def audit(
        self,
        data: bytes,
        *,
        rules_only: bool,
        fmt: str = "json",
        target_grade: int | None = None,
    ) -> Any:
        """Upload ``data``; returns parsed JSON for ``json``, raw bytes/text for other formats.

        The upload is sent under a fixed name, so the user's file name never leaves the browser
        session.
        """
        form = {"mode": "rules_only" if rules_only else "full"}
        if target_grade:
            form["target_grade"] = str(target_grade)
        response = self._http.post(
            "/v1/audits",
            params={"format": fmt},
            data=form,
            files={"file": ("document.docx", data)},
            headers=self._headers,
        )
        if response.status_code >= 400:
            try:
                problem = response.json()
                raise ApiError(
                    problem.get("code", "error"), problem.get("detail") or problem["title"]
                )
            except (ValueError, KeyError):
                raise ApiError("error", "The server could not process the request.") from None
        return response.json() if fmt == "json" else response.content
