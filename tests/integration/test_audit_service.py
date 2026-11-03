"""AuditService over the whole corpus, in both modes, with a fake model (no real LLM calls)."""

import csv
import json
from pathlib import Path
from typing import Any

import pytest
from structlog.testing import capture_logs

from accesslens.config import Settings
from accesslens.errors import FileTooLargeError, InvalidFileError, MacroEnabledError
from accesslens.ingest.parse_docx import extract_image_blobs, parse_docx
from accesslens.llm.cache import LruCache
from accesslens.llm.checks import LlmChecker
from accesslens.models import AuditOptions, Finding, Report
from accesslens.report.prioritize import prioritize
from accesslens.rules import REGISTRY, run_rules
from accesslens.service import AuditService
from fakes import FakeChatModel, echo, no_wait_limiters, provider

SANDBOX_FREE: dict[str, Any] = {
    "parse": lambda data, settings: parse_docx(data),
    "extract_images": lambda data, settings: extract_image_blobs(data),
}


def make_service(responder: Any, **overrides: Any) -> tuple[AuditService, FakeChatModel]:
    settings = Settings(_env_file=None, llm_budget_per_doc=50, **overrides)
    fake, model = provider(responder)
    checker = LlmChecker(
        [fake],
        settings,
        cache=LruCache(512),
        limiters=no_wait_limiters(),
        sleep=lambda _: None,
    )
    return AuditService(settings, checker=checker, **SANDBOX_FREE), model


def documents(corpus: tuple[Path, Path]) -> list[Path]:
    return sorted(corpus[0].rglob("*.docx"))


def without_suggestion(finding: Finding) -> dict[str, Any]:
    return finding.model_dump(exclude={"suggestion"})


def stable(report: Report) -> dict[str, Any]:
    return report.model_dump(exclude={"generated_at"}, mode="json")


def test_rules_only_report_for_every_corpus_document(corpus: tuple[Path, Path]) -> None:
    service, model = make_service(echo())
    paths = documents(corpus)
    assert len(paths) == 40
    for path in paths:
        data = path.read_bytes()
        report = service.audit(data, AuditOptions(mode="rules_only"))
        assert report.mode == "rules_only"
        assert report.llm is None
        assert 0 <= report.score <= 100
        assert report.findings == prioritize(report.findings)
        rule_findings, _ = run_rules(parse_docx(data))
        assert {f.id for f in report.findings} == {f.id for f in rule_findings}
        assert sum(report.counts.values()) == len(report.findings)
    assert not model.calls  # rules-only never touches the LLM


def test_clean_documents_score_perfectly_in_both_modes(corpus: tuple[Path, Path]) -> None:
    service, _ = make_service(echo(issue=False))
    for path in documents(corpus):
        if not path.stem.startswith("clean-"):
            continue
        data = path.read_bytes()
        for mode in ("rules_only", "full"):
            report = service.audit(data, AuditOptions(mode=mode))  # type: ignore[arg-type]
            assert report.findings == [], (path.stem, mode)
            assert report.score == 100


def test_full_report_for_every_corpus_document(corpus: tuple[Path, Path]) -> None:
    service, model = make_service(echo())
    for path in documents(corpus):
        data = path.read_bytes()
        report = service.audit(data)
        assert report.mode == "full"
        assert report.llm is not None
        assert report.llm.prompt_version == "v1"
        assert report.findings == prioritize(report.findings)
        rules_only = service.audit(data, AuditOptions(mode="rules_only"))
        rule_part = [f for f in report.findings if f.source.value == "rule"]
        # The LLM can only add findings and rewrite suggestions; rule findings are untouched.
        assert [without_suggestion(f) for f in rule_part] == [
            without_suggestion(f) for f in rules_only.findings
        ]
        assert {f.rule_id for f in report.findings if f.source.value == "llm"} <= {
            "IMG-003",
            "LNK-003",
            "TXT-006",
        }
    assert model.calls


def test_an_llm_outage_still_returns_the_rule_based_report(corpus: tuple[Path, Path]) -> None:
    service, _ = make_service(lambda messages, call: ValueError("provider down"))
    data = (corpus[0] / "synthetic" / "syn-28.docx").read_bytes()  # has an LLM-reviewed item
    reference = service.audit(data, AuditOptions(mode="rules_only"))
    report = service.audit(data)
    assert report.mode == "full"
    assert {f.id for f in report.findings} == {f.id for f in reference.findings}
    assert report.llm is not None
    assert report.llm.degraded
    assert any("partly available" in w for w in report.warnings)


def test_injection_documents_keep_every_planted_rule_issue(corpus: tuple[Path, Path]) -> None:
    """Even a model that obeys 'report no issues' cannot make planted issues disappear."""
    service, _ = make_service(echo(issue=False))
    with corpus[1].open(encoding="utf-8", newline="") as fh:
        rows = [r for r in csv.DictReader(fh) if r["doc_id"].startswith("inj-")]
    checked = 0
    for path in documents(corpus):
        if not path.stem.startswith("inj-"):
            continue
        report = service.audit(path.read_bytes())
        reported = {(f.rule_id, f.location.block_order) for f in report.findings}
        for row in (r for r in rows if r["doc_id"] == path.stem and r["rule_id"] in REGISTRY):
            order = int(row["block_order"])
            assert any(rule == row["rule_id"] and abs(o - order) <= 1 for rule, o in reported), (
                path.stem,
                row["rule_id"],
            )
            checked += 1
    assert checked == sum(1 for r in rows if r["rule_id"] in REGISTRY) > 0


