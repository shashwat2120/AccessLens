"""HTTP client for the AccessLens API. The UI never runs the pipeline itself (ADR-005)."""

from typing import Any

import httpx

TIMEOUT_S = 90.0


class ApiError(Exception):
    """A problem+json error from the API; the message is already safe to show."""

    def __init__(self, code: str, message: str) -> None:
        super().__init__(message)
        self.code = code


def _raise_for_problem(response: httpx.Response) -> None:
    if response.status_code < 400:
        return
    try:
        problem = response.json()
        message = problem.get("detail") or problem["title"]
        code = problem.get("code", "error")
    except (ValueError, KeyError, AttributeError):
        raise ApiError("error", "The server could not process the request.") from None
    raise ApiError(code, message)


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
        _raise_for_problem(response)
        return response.json() if fmt == "json" else response.content

    def rules(self) -> list[dict[str, Any]]:
        """The rule catalog (ids, titles, WCAG links), used to enrich the findings view."""
        response = self._http.get("/v1/rules", headers=self._headers)
        _raise_for_problem(response)
        return list(response.json())
