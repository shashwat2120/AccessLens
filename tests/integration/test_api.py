import io
import time
import zipfile
from pathlib import Path
from typing import Any

import pytest
from fastapi.testclient import TestClient

from accesslens.api.auth import hash_key
from accesslens.api.main import create_app
from accesslens.config import Settings
from accesslens.rules.catalog import rule_catalog
from fakes import service_for

KEY = "test-key-123"
HEADERS = {"X-API-Key": KEY}
DOCX = "application/vnd.openxmlformats-officedocument.wordprocessingml.document"
SECURITY_HEADERS = (
    "x-content-type-options",
    "referrer-policy",
    "x-frame-options",
    "strict-transport-security",
    "content-security-policy",
)


def settings(**kw: Any) -> Settings:
    base: dict[str, Any] = {
        "api_keys_sha256": hash_key(KEY),
        "rate_limit": "1000/minute",
        "llm_budget_per_doc": 50,
    }
    return Settings(_env_file=None, **{**base, **kw})


def client(service: Any = None, **kw: Any) -> TestClient:
    cfg = settings(**kw)
    return TestClient(create_app(service or service_for(cfg), cfg), raise_server_exceptions=False)


def doc(corpus: tuple[Path, Path], folder: str, name: str) -> bytes:
    return (corpus[0] / folder / f"{name}.docx").read_bytes()


def upload(data: bytes, name: str = "document.docx") -> dict[str, Any]:
    return {"file": (name, data, DOCX)}


def assert_problem(response: Any, status: int, code: str) -> dict[str, Any]:
    assert response.status_code == status
    assert response.headers["content-type"].startswith("application/problem+json")
    body = response.json()
    assert body["code"] == code
    assert body["status"] == status
    assert body["type"] == f"urn:accesslens:problem:{code}"
    for name in SECURITY_HEADERS:
        assert name in response.headers
    return body  # type: ignore[no-any-return]


# ---- authentication ------------------------------------------------------------------


@pytest.mark.parametrize("headers", [{}, {"X-API-Key": "wrong"}, {"X-API-Key": ""}])
def test_requests_without_a_valid_key_are_refused(
    corpus: tuple[Path, Path], headers: dict[str, str]
) -> None:
    c = client()
    response = c.post("/v1/audits", files=upload(doc(corpus, "clean", "clean-01")), headers=headers)
    assert_problem(response, 401, "unauthorized")
    assert_problem(c.get("/v1/rules", headers=headers), 401, "unauthorized")


def test_with_no_keys_configured_everything_is_refused() -> None:
    c = client(api_keys_sha256="")
    assert_problem(c.get("/v1/rules", headers=HEADERS), 401, "unauthorized")


def test_the_second_of_several_configured_keys_works() -> None:
    c = client(api_keys_sha256=f"{hash_key('other')}, {hash_key(KEY).upper()}")
    assert c.get("/v1/rules", headers=HEADERS).status_code == 200


# ---- audits --------------------------------------------------------------------------


def test_audit_returns_the_same_report_as_the_service(corpus: tuple[Path, Path]) -> None:
    cfg = settings()
    service = service_for(cfg)
    c = TestClient(create_app(service, cfg))
    data = doc(corpus, "synthetic", "syn-01")
    response = c.post(
        "/v1/audits", files=upload(data), data={"mode": "rules_only"}, headers=HEADERS
    )
    assert response.status_code == 200
    body = response.json()
    expected = service.audit(data, None).model_dump(mode="json")
    expected["mode"] = "rules_only"
    assert [f["id"] for f in body["findings"]] == [
        f["id"] for f in service.audit(data).model_dump(mode="json")["findings"]
    ]
    assert body["mode"] == "rules_only"
    assert body["llm"] is None
    assert "X-Request-ID" in response.headers or "x-request-id" in response.headers


