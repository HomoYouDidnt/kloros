"""Utility CLI for orchestrating the RZERO self-improvement sandbox."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any, Dict, Iterable, List

import yaml

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from kloROS_accuracy_stack.rzero.evaluator import evaluate_candidate  # noqa: E402
from kloROS_accuracy_stack.rzero.gatekeeper import gatekeep  # noqa: E402
from kloROS_accuracy_stack.rzero.proposer import propose_candidates  # noqa: E402

PLAN_STEPS: List[str] = [
    "Load accuracy configuration and verify RZERO is enabled.",
    "Generate candidate knob profiles via rzero/proposer.py.",
    "Evaluate each candidate offline and emit JSON reports.",
    "Gatekeep reports against win criteria before staging.",
]


def load_config(path: Path) -> Dict[str, Any]:
    with path.open("r", encoding="utf-8") as handle:
        return yaml.safe_load(handle)


def rzero_enabled(cfg: Dict[str, Any]) -> bool:
    return bool(cfg.get("self_improve", {}).get("rzero_enabled", False))


def print_plan() -> None:
    print("RZERO pipeline plan:")
    for idx, step in enumerate(PLAN_STEPS, start=1):
        print(f"  {idx}. {step}")


def ensure_enabled(cfg: Dict[str, Any], *, quiet: bool = False) -> bool:
    if rzero_enabled(cfg):
        return True
    if not quiet:
        print("RZERO is disabled in config (self_improve.rzero_enabled=false); exiting.")
    return False


def handle_propose(cfg: Dict[str, Any], out_dir: Path, count: int) -> None:
    knobs = cfg.get("self_improve", {}).get("knobs", {})
    candidates = propose_candidates(cfg, knobs, n=count)
    out_dir.mkdir(parents=True, exist_ok=True)
    out_path = out_dir / "candidates.jsonl"
    with out_path.open("w", encoding="utf-8") as handle:
        for candidate in candidates:
            handle.write(json.dumps(candidate) + "\n")
    print(f"Wrote {len(candidates)} candidates to {out_path}")


def _iter_candidate_profiles(path: Path) -> Iterable[Dict[str, Any]]:
    if path.is_file():
        text = path.read_text(encoding="utf-8").strip()
        if path.suffix in {".json", ".jsonl"}:
            if path.suffix == ".jsonl":
                for line in text.splitlines():
                    if line.strip():
                        yield json.loads(line)
            else:
                payload = json.loads(text)
                if isinstance(payload, list):
                    yield from payload
                else:
                    yield payload
        else:
            try:
                yield yaml.safe_load(text)
            except yaml.YAMLError as exc:  # pragma: no cover - best-effort parse
                raise ValueError(f"Unable to parse candidate file {path}") from exc
    else:
        raise FileNotFoundError(path)


def handle_evaluate(cfg: Dict[str, Any], candidates_path: Path, out_dir: Path) -> List[Path]:
    out_dir.mkdir(parents=True, exist_ok=True)
    emitted: List[Path] = []
    for profile in _iter_candidate_profiles(candidates_path):
        report_path = evaluate_candidate(profile, str(out_dir))
        emitted.append(Path(report_path))
    print(f"Evaluated {len(emitted)} candidates -> reports under {out_dir}")
    return emitted


def handle_gatekeep(cfg: Dict[str, Any], reports: Iterable[Path]) -> List[Path]:
    criteria = cfg.get("self_improve", {}).get("win_criteria", {})
    report_list = list(reports)
    promoted: List[Path] = []
    for report_path in report_list:
        data = json.loads(report_path.read_text(encoding="utf-8"))
        if gatekeep(data, criteria):
            promoted.append(report_path)
    print(f"Gatekeeper accepted {len(promoted)} of {len(report_list)} reports")
    return promoted


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "command",
        nargs="?",
        choices=["propose", "evaluate", "gatekeep"],
        default="propose",
        help="RZERO stage to execute",
    )
    parser.add_argument("--config", default="kloROS_accuracy_stack/config/accuracy.yml")
    parser.add_argument("--out", default="out/rzero")
    parser.add_argument("--count", type=int, default=4, help="Number of candidates to propose")
    parser.add_argument("--candidates", type=Path, help="Path to candidate JSON/JSONL/YAML")
    parser.add_argument("--reports", type=Path, help="Directory of evaluation reports")
    parser.add_argument("--dry-run", action="store_true", help="Print pipeline plan and exit")
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    cfg_path = Path(args.config)
    cfg = load_config(cfg_path)

    if args.dry_run:
        print_plan()
        return

    if not ensure_enabled(cfg):
        return

    out_dir = Path(args.out)

    if args.command == "propose":
        handle_propose(cfg, out_dir / "candidates", args.count)
    elif args.command == "evaluate":
        if not args.candidates:
            raise SystemExit("--candidates path required for evaluate stage")
        handle_evaluate(cfg, args.candidates, out_dir / "reports")
    elif args.command == "gatekeep":
        reports_dir = args.reports or (out_dir / "reports")
        if not Path(reports_dir).exists():
            raise SystemExit("--reports directory missing")
        report_paths = list(Path(reports_dir).glob("*.json"))
        if not report_paths:
            raise SystemExit("No report JSON files found")
        winners = handle_gatekeep(cfg, report_paths)
        if winners:
            ledger = out_dir / "promoted.json"
            ledger.write_text(
                json.dumps([str(path) for path in winners], indent=2),
                encoding="utf-8",
            )
            print(f"Wrote promotion ledger to {ledger}")


if __name__ == "__main__":
    main()
