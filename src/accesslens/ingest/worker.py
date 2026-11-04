"""Child-process entry point: reads a .docx or .pptx on stdin, writes JSON on stdout.

argv: ``memory_mb mode limits_json [max_image_bytes]``. Modes: ``parse`` writes ParsedDocument
JSON; ``images`` writes {image id: base64 bytes}, skipping images over the byte cap.

The child imports as little as possible (no pydantic-settings, no asyncio): its start-up cost is
paid on every audit. Run only through ``sandbox``. Failures exit non-zero with no output so no
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
        _limit_memory(int(argv[1]))
        mode = argv[2]
        import json

        from accesslens.ingest.validate import ValidationLimits, validate_upload

        data = sys.stdin.buffer.read()
        # Defence in depth: the sandbox does not trust its caller, so it validates again.
        _, kind = validate_upload(data, limits=ValidationLimits(**json.loads(argv[3])))
        if mode == "images":
            import base64

            if kind == "pptx":
                from accesslens.ingest.parse_pptx import extract_image_blobs
            else:
                from accesslens.ingest.parse_docx import extract_image_blobs

            cap = int(argv[4])
            blobs = {
                key: base64.b64encode(blob).decode("ascii")
                for key, blob in extract_image_blobs(data).items()
                if len(blob) <= cap
            }
            sys.stdout.buffer.write(json.dumps(blobs).encode("utf-8"))
        else:
            if kind == "pptx":
                from accesslens.ingest.parse_pptx import parse_pptx as parse
            else:
                from accesslens.ingest.parse_docx import parse_docx as parse

            sys.stdout.buffer.write(parse(data).model_dump_json().encode("utf-8"))
    except Exception:
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
