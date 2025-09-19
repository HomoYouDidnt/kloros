#!/usr/bin/env python
"""Tiny evaluation harness for the accuracy stack fixtures."""
from __future__ import annotations

import argparse
import csv
import json
from collections import Counter
from pathlib import Path
from typing import Any, Dict, List

import sys

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

import yaml

from kloROS_accuracy_stack.pipeline.qa import answer


def _normalise(text: str) -> str:
    return " ".join(text.lower().split())


def exact_match(pred: str, gold: str) -> float:
    return float(_normalise(pred) == _normalise(gold))


def f1_score(pred: str, gold: str) -> float:
    pred_tokens = Counter(_normalise(pred).split())
    gold_tokens = Counter(_normalise(gold).split())
    if not pred_tokens or not gold_tokens:
        return 0.0
    overlap = sum((pred_tokens & gold_tokens).values())
    precision = overlap / sum(pred_tokens.values())
    recall = overlap / sum(gold_tokens.values())
    if precision + recall == 0:
        return 0.0
    return 2 * precision * recall / (precision + recall)


def citation_hit(result: Dict[str, Any], record: Dict[str, Any]) -> float:
    expected = set(record.get("docs", []))
    cited = set(result.get("citations", []))
    if not expected:
        return 1.0
    return float(bool(expected & cited))


def run_eval(cfg_path: Path, qa_path: Path, out_dir: Path, limit: int) -> None:
    cfg = yaml.safe_load(cfg_path.read_text(encoding="utf-8"))
    records = [json.loads(line) for line in qa_path.read_text(encoding="utf-8").splitlines() if line]
    if limit:
        records = records[:limit]
    out_dir.mkdir(parents=True, exist_ok=True)

    rows: List[Dict[str, Any]] = []
    for record in records:
        result, trace = answer(record["q"], cfg)
        pred_answer = result.get("answer") or ""
        abstained = bool(result.get("abstained"))
        row = {
            "question": record["q"],
            "gold": record.get("a", ""),
            "answer": pred_answer,
            "abstained": abstained,
            "em": exact_match(pred_answer, record.get("a", "")),
            "f1": f1_score(pred_answer, record.get("a", "")),
            "citation_hit": citation_hit(result, record),
            "decode_mode": trace.get("decode_mode"),
        }
        rows.append(row)

    csv_path = out_dir / "eval_results.csv"
    md_path = out_dir / "eval_report.md"

    with csv_path.open("w", encoding="utf-8", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=list(rows[0].keys()) if rows else [])
        writer.writeheader()
        writer.writerows(rows)

    em_avg = sum(row["em"] for row in rows) / len(rows)
    f1_avg = sum(row["f1"] for row in rows) / len(rows)
    abstain_rate = sum(1 for row in rows if row["abstained"]) / len(rows)
    citation_rate = sum(row["citation_hit"] for row in rows) / len(rows)

    md_path.write_text(
        """# Tiny Evaluation Report

- Questions: {total}
- Exact Match: {em:.3f}
- F1 Score: {f1:.3f}
- Abstain Rate: {abstain:.3f}
- Citation Hit Rate: {cit:.3f}
""".format(
            total=len(rows), em=em_avg, f1=f1_avg, abstain=abstain_rate, cit=citation_rate
        ),
        encoding="utf-8",
    )


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--config", default="kloROS_accuracy_stack/config/accuracy.yml")
    parser.add_argument("--qa", default="kloROS_accuracy_stack/fixtures/mini/qa.jsonl")
    parser.add_argument("--out", default="out")
    parser.add_argument("--limit", type=int, default=0)
    args = parser.parse_args()

    run_eval(Path(args.config), Path(args.qa), Path(args.out), args.limit)


if __name__ == "__main__":
    main()
