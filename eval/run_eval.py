"""Rules-only evaluation against the answer key (docs/05-EVALUATION.md §3-§4).

Run ``python eval/generate_corpus.py`` first, then ``python eval/run_eval.py --check``.
Only rule-based rule ids are scored; LLM rules (IMG-003, LNK-003, TXT-006) are ignored here.
"""

from __future__ import annotations

import argparse
import csv
import datetime as dt
import json
import subprocess
import sys
from collections import defaultdict
from pathlib import Path
from typing import Any

from accesslens.ingest.parse_docx import parse_docx
from accesslens.ingest.parse_pptx import parse_pptx
from accesslens.ingest.validate import validate_upload
from accesslens.rules import REGISTRY, RuleConfig, run_rules

ROOT = Path(__file__).resolve().parent
TOLERANCE = 1  # block_order may be off by one (heading heuristics)
TARGETS = {"recall": 0.98, "precision": 0.95, "false_positives_per_clean_doc": 0.5}
FOLDERS = {"syn": "synthetic", "clean": "clean", "inj": "injection"}

Key = tuple[str, str]  # (doc_id, rule_id)


def load_expected(path: Path) -> dict[Key, list[int]]:
    expected: dict[Key, list[int]] = defaultdict(list)
    with path.open(encoding="utf-8", newline="") as fh:
        for row in csv.DictReader(fh):
            if row["expected"] == "true" and row["rule_id"] in REGISTRY:
                expected[(row["doc_id"], row["rule_id"])].append(int(row["block_order"]))
    return expected


def match(expected: list[int], predicted: list[int]) -> tuple[int, list[int], list[int]]:
    """One-to-one matching within TOLERANCE; returns (true positives, missed, spurious)."""
    unused = sorted(predicted)
    missed: list[int] = []
    hits = 0
    for order in sorted(expected):
        candidates = [p for p in unused if abs(p - order) <= TOLERANCE]
        if candidates:
            unused.remove(min(candidates, key=lambda p: abs(p - order)))
            hits += 1
        else:
            missed.append(order)
    return hits, missed, unused


def evaluate(corpus: Path, key_path: Path) -> dict[str, Any]:
    expected = load_expected(key_path)
    config = RuleConfig()
    predicted: dict[Key, list[int]] = defaultdict(list)
    doc_ids: list[str] = []
    for path in sorted([*corpus.rglob("*.docx"), *corpus.rglob("*.pptx")]):
        data = path.read_bytes()
        _, kind = validate_upload(data)
        parse = parse_pptx if kind == "pptx" else parse_docx
        findings, warnings = run_rules(parse(data), config)
        if warnings:
            raise SystemExit(f"{path.stem}: {warnings}")
        doc_ids.append(path.stem)
        for finding in findings:
            predicted[(path.stem, finding.rule_id)].append(finding.location.block_order)

    per_rule: dict[str, dict[str, int]] = defaultdict(lambda: {"tp": 0, "fn": 0, "fp": 0})
    misses: list[dict[str, Any]] = []
    spurious: list[dict[str, Any]] = []
    for key in sorted(set(expected) | set(predicted)):
        doc_id, rule_id = key
        hits, missed, extra = match(expected.get(key, []), predicted.get(key, []))
        per_rule[rule_id]["tp"] += hits
        per_rule[rule_id]["fn"] += len(missed)
        per_rule[rule_id]["fp"] += len(extra)
        misses += [{"doc": doc_id, "rule": rule_id, "block_order": o} for o in missed]
        spurious += [{"doc": doc_id, "rule": rule_id, "block_order": o} for o in extra]

    tp = sum(r["tp"] for r in per_rule.values())
    fn = sum(r["fn"] for r in per_rule.values())
    fp = sum(r["fp"] for r in per_rule.values())
    clean_docs = [d for d in doc_ids if d.startswith("clean-")]
    clean_fp = sum(1 for s in spurious if s["doc"].startswith("clean-"))
    metrics = {
        "recall": tp / (tp + fn) if tp + fn else 1.0,
        "precision": tp / (tp + fp) if tp + fp else 1.0,
        "false_positives_per_clean_doc": clean_fp / len(clean_docs) if clean_docs else 0.0,
    }
    return {
        "documents": len(doc_ids),
        "true_positives": tp,
        "false_negatives": fn,
        "false_positives": fp,
        "metrics": metrics,
        "per_rule": {
            rule_id: {
                **counts,
                "recall": counts["tp"] / (counts["tp"] + counts["fn"])
                if counts["tp"] + counts["fn"]
                else None,
                "precision": counts["tp"] / (counts["tp"] + counts["fp"])
                if counts["tp"] + counts["fp"]
                else None,
            }
            for rule_id, counts in sorted(per_rule.items())
        },
        "misses": misses,
        "spurious": spurious,
    }


