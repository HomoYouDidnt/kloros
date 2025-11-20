#!/usr/bin/env python3
"""
Emit PHASE completion signal for orchestrator consumption.

Called by spica-phase-test.service after pytest completes.
Writes dual signal: /tmp marker + ~/.kloros/signals JSON payload.
"""
import os
import json
import time
import hashlib
from pathlib import Path

HOME = Path("/home/kloros")
OUT = HOME / "out" / "test_runs"
SIGNAL_HOME = HOME / ".kloros" / "signals"
SIGNAL_HOME.mkdir(parents=True, exist_ok=True)

# Derive epoch_id as the most recent overnight run dir
runs = sorted(OUT.glob("overnight-*"), key=lambda p: p.stat().st_mtime, reverse=True)
if not runs:
    raise SystemExit("No overnight-* runs found in /home/kloros/out/test_runs")
epoch_dir = runs[0]
epoch_id = epoch_dir.name  # e.g., overnight-20251029

# Prefer a consolidated report if you have one; else stitch a stable file
# Here we pick the main PHASE report jsonl if present, else hash the directory listing
candidates = list(epoch_dir.glob("phase*_report.json")) + list(epoch_dir.glob("phase_report.jsonl"))
if candidates:
    report_path = max(candidates, key=lambda p: p.stat().st_mtime)
else:
    # Fallback: create a synthetic report index to hash
    report_path = epoch_dir / "phase_report.index"
    listing = sorted([p.name for p in epoch_dir.glob("*")])
    report_path.write_text("\n".join(listing))

report_path = report_path.resolve()
sha = hashlib.sha256(report_path.read_bytes()).hexdigest()

# Touch file in /tmp (existence marker)
touch = Path(f"/tmp/klr_phase_complete_{epoch_id}")
touch.touch()

# Protected JSON payload in ~/.kloros/signals
payload = {
    "epoch_id": epoch_id,
    "ts": int(time.time()),
    "report": str(report_path),
    "sha256": sha,
}
payload_file = SIGNAL_HOME / f"klr_phase_complete_{epoch_id}.json"
tmp = payload_file.with_suffix(".tmp")
tmp.write_text(json.dumps(payload))
os.chmod(tmp, 0o640)
os.replace(tmp, payload_file)

print(f"[emit_phase_signal] signaled {epoch_id} sha={sha[:8]} file={report_path}")
