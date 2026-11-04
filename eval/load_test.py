"""Concurrent load test for the API (docs/06-ROADMAP.md, Phase 7).

    python eval/load_test.py --url http://127.0.0.1:8000 --key <api key> \\
        --file eval/corpus/synthetic/syn-01.docx --concurrency 10 --requests 50

Sends rules-only audits, so it spends no AI quota. Reports success count and latency
percentiles; the target is p95 <= 3 s for rules-only (docs/05-EVALUATION.md §4).
"""

from __future__ import annotations

import argparse
import statistics
import sys
import time
from collections.abc import Callable
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from typing import Any

import httpx

P95_TARGET_S = 3.0


def percentile(values: list[float], pct: float) -> float:
    ordered = sorted(values)
    return ordered[min(len(ordered) - 1, round(pct / 100 * (len(ordered) - 1)))]


def run_load(
    send: Callable[[bytes], Any], data: bytes, *, concurrency: int, requests: int
) -> dict[str, Any]:
    """Call ``send(data)`` ``requests`` times across ``concurrency`` threads."""

    def one(_: int) -> tuple[bool, float]:
        started = time.perf_counter()
        try:
            ok = send(data).status_code == 200
        except Exception:
            ok = False
        return ok, time.perf_counter() - started

    wall = time.perf_counter()
    with ThreadPoolExecutor(max_workers=concurrency) as pool:
        results = list(pool.map(one, range(requests)))
    elapsed = time.perf_counter() - wall
    latencies = [seconds for ok, seconds in results if ok]
    return {
        "requests": requests,
        "concurrency": concurrency,
        "succeeded": len(latencies),
        "failed": requests - len(latencies),
        "wall_s": round(elapsed, 2),
        "throughput_per_s": round(requests / elapsed, 2) if elapsed else 0.0,
        "p50_s": round(statistics.median(latencies), 3) if latencies else None,
        "p95_s": round(percentile(latencies, 95), 3) if latencies else None,
        "max_s": round(max(latencies), 3) if latencies else None,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--url", default="http://127.0.0.1:8000")
    parser.add_argument("--key", required=True)
    parser.add_argument("--file", type=Path, required=True)
    parser.add_argument("--concurrency", type=int, default=10)
    parser.add_argument("--requests", type=int, default=50)
    args = parser.parse_args()

    data = args.file.read_bytes()
    with httpx.Client(base_url=args.url, timeout=60) as client:

        def send(payload: bytes) -> httpx.Response:
            return client.post(
                "/v1/audits",
                files={"file": ("document.docx", payload)},
                data={"mode": "rules_only"},
                headers={"X-API-Key": args.key},
            )

        result = run_load(send, data, concurrency=args.concurrency, requests=args.requests)
    for name, value in result.items():
        sys.stdout.write(f"{name}: {value}\n")
    healthy = result["failed"] == 0 and (result["p95_s"] or 0) <= P95_TARGET_S
    sys.stdout.write(f"{'PASS' if healthy else 'FAIL'}: p95 target {P95_TARGET_S} s\n")
    return 0 if healthy else 1


if __name__ == "__main__":
    sys.exit(main())
