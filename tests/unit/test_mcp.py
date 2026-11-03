import asyncio
import json
import os
import shutil
from pathlib import Path
from typing import Any

import pytest

from accesslens.config import Settings
from accesslens.errors import InvalidRequestError
from accesslens.mcp_server.server import (
    TOP_FINDINGS,
    create_server,
    resolve_allowed_path,
    summarize,
)
from accesslens.models import DocMeta, Finding, Location, Report, Severity, Source, WcagLevel
from fakes import service_for


@pytest.fixture
def inbox(tmp_path: Path, corpus: tuple[Path, Path]) -> Path:
    folder = tmp_path / "inbox"
    (folder / "sub").mkdir(parents=True)
    shutil.copy(corpus[0] / "synthetic" / "syn-01.docx", folder / "a.docx")
    shutil.copy(corpus[0] / "clean" / "clean-01.docx", folder / "sub" / "b.docx")
    (folder / "notes.txt").write_text("hi", encoding="utf-8")
    shutil.copy(corpus[0] / "clean" / "clean-01.docx", tmp_path / "secret.docx")
    return folder


def payload(result: Any) -> Any:
    return json.loads(result.content[0].text)


def call(server: Any, tool: str, args: dict[str, Any]) -> Any:
    return asyncio.run(server.call_tool(tool, args))


def test_paths_inside_the_allowed_folder_resolve(inbox: Path) -> None:
    assert resolve_allowed_path("a.docx", str(inbox)) == (inbox / "a.docx").resolve()
    assert resolve_allowed_path("sub/b.docx", str(inbox)).name == "b.docx"
    assert resolve_allowed_path(str(inbox / "a.docx"), str(inbox)).name == "a.docx"


@pytest.mark.parametrize(
    "raw",
    ["../secret.docx", "sub/../../secret.docx", "notes.txt", "missing.docx", "sub", ""],
)
def test_traversal_wrong_types_and_missing_files_are_refused(inbox: Path, raw: str) -> None:
    with pytest.raises(InvalidRequestError):
        resolve_allowed_path(raw, str(inbox))


def test_absolute_paths_outside_and_prefix_tricks_are_refused(inbox: Path) -> None:
    with pytest.raises(InvalidRequestError):
        resolve_allowed_path(str(inbox.parent / "secret.docx"), str(inbox))
    sibling = inbox.parent / "inbox-evil"
    sibling.mkdir()
    shutil.copy(inbox / "a.docx", sibling / "x.docx")
    with pytest.raises(InvalidRequestError):  # shares a name prefix, but is not inside
        resolve_allowed_path(str(sibling / "x.docx"), str(inbox))


def test_symlinks_pointing_outside_are_refused(inbox: Path) -> None:
    link = inbox / "link.docx"
    try:
        os.symlink(inbox.parent / "secret.docx", link)
    except (OSError, NotImplementedError):
        pytest.skip("symlinks need extra privileges on this machine")
    with pytest.raises(InvalidRequestError):
        resolve_allowed_path("link.docx", str(inbox))


def test_no_configured_folder_means_no_file_access(inbox: Path) -> None:
    with pytest.raises(InvalidRequestError):
        resolve_allowed_path("a.docx", "")


def test_server_registers_exactly_the_three_tools(inbox: Path) -> None:
    cfg = Settings(_env_file=None, mcp_allowed_dir=str(inbox))
    server = create_server(cfg, service_for(cfg))
    names = {t.name for t in asyncio.run(server.list_tools())}
    assert names == {"audit_docx", "list_rules", "explain_rule"}


def test_audit_tool_returns_a_bounded_summary(inbox: Path) -> None:
    cfg = Settings(_env_file=None, mcp_allowed_dir=str(inbox))
    server = create_server(cfg, service_for(cfg))
    result = payload(call(server, "audit_docx", {"path": "a.docx", "rules_only": True}))
    assert result["mode"] == "rules_only"
    assert result["findings_by_severity"]["critical"] >= 1
    assert result["shown_findings"] == len(result["findings"]) <= TOP_FINDINGS
    assert all(len(f["snippet"]) <= 120 for f in result["findings"])


def test_audit_tool_refuses_outside_paths_without_leaking(inbox: Path) -> None:
    cfg = Settings(_env_file=None, mcp_allowed_dir=str(inbox))
    server = create_server(cfg, service_for(cfg))
    result = payload(call(server, "audit_docx", {"path": "../secret.docx"}))
    assert result["error"] == "invalid_request"
    assert str(inbox.parent) not in json.dumps(result)
    bad = inbox / "bad.docx"
    bad.write_bytes(b"not a docx")
    assert payload(call(server, "audit_docx", {"path": "bad.docx"}))["error"] == "invalid_file"


def test_rule_tools(inbox: Path) -> None:
    cfg = Settings(_env_file=None, mcp_allowed_dir=str(inbox))
    server = create_server(cfg, service_for(cfg))
    explained = payload(call(server, "explain_rule", {"rule_id": "img-001"}))
    assert explained["id"] == "IMG-001"
    assert explained["wcag_url"].startswith("https://www.w3.org/")
    assert explained["how_to_fix"]
    assert payload(call(server, "explain_rule", {"rule_id": "NOPE"}))["error"] == "invalid_request"
    listed = call(server, "list_rules", {})
    entries = (
        listed.structured_content.get("result")
        if getattr(listed, "structured_content", None)
        else [json.loads(c.text) for c in listed.content]
    )
    assert len(entries) == 26


def test_summary_is_capped_at_the_top_25_findings() -> None:
    findings = [
        Finding(
            id=f"IMG-001-b{i:04d}",
            rule_id="IMG-001",
            title="t",
            severity=Severity.CRITICAL,
            wcag_criterion="1.1.1",
            wcag_level=WcagLevel.A,
            location=Location(block_id=f"b{i:04d}", block_order=i, snippet="x" * 120),
            message="m",
            suggestion="s",
            source=Source.RULE,
        )
        for i in range(40)
    ]
    report = Report(
        generated_at="2026-11-03T00:00:00Z",  # type: ignore[arg-type]
        meta=DocMeta(
            title="t",
            language="en",
            word_count=1,
            paragraph_count=1,
            image_count=0,
            table_count=0,
            sha256="0" * 64,
        ),
        score=0,
        counts={Severity.CRITICAL: 40, Severity.HIGH: 0, Severity.MEDIUM: 0, Severity.LOW: 0},
        findings=findings,
        llm=None,
        mode="rules_only",
        warnings=[],
    )
    summary = summarize(report)
    assert summary["total_findings"] == 40
    assert summary["shown_findings"] == len(summary["findings"]) == TOP_FINDINGS
