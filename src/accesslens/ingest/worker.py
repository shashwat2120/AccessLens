"""Child-process entry point: reads a .docx on stdin, writes ParsedDocument JSON on stdout.

Run only through ``sandbox.parse_in_sandbox``. Failures exit non-zero with no output so no
stack trace (and therefore no document content) can leak.
"""

import sys


def _limit_memory(megabytes: int) -> None:
    if sys.platform == "win32":
        return  # no setrlimit; the parent's wall-clock timeout still applies
    import resource

    limit = megabytes * 1024 * 1024
    resource.setrlimit(resource.RLIMIT_AS, (limit, limit))


def main(argv: list[str]) -> int:
    try:
        _limit_memory(int(argv[1]) if len(argv) > 1 else 512)
        from accesslens.ingest.parse_docx import parse_docx
        from accesslens.ingest.validate import validate_docx

        data = sys.stdin.buffer.read()
        validate_docx(data)  # defence in depth: the sandbox does not trust its caller
        sys.stdout.buffer.write(parse_docx(data).model_dump_json().encode("utf-8"))
    except Exception:
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