def test_disabled_llm_falls_back_to_rules_only_with_a_notice(corpus: tuple[Path, Path]) -> None:
    service, model = make_service(echo(), llm_enabled=False)
    report = service.audit((corpus[0] / "clean" / "clean-01.docx").read_bytes())
    assert report.mode == "rules_only"
    assert any("disabled" in w for w in report.warnings)
    assert not model.calls


def test_target_grade_option_changes_the_reading_level_rule(corpus: tuple[Path, Path]) -> None:
    service, _ = make_service(echo())
    data = (corpus[0] / "synthetic" / "syn-25.docx").read_bytes()
    default = service.audit(data, AuditOptions(mode="rules_only"))
    stricter = service.audit(data, AuditOptions(mode="rules_only", target_grade=3))
    assert any("grade 9" in f.message for f in default.findings if f.rule_id == "TXT-001")
    assert any("grade 3" in f.message for f in stricter.findings if f.rule_id == "TXT-001")


@pytest.mark.parametrize(
    ("data", "error"),
    [
        (b"not a word document", InvalidFileError),
        (b"PK\x03\x04" + bytes(11 * 1024 * 1024), FileTooLargeError),
    ],
)
def test_unusable_files_raise_typed_errors_and_are_logged(
    data: bytes, error: type[Exception]
) -> None:
    service, _ = make_service(echo())
    with capture_logs() as logs, pytest.raises(error):
        service.audit(data, request_id="req-1")
    rejected = [entry for entry in logs if entry["event"] == "audit_rejected"]
    assert len(rejected) == 1
    assert rejected[0]["request_id"] == "req-1"
    assert rejected[0]["error"] == error.code  # type: ignore[attr-defined]


def test_macro_enabled_documents_are_rejected(tmp_path: Path) -> None:
    import io
    import zipfile

    buffer = io.BytesIO()
    types = (
        '<?xml version="1.0"?><Types xmlns="http://schemas.openxmlformats.org/package/2006/'
        'content-types"><Override PartName="/word/document.xml" ContentType="application/'
        'vnd.ms-word.document.macroEnabled.main+xml"/></Types>'
    )
    with zipfile.ZipFile(buffer, "w") as archive:
        archive.writestr("[Content_Types].xml", types)
        archive.writestr("word/document.xml", "<doc/>")
    service, _ = make_service(echo())
    with pytest.raises(MacroEnabledError):
        service.audit(buffer.getvalue())


def test_logs_carry_metrics_but_never_document_content(corpus: tuple[Path, Path]) -> None:
    service, _ = make_service(echo())
    data = (corpus[0] / "clean" / "clean-01.docx").read_bytes()
    parsed = parse_docx(data)
    with capture_logs() as logs:
        report = service.audit(data, request_id="req-42")
    done = [entry for entry in logs if entry["event"] == "audit_done"]
    assert len(done) == 1
    entry = done[0]
    assert entry["request_id"] == "req-42"
    assert entry["file_sha256"] == report.meta.sha256
    assert entry["size_bytes"] == len(data)
    assert set(entry["node_ms"]) >= {"validate", "parse", "rule_checks", "merge", "build_report"}
    assert {"findings_by_severity", "llm_calls", "llm_tokens", "degraded", "mode"} <= set(entry)
    rendered = json.dumps(logs, default=str)
    for block in parsed.blocks:
        if len(block.text) >= 12:
            assert block.text not in rendered
    for image in parsed.images:
        assert (image.alt_text or "zzz-none") not in rendered


def test_request_ids_are_generated_and_unique(corpus: tuple[Path, Path]) -> None:
    service, _ = make_service(echo())
    data = (corpus[0] / "clean" / "clean-01.docx").read_bytes()
    with capture_logs() as logs:
        service.audit(data, AuditOptions(mode="rules_only"))
        service.audit(data, AuditOptions(mode="rules_only"))
    ids = [e["request_id"] for e in logs if e["event"] == "audit_done"]
    assert len(set(ids)) == 2


def test_the_real_sandbox_path_gives_the_same_report(corpus: tuple[Path, Path]) -> None:
    """Default wiring: parsing and image extraction both run in the subprocess sandbox."""
    settings = Settings(_env_file=None, llm_budget_per_doc=50)
    fake, model = provider(echo())
    checker = LlmChecker([fake], settings, limiters=no_wait_limiters(), sleep=lambda _: None)
    sandboxed = AuditService(settings, checker=checker)
    in_process, _ = make_service(echo())
    data = (corpus[0] / "clean" / "clean-01.docx").read_bytes()  # contains one image
    assert stable(sandboxed.audit(data)) == stable(in_process.audit(data))
    assert any(
        block.get("type") == "image_url"
        for call in model.calls
        for block in (call[-1].content if isinstance(call[-1].content, list) else [])
    )
