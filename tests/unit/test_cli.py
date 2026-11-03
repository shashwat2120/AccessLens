import json
import zipfile
from pathlib import Path

import pytest

from accesslens.cli import EXIT_ERROR, EXIT_ISSUES, EXIT_OK, main


def run(args: list[str], capsys: pytest.CaptureFixture[str]) -> tuple[int, str, str]:
    code = main(args)
    captured = capsys.readouterr()
    return code, captured.out, captured.err


def test_json_to_stdout_and_exit_1_when_critical_issues_exist(
    corpus: tuple[Path, Path], capsys: pytest.CaptureFixture[str]
) -> None:
    path = corpus[0] / "synthetic" / "syn-01.docx"  # missing alt text: critical
    code, out, err = run(["audit", str(path), "--rules-only"], capsys)
    assert code == EXIT_ISSUES
    report = json.loads(out)
    assert report["mode"] == "rules_only"
    assert {f["rule_id"] for f in report["findings"]} >= {"IMG-001"}
    assert "score" in err


def test_clean_document_exits_0(
    corpus: tuple[Path, Path], capsys: pytest.CaptureFixture[str]
) -> None:
    code, out, err = run(
        ["audit", str(corpus[0] / "clean" / "clean-01.docx"), "--rules-only"], capsys
    )
    assert code == EXIT_OK
    assert json.loads(out)["findings"] == []
    assert "no issues found" in err


def test_only_low_and_medium_issues_exit_0(
    corpus: tuple[Path, Path], capsys: pytest.CaptureFixture[str]
) -> None:
    medium_only = corpus[0] / "synthetic" / "syn-13.docx"  # DOC-002 and LNK-001, both medium
    code, _, _ = run(["audit", str(medium_only), "--rules-only"], capsys)
    assert code == EXIT_OK


def test_writes_html_and_xlsx_files(
    corpus: tuple[Path, Path], tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    source = str(corpus[0] / "synthetic" / "syn-01.docx")
    out_dir = tmp_path / "reports"
    for fmt, suffix in (("html", ".html"), ("xlsx", ".xlsx"), ("json", ".json")):
        code, out, _ = run(
            ["audit", source, "--rules-only", "--format", fmt, "--out", str(out_dir)], capsys
        )
        assert code == EXIT_ISSUES
        assert out == ""
        assert (out_dir / f"syn-01.report{suffix}").exists()
    assert "<html" in (out_dir / "syn-01.report.html").read_text(encoding="utf-8")
    assert zipfile.is_zipfile(out_dir / "syn-01.report.xlsx")


def test_folder_audit_needs_out_and_writes_one_report_each(
    corpus: tuple[Path, Path], tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    folder = corpus[0] / "clean"
    code, _, err = run(["audit", str(folder), "--rules-only"], capsys)
    assert code == EXIT_ERROR
    assert "--out" in err
    out_dir = tmp_path / "out"
    code, _, _ = run(["audit", str(folder), "--rules-only", "--out", str(out_dir)], capsys)
    assert code == EXIT_OK
    assert len(list(out_dir.glob("*.report.json"))) == 5


def test_xlsx_to_stdout_is_refused(
    corpus: tuple[Path, Path], capsys: pytest.CaptureFixture[str]
) -> None:
    code, _, err = run(
        ["audit", str(corpus[0] / "clean" / "clean-01.docx"), "--format", "xlsx"], capsys
    )
    assert code == EXIT_ERROR
    assert "--out" in err


def test_errors_exit_2_without_leaking_details(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    bad = tmp_path / "bad.docx"
    bad.write_bytes(b"not a word document")
    code, out, err = run(["audit", str(bad), "--rules-only"], capsys)
    assert code == EXIT_ERROR
    assert out == ""
    assert "invalid_file" in err
    assert "Traceback" not in err
    code, _, err = run(["audit", str(tmp_path / "missing.docx")], capsys)
    assert code == EXIT_ERROR
    assert "no .docx files found" in err


def test_target_grade_is_validated(
    corpus: tuple[Path, Path], capsys: pytest.CaptureFixture[str]
) -> None:
    path = str(corpus[0] / "clean" / "clean-01.docx")
    code, _, err = run(["audit", path, "--rules-only", "--target-grade", "40"], capsys)
    assert code == EXIT_ERROR
    assert "between 1 and 18" in err
    code, out, _ = run(["audit", path, "--rules-only", "--target-grade", "6"], capsys)
    assert code == EXIT_OK
    assert json.loads(out)["findings"] == []
