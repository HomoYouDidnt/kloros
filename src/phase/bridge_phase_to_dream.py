#!/usr/bin/env python3
"""
PHASE → D-REAM bridge: Transform phase_report.jsonl to D-REAM candidate format.
"""
import json
import os
import sys
import uuid
from datetime import datetime

ART = os.environ.get("DREAM_ARTIFACTS", "artifacts/dream")
PHASE_REPORT = "/home/kloros/src/phase/phase_report.jsonl"
EPISODE = sys.argv[1] if len(sys.argv) > 1 else datetime.utcnow().strftime("%Y%m%dT%H%M")

def _domain_for(test_id: str) -> str:
    """Map test_id to domain (naive mapping, refine as needed)."""
    test_lower = test_id.lower()
    if "asr" in test_lower or "tts" in test_lower:
        return "asr_tts"
    if "audio" in test_lower:
        return "audio"
    if "conversation" in test_lower:
        return "conversation"
    if "rag" in test_lower:
        return "rag_context"
    return "unknown"

def main():
    out_dir = os.path.join(ART, "phase_raw")
    os.makedirs(out_dir, exist_ok=True)
    out_path = os.path.join(out_dir, f"{EPISODE}.jsonl")

    if not os.path.exists(PHASE_REPORT):
        print(f"Warning: {PHASE_REPORT} not found, creating empty output", file=sys.stderr)
        open(out_path, "w").close()
        print(out_path)
        return

    with open(PHASE_REPORT, "r") as src, open(out_path, "w") as dst:
        for ln in src:
            r = json.loads(ln)
            # Build metrics dict with standard fields
            metrics = {
                # Adapt these keys to your report fields
                "score": float(r.get("score", r.get("pass_rate", 0))),
                "latency_ms": r.get("latency_ms"),
                "novelty": r.get("novelty", 0.0),
                "wer": r.get("wer", 0.0),
                "vad_boundary_ms": r.get("vad_boundary_ms", 0),
                "holdout_ok": r.get("holdout_ok", True),
            }

            # Preserve TTS-specific metrics if present
            if "tts_pesq" in r:
                metrics["tts_pesq"] = r["tts_pesq"]
            if "tts_stoi" in r:
                metrics["tts_stoi"] = r["tts_stoi"]

            cand = {
                "id": r.get("run_id") or r.get("test_id") or str(uuid.uuid4())[:8],
                "domain": _domain_for(r.get("test_id", "")),
                "params": r.get("params", {}),
                "metrics": metrics,
                "notes": r.get("notes", "")
            }
            dst.write(json.dumps(cand) + "\n")

    print(out_path)

if __name__ == "__main__":
    main()