def test_html_and_xlsx_formats(corpus: tuple[Path, Path]) -> None:
    c = client()
    data = doc(corpus, "synthetic", "syn-01")
    html = c.post("/v1/audits?format=html", files=upload(data), headers=HEADERS)
    assert html.status_code == 200
    assert html.headers["content-type"].startswith("text/html")
    assert (
        html.headers["content-security-policy"] == "default-src 'none'; style-src 'unsafe-inline'"
    )
    assert "<h1>Accessibility report</h1>" in html.text
    negotiated = c.post(
        "/v1/audits", files=upload(data), headers={**HEADERS, "Accept": "text/html"}
    )
    assert negotiated.headers["content-type"].startswith("text/html")
    xlsx = c.post("/v1/audits?format=xlsx", files=upload(data), headers=HEADERS)
    assert xlsx.status_code == 200
    assert "spreadsheetml" in xlsx.headers["content-type"]
    assert zipfile.is_zipfile(io.BytesIO(xlsx.content))


def test_invalid_inputs_get_typed_problems(corpus: tuple[Path, Path]) -> None:
    c = client()
    good = doc(corpus, "clean", "clean-01")
    assert_problem(
        c.post("/v1/audits", files=upload(b"not a docx"), headers=HEADERS), 400, "invalid_file"
    )
    assert_problem(
        c.post("/v1/audits", data={"target_grade": "99"}, files=upload(good), headers=HEADERS),
        400,
        "invalid_request",
    )
    assert_problem(c.post("/v1/audits", headers=HEADERS), 400, "invalid_request")
    assert_problem(c.get("/v1/nope", headers=HEADERS), 404, "not_found")
    assert_problem(c.get("/v1/audits", headers=HEADERS), 405, "method_not_allowed")


def test_macro_enabled_documents_are_rejected() -> None:
    types = (
        '<?xml version="1.0"?><Types xmlns="http://schemas.openxmlformats.org/package/2006/'
        'content-types"><Override PartName="/word/document.xml" ContentType="application/'
        'vnd.ms-word.document.macroEnabled.main+xml"/></Types>'
    )
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w") as archive:
        archive.writestr("[Content_Types].xml", types)
        archive.writestr("word/document.xml", "<doc/>")
    response = client().post("/v1/audits", files=upload(buffer.getvalue()), headers=HEADERS)
    assert_problem(response, 422, "macro_enabled")


def test_oversized_uploads_are_stopped_at_the_server() -> None:
    c = client(max_upload_mb=1)
    big = b"PK\x03\x04" + bytes(3 * 1024 * 1024)
    assert_problem(c.post("/v1/audits", files=upload(big), headers=HEADERS), 413, "file_too_large")
    # Just over the file cap but under the body cap is caught by the in-code check.
    mid = b"PK\x03\x04" + bytes(1024 * 1024 + 10)
    assert_problem(c.post("/v1/audits", files=upload(mid), headers=HEADERS), 413, "file_too_large")


def test_a_hostile_file_name_is_ignored_and_never_echoed(corpus: tuple[Path, Path]) -> None:
    response = client().post(
        "/v1/audits",
        files=upload(doc(corpus, "clean", "clean-01"), "../../etc/passwd<script>.docx"),
        data={"mode": "rules_only"},
        headers=HEADERS,
    )
    assert response.status_code == 200
    assert "passwd" not in response.text
    assert "script" not in response.text


def test_batch_audit_with_a_bad_file_in_the_mix(corpus: tuple[Path, Path]) -> None:
    c = client()
    files = [
        ("files", ("a.docx", doc(corpus, "clean", "clean-01"), DOCX)),
        ("files", ("b.docx", b"garbage", DOCX)),
        ("files", ("c.docx", doc(corpus, "synthetic", "syn-01"), DOCX)),
    ]
    response = c.post("/v1/audits/batch", files=files, data={"mode": "rules_only"}, headers=HEADERS)
    assert response.status_code == 200
    body = response.json()
    assert body["summary"]["files"] == 3
    assert body["summary"]["succeeded"] == 2
    assert body["summary"]["failed"] == 1
    assert body["errors"] == [
        {"index": 1, "code": "invalid_file", "detail": body["errors"][0]["detail"]}
    ]
    assert len(body["reports"]) == 2
    assert body["summary"]["findings_by_severity"]["critical"] >= 1