def failed_targets(result: dict[str, Any]) -> list[str]:
    metrics = result["metrics"]
    failures = [
        f"recall {metrics['recall']:.1%} < {TARGETS['recall']:.0%}"
        if metrics["recall"] < TARGETS["recall"]
        else "",
        f"precision {metrics['precision']:.1%} < {TARGETS['precision']:.0%}"
        if metrics["precision"] < TARGETS["precision"]
        else "",
        f"false positives per clean doc {metrics['false_positives_per_clean_doc']:.2f} "
        f"> {TARGETS['false_positives_per_clean_doc']}"
        if metrics["false_positives_per_clean_doc"] > TARGETS["false_positives_per_clean_doc"]
        else "",
    ]
    return [f for f in failures if f]


def git_commit() -> str:
    try:
        return subprocess.run(
            ["git", "rev-parse", "HEAD"],  # noqa: S607
            capture_output=True,
            text=True,
            check=True,
            cwd=ROOT,
        ).stdout.strip()
    except (OSError, subprocess.CalledProcessError):
        return "unknown"


def render_markdown(result: dict[str, Any], meta: dict[str, Any]) -> str:
    m = result["metrics"]
    lines = [
        f"# Rules-only eval, {meta['date']}",
        "",
        f"Commit `{meta['commit']}` · {result['documents']} documents · LLM off",
        "",
        "| Metric | Result | Target |",
        "|---|---|---|",
        f"| Recall | {m['recall']:.1%} | >= {TARGETS['recall']:.0%} |",
        f"| Precision | {m['precision']:.1%} | >= {TARGETS['precision']:.0%} |",
        f"| False positives per clean doc | {m['false_positives_per_clean_doc']:.2f} "
        f"| <= {TARGETS['false_positives_per_clean_doc']} |",
        "",
        "| Rule | TP | FN | FP |",
        "|---|---|---|---|",
    ]
    lines += [f"| {r} | {c['tp']} | {c['fn']} | {c['fp']} |" for r, c in result["per_rule"].items()]
    return "\n".join(lines) + "\n"


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--corpus", type=Path, default=ROOT / "corpus")
    parser.add_argument("--key", type=Path, default=ROOT / "answer_key.csv")
    parser.add_argument("--out", type=Path, default=ROOT / "results")
    parser.add_argument("--check", action="store_true", help="exit 1 if a target is missed")
    args = parser.parse_args()

    if not any(args.corpus.rglob("*.docx")):
        print(f"No corpus at {args.corpus}; run: python eval/generate_corpus.py")
        return 2
    result = evaluate(args.corpus, args.key)
    meta = {"date": dt.date.today().isoformat(), "commit": git_commit(), "targets": TARGETS}
    args.out.mkdir(parents=True, exist_ok=True)
    stem = args.out / meta["date"]
    stem.with_suffix(".json").write_text(
        json.dumps({**meta, **result}, indent=2) + "\n", encoding="utf-8"
    )
    stem.with_suffix(".md").write_text(render_markdown(result, meta), encoding="utf-8")

    m = result["metrics"]
    print(
        f"recall {m['recall']:.1%} · precision {m['precision']:.1%} · "
        f"FP/clean doc {m['false_positives_per_clean_doc']:.2f}"
    )
    for item in result["misses"][:20]:
        print("MISSED  ", item)
    for item in result["spurious"][:20]:
        print("SPURIOUS", item)
    failures = failed_targets(result)
    for failure in failures:
        print("FAIL:", failure)
    return 1 if args.check and failures else 0


if __name__ == "__main__":
    sys.exit(main())
