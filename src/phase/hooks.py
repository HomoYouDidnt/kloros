#!/usr/bin/env python3
"""
PHASE hooks for D-REAM integration.
"""
import subprocess
import os
import sys

# Add parent directory to path for imports
sys.path.insert(0, "/home/kloros")

from src.dream.config import load_cfg
from src.dream.schema import Candidate, CandidatePack, Lineage
from src.dream.io import read_phase_results, write_candidate_pack
from src.dream.admit import judge_and_admit
from src.dream.report import emit_report

def on_phase_window_complete(episode_id: str):
    """
    Called when a PHASE test window completes.

    Args:
        episode_id: The PHASE episode/window identifier
    """
    # 1) Transform existing PHASE report → dream/phase_raw/<episode>.jsonl
    env = dict(os.environ, DREAM_ARTIFACTS=os.environ.get("DREAM_ARTIFACTS", "artifacts/dream"))
    subprocess.check_call([
        sys.executable, "-m", "src.phase.bridge_phase_to_dream", episode_id
    ], env=env)

    # Guard: Only proceed if bridged JSONL exists and has content
    phase_raw_path = os.path.join(env["DREAM_ARTIFACTS"], "phase_raw", f"{episode_id}.jsonl")
    if not os.path.exists(phase_raw_path):
        print(f"Warning: No phase_raw data for {episode_id}, skipping D-REAM evaluation")
        return

    with open(phase_raw_path) as f:
        lines = f.readlines()
    if len(lines) < 1:
        print(f"Warning: Empty phase_raw data for {episode_id}, skipping D-REAM evaluation")
        return

    # 2) Load config
    cfg = load_cfg()

    # 3) Read bridged PHASE results
    raw = read_phase_results(episode_id)
    if not raw:
        print(f"No PHASE results for episode {episode_id}")
        return  # nothing to do

    # 4) Convert to candidates
    cands = [
        Candidate(
            id=r["id"],
            domain=r.get("domain", "unknown"),
            params=r.get("params", {}),
            metrics=r.get("metrics", {}),
            notes=r.get("notes", "")
        )
        for r in raw
    ]

    # 5) Create lineage
    lin = Lineage(
        origin="phase",
        episode_id=episode_id,
        generator_sha=cfg.runtime.generator_sha,
        judge_sha=cfg.runtime.judge_sha
    )

    # 6) Create pack
    pack = CandidatePack.new(cands, lin)
    write_candidate_pack(pack)

    # 7) Judge and admit
    admitted, rejected = judge_and_admit(cfg, pack)

    # 8) Emit report
    emit_report(pack, len(admitted), len(rejected), anchors={"kl": None})

    print(f"D-REAM completed: {len(admitted)} admitted, {len(rejected)} rejected")
    print(f"Run ID: {pack.run_id}")