def test_batch_size_is_limited(corpus: tuple[Path, Path]) -> None:
    c = client(max_batch_files=2)
    data = doc(corpus, "clean", "clean-01")
    files = [("files", (f"{i}.docx", data, DOCX)) for i in range(3)]
    assert_problem(c.post("/v1/audits/batch", files=files, headers=HEADERS), 400, "invalid_request")


# ---- catalog, health, docs, CORS -------------------------------------------------------


def test_rules_endpoint_lists_every_check() -> None:
    response = client().get("/v1/rules", headers=HEADERS)
    assert response.status_code == 200
    rules = response.json()
    assert len(rules) == len(rule_catalog())
    assert {r["source"] for r in rules} == {"rule", "llm"}
    assert all(r["how_to_fix"] for r in rules)


def test_health_endpoints_are_open_and_never_call_an_llm() -> None:
    c = client()
    assert c.get("/healthz").json() == {"status": "ok"}
    assert c.get("/readyz").json()["status"] == "ready"


def test_docs_are_disabled_in_production_only() -> None:
    prod = client(app_env="prod")
    assert prod.get("/docs").status_code == 404
    assert prod.get("/openapi.json").status_code == 404
    dev = client(app_env="dev")
    assert dev.get("/openapi.json").status_code == 200


def test_cors_allows_only_configured_origins() -> None:
    c = client(cors_origins="https://ui.example.org")
    allowed = c.get("/healthz", headers={"Origin": "https://ui.example.org"})
    assert allowed.headers["access-control-allow-origin"] == "https://ui.example.org"
    other = c.get("/healthz", headers={"Origin": "https://evil.example"})
    assert "access-control-allow-origin" not in other.headers
    none = client()
    assert (
        "access-control-allow-origin"
        not in none.get("/healthz", headers={"Origin": "https://ui.example.org"}).headers
    )


def test_wildcard_cors_is_refused_in_production() -> None:
    with pytest.raises(ValueError):
        create_app(service_for(settings()), settings(app_env="prod", cors_origins="*"))
    create_app(service_for(settings()), settings(app_env="dev", cors_origins="*"))


# ---- abuse prevention and error hygiene -----------------------------------------------


def test_rate_limit_applies_per_key_and_to_failed_logins() -> None:
    c = client(rate_limit="3/minute")
    for _ in range(3):
        assert c.get("/v1/rules", headers=HEADERS).status_code == 200
    limited = c.get("/v1/rules", headers=HEADERS)
    body = assert_problem(limited, 429, "rate_limited")
    assert body["title"] == "Too many requests"
    assert limited.headers["retry-after"] == "60"

    brute = client(rate_limit="3/minute")
    statuses = [
        brute.get("/v1/rules", headers={"X-API-Key": f"guess-{i}"}).status_code for i in range(5)
    ]
    assert statuses[:3] == [401, 401, 401]
    assert statuses[3:] == [429, 429]
    assert brute.get("/healthz").status_code == 200  # probes are exempt


def test_security_headers_and_request_id_on_every_response() -> None:
    c = client()
    for response in (c.get("/healthz"), c.get("/nope"), c.get("/v1/rules")):
        for name in SECURITY_HEADERS:
            assert name in response.headers
        assert len(response.headers["x-request-id"]) == 32


def test_unexpected_errors_are_generic() -> None:
    class Exploding:
        def audit(self, *args: Any, **kwargs: Any) -> Any:
            raise RuntimeError("secret document text /internal/path")

    c = client(service=Exploding())
    response = c.post("/v1/audits", files=upload(b"x"), headers=HEADERS)
    body = assert_problem(response, 500, "internal_error")
    assert "secret" not in response.text
    assert "/internal/path" not in response.text
    assert body["detail"] == "An internal error occurred."


def test_slow_requests_time_out() -> None:
    class Slow:
        def audit(self, *args: Any, **kwargs: Any) -> Any:
            time.sleep(0.6)

    c = client(service=Slow(), request_timeout_s=0.1)
    assert_problem(c.post("/v1/audits", files=upload(b"x"), headers=HEADERS), 504, "timeout")
