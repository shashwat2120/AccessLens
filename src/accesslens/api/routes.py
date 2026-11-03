"""``/v1`` routes (TRD §7). Thin: every audit goes through ``AuditService``."""

import uuid
from collections.abc import Callable
from typing import Annotated, Any, Literal

from fastapi import APIRouter, Depends, File, Form, Query, Request, Response, UploadFile
from fastapi.responses import JSONResponse

from accesslens.api.problems import SECURITY_HEADERS
from accesslens.config import Settings
from accesslens.errors import AccessLensError, FileTooLargeError, InvalidRequestError
from accesslens.models import AuditOptions, Report
from accesslens.report.html import HTML_CSP, render_html
from accesslens.report.xlsx import render_xlsx
from accesslens.rules.catalog import rule_catalog
from accesslens.service import AuditService

XLSX_TYPE = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
Mode = Literal["full", "rules_only"]
Format = Literal["json", "html", "xlsx"]


def _read_limited(upload: UploadFile, settings: Settings) -> bytes:
    """The filename is never used; content is read with a hard cap."""
    cap = settings.max_upload_mb * 1024 * 1024
    data = upload.file.read(cap + 1)
    if len(data) > cap:
        raise FileTooLargeError
    return data


def _respond(report: Report, fmt: Format) -> Response:
    if fmt == "html":
        return Response(
            render_html(report),
            media_type="text/html",
            headers={**SECURITY_HEADERS, "Content-Security-Policy": HTML_CSP},
        )
    if fmt == "xlsx":
        return Response(render_xlsx(report), media_type=XLSX_TYPE)
    return JSONResponse(report.model_dump(mode="json"))


def _negotiate(request: Request, requested: Format | None) -> Format:
    if requested:
        return requested
    accept = request.headers.get("accept", "")
    return "html" if "text/html" in accept and "application/json" not in accept else "json"


def build_routers(
    service: AuditService,
    settings: Settings,
    ip_guard: Callable[[Request], None],
    auth: Callable[[Request], str],
) -> tuple[APIRouter, APIRouter]:
    """Returns (v1 router, ops router). Only ``/v1`` is authenticated and rate limited."""
    # Router dependencies run before each route's own, so the IP limit precedes auth.
    v1 = APIRouter(dependencies=[Depends(ip_guard)])
    ops = APIRouter()

    @v1.post("/v1/audits")
    def create_audit(
        request: Request,
        file: Annotated[UploadFile, File()],
        _key: Annotated[str, Depends(auth)],
        mode: Annotated[Mode, Form()] = "full",
        target_grade: Annotated[int | None, Form(ge=1, le=18)] = None,
        format: Annotated[Format | None, Query()] = None,
    ) -> Response:
        report = service.audit(
            _read_limited(file, settings),
            AuditOptions(mode=mode, target_grade=target_grade),
            request_id=request.state.request_id,
        )
        return _respond(report, _negotiate(request, format))

    @v1.post("/v1/audits/batch")
    def create_batch(
        request: Request,
        files: Annotated[list[UploadFile], File()],
        _key: Annotated[str, Depends(auth)],
        mode: Annotated[Mode, Form()] = "full",
        target_grade: Annotated[int | None, Form(ge=1, le=18)] = None,
    ) -> JSONResponse:
        if not 1 <= len(files) <= settings.max_batch_files:
            raise InvalidRequestError(f"Send between 1 and {settings.max_batch_files} files.")
        options = AuditOptions(mode=mode, target_grade=target_grade)
        reports: list[dict[str, Any]] = []
        errors: list[dict[str, Any]] = []
        totals = {"critical": 0, "high": 0, "medium": 0, "low": 0}
        scores: list[int] = []
        for index, upload in enumerate(files):
            try:
                report = service.audit(
                    _read_limited(upload, settings),
                    options,
                    request_id=f"{request.state.request_id}-{index}",
                )
            except AccessLensError as exc:
                errors.append({"index": index, "code": exc.code, "detail": str(exc)})
                continue
            reports.append(report.model_dump(mode="json"))
            scores.append(report.score)
            for severity, count in report.counts.items():
                totals[severity.value] += count
        summary = {
            "files": len(files),
            "succeeded": len(reports),
            "failed": len(errors),
            "mean_score": round(sum(scores) / len(scores), 1) if scores else None,
            "findings_by_severity": totals,
        }
        return JSONResponse({"reports": reports, "errors": errors, "summary": summary})

    @v1.get("/v1/rules")
    def list_rules(_key: Annotated[str, Depends(auth)]) -> JSONResponse:
        return JSONResponse(
            [
                {
                    "id": r.id,
                    "title": r.title,
                    "severity": r.severity.value,
                    "wcag_criterion": r.wcag_criterion,
                    "wcag_level": r.wcag_level.value,
                    "source": r.source,
                    "description": r.description,
                    "how_to_fix": r.how_to_fix,
                    "wcag_url": r.wcag_url,
                }
                for r in rule_catalog()
            ]
        )

    @ops.get("/healthz")
    def healthz() -> dict[str, str]:
        return {"status": "ok"}

    @ops.get("/readyz")
    def readyz() -> dict[str, str]:
        # Configuration loaded and the service constructed; deliberately does not call an LLM.
        return {"status": "ready", "env": settings.app_env}

    return v1, ops


def new_request_id() -> str:
    return uuid.uuid4().hex
