"""Command line interface (TRD §7). A thin wrapper: all logic is in ``AuditService``.

    accesslens audit <path|dir> [--rules-only] [--format json|html|xlsx] [--out DIR]
                                [--target-grade N]

Exit codes: 0 nothing critical or high, 1 critical or high issues found, 2 error.
"""

import argparse
import logging
import sys
from pathlib import Path

from accesslens.errors import AccessLensError
from accesslens.logging import configure_logging
from accesslens.models import AuditOptions, Report, Severity
from accesslens.report.html import render_html
from accesslens.report.xlsx import render_xlsx
from accesslens.service import AuditService

EXIT_OK, EXIT_ISSUES, EXIT_ERROR = 0, 1, 2
_SUFFIX = {"json": ".json", "html": ".html", "xlsx": ".xlsx"}


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="accesslens", description=__doc__.splitlines()[0])
    commands = parser.add_subparsers(dest="command", required=True)
    audit = commands.add_parser("audit", help="audit a .docx file or a folder of them")
    audit.add_argument("path", type=Path)
    audit.add_argument("--rules-only", action="store_true", help="send nothing to any AI service")
    audit.add_argument("--format", choices=sorted(_SUFFIX), default="json")
    audit.add_argument("--out", type=Path, help="folder for report files (required for folders)")
    audit.add_argument("--target-grade", type=int, help="reading grade target (1-18)")
    audit.add_argument("-v", "--verbose", action="store_true", help="show service logs")
    return parser


def _collect(path: Path) -> list[Path]:
    if path.is_dir():
        return sorted(p for p in path.rglob("*.docx") if p.is_file() and not p.is_symlink())
    return [path]


def _render(report: Report, fmt: str) -> bytes:
    if fmt == "html":
        return render_html(report).encode("utf-8")
    if fmt == "xlsx":
        return render_xlsx(report)
    return (report.model_dump_json(indent=2) + "\n").encode("utf-8")


def _summary(report: Report) -> str:
    counts = ", ".join(f"{n} {sev.value}" for sev, n in report.counts.items() if n)
    return f"score {report.score}/100" + (f" ({counts})" if counts else " (no issues found)")


def main(argv: list[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    configure_logging(logging.INFO if args.verbose else logging.WARNING)

    files = _collect(args.path)
    if not args.path.exists() or not files:
        sys.stderr.write(f"error: no .docx files found at {args.path}\n")
        return EXIT_ERROR
    if (len(files) > 1 or args.path.is_dir() or args.format == "xlsx") and args.out is None:
        sys.stderr.write("error: --out is required for folders and for xlsx output\n")
        return EXIT_ERROR

    try:
        options = AuditOptions(
            mode="rules_only" if args.rules_only else "full", target_grade=args.target_grade
        )
    except ValueError:
        sys.stderr.write("error: --target-grade must be between 1 and 18\n")
        return EXIT_ERROR

    service = AuditService()
    status = EXIT_OK
    for path in files:
        try:
            report = service.audit(path.read_bytes(), options)
        except AccessLensError as exc:
            sys.stderr.write(f"{path}: error ({exc.code}): {exc}\n")
            status = EXIT_ERROR
            continue
        except OSError:
            sys.stderr.write(f"{path}: error: could not read the file\n")
            status = EXIT_ERROR
            continue
        except Exception:
            sys.stderr.write(f"{path}: error: internal error\n")
            status = EXIT_ERROR
            continue

        sys.stderr.write(f"{path}: {_summary(report)}\n")
        payload = _render(report, args.format)
        if args.out is None:
            sys.stdout.buffer.write(payload)
        else:
            args.out.mkdir(parents=True, exist_ok=True)
            (args.out / f"{path.stem}.report{_SUFFIX[args.format]}").write_bytes(payload)
        if status == EXIT_OK and any(report.counts[s] for s in (Severity.CRITICAL, Severity.HIGH)):
            status = EXIT_ISSUES
    return status


if __name__ == "__main__":
    sys.exit(main())
