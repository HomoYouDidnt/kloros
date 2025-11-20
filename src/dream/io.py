import os
import json
from typing import List, Dict
from .schema import CandidatePack, Candidate, Lineage

BASE = os.environ.get("DREAM_ARTIFACTS", "artifacts/dream")

def _p(*xs):
    return os.path.join(BASE, *xs)

def read_phase_results(episode_id: str) -> List[Dict]:
    """Read PHASE results that have been bridged to D-REAM format."""
    path = _p("phase_raw", f"{episode_id}.jsonl")
    if not os.path.exists(path):
        return []
    with open(path, "r", encoding="utf-8") as f:
        return [json.loads(l) for l in f]

def write_candidate_pack(pack: CandidatePack):
    """Write candidate pack to artifacts."""
    d = _p("candidates", pack.run_id)
    os.makedirs(d, exist_ok=True)
    with open(os.path.join(d, "pack.json"), "w") as f:
        json.dump({
            "run_id": pack.run_id,
            "candidates": [c.__dict__ for c in pack.candidates],
            "lineage": pack.lineage.__dict__,
            "summary": pack.summary
        }, f, indent=2)

def write_admitted(run_id: str, cs: List[Candidate], lin: Lineage):
    """Write admitted candidates."""
    d = _p("candidates", run_id)
    with open(os.path.join(d, "admitted.json"), "w") as f:
        json.dump({
            "lineage": lin.__dict__,
            "admitted": [c.__dict__ for c in cs]
        }, f, indent=2)

def write_quarantine(run_id: str, cs: List[Candidate], lin: Lineage):
    """Write quarantined candidates."""
    d = _p("candidates", run_id)
    with open(os.path.join(d, "quarantine.json"), "w") as f:
        json.dump({
            "lineage": lin.__dict__,
            "quarantine": [c.__dict__ for c in cs]
        }, f, indent=2)

def write_mix(mix: Dict, lin: Lineage):
    """Write training mix."""
    d = _p("mixes", lin.episode_id)
    os.makedirs(d, exist_ok=True)
    with open(os.path.join(d, "mix.json"), "w") as f:
        json.dump(mix, f, indent=2)

def write_report_files(pack: CandidatePack, report: Dict):
    """Write report markdown and JSON."""
    d = _p("reports", pack.run_id)
    os.makedirs(d, exist_ok=True)
    with open(os.path.join(d, "REPORT.md"), "w") as f:
        f.write(f"# D-REAM Run {pack.run_id}\n")
        f.write(f"Admitted: {report['scores']['admitted']}, Rejected: {report['scores']['rejected']}\n")
    with open(os.path.join(d, "report.json"), "w") as f:
        json.dump(report, f, indent=2)
