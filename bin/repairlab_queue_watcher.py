#!/usr/bin/env python3
"""
RepairLab Queue Watcher: Monitor handoffs from ToolGen and trigger repairs.

Polls /tmp/repairlab_queue for handoff files from ToolGen and invokes
RepairLab agent to attempt repairs. Tracks success/failure for analytics.
"""
import json
import subprocess
import time
import pathlib
import os
import sys

QUEUE = pathlib.Path("/tmp/repairlab_queue")
PROCESSED = QUEUE / "processed"
LOGDIR = pathlib.Path("/home/kloros/logs/repairlab_watcher")

# Create directories
LOGDIR.mkdir(parents=True, exist_ok=True)
PROCESSED.mkdir(parents=True, exist_ok=True)


def log_append(logfile: pathlib.Path, msg: str):
    """Append message to log file."""
    with open(logfile, "a", encoding="utf-8") as fp:
        fp.write(msg)


def run_repair(handoff_path: pathlib.Path) -> tuple[bool, dict]:
    """
    Process a single handoff file and attempt repair.

    Args:
        handoff_path: Path to handoff JSON file

    Returns:
        Tuple of (success, agent_result_dict)
    """
    try:
        meta = json.loads(handoff_path.read_text())
    except Exception as e:
        log_append(LOGDIR / "error.log", f"[{time.ctime()}] Bad JSON {handoff_path}: {e}\n")
        return False, {}

    bundle = meta["bundle_dir"]
    spec_path = meta.get("spec_path", "")

    log_msg = (
        f"[{time.ctime()}] Processing handoff: {handoff_path.name}\n"
        f"  Bundle: {bundle}\n"
        f"  Spec: {spec_path}\n"
        f"  Reason: {meta.get('reason', 'unknown')}\n"
        f"  Correctness: {meta.get('metrics', {}).get('correctness', 0.0)}\n"
    )
    log_append(LOGDIR / "runs.log", log_msg)

    # Invoke meta-repair agent (Phase 6)
    agent = "/home/kloros/repairlab/agent_meta.py"

    try:
        proc = subprocess.run(
            [agent, "--handoff", str(handoff_path)],
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            timeout=180
        )

        # Log full output
        log_append(LOGDIR / "runs.log", f"agent_meta exit={proc.returncode}\n{proc.stdout}\n")

        # Parse JSON result
        success = proc.returncode == 0
        agent_result = {}
        try:
            agent_result = json.loads(proc.stdout.strip())
        except Exception:
            pass

        log_append(LOGDIR / "runs.log", f"Repair {'succeeded' if success else 'failed'} (rc={proc.returncode})\n")

        return success, agent_result

    except subprocess.TimeoutExpired:
        log_append(LOGDIR / "runs.log", f"ERROR: Repair timeout after 180s\n")
        return False, {}
    except Exception as e:
        log_append(LOGDIR / "runs.log", f"ERROR: Repair exception: {e}\n")
        return False, {}


def main():
    """Main watcher loop."""
    print(f"RepairLab queue watcher started. Monitoring: {QUEUE}")
    print(f"Logs: {LOGDIR}")

    # Backoff tracking: {filename: [timestamp1, timestamp2, ...]}
    failure_history = {}
    BACKOFF_WINDOW = 600  # 10 minutes
    BACKOFF_THRESHOLD = 3  # 3 failures

    iteration = 0
    while True:
        iteration += 1
        found_any = False

        for f in sorted(QUEUE.glob("handoff_*.json")):
            if f.suffix == ".processed":
                continue

            found_any = True
            print(f"[Iteration {iteration}] Processing: {f.name}")

            # Check backoff/quarantine
            now = time.time()
            if f.name in failure_history:
                recent_failures = [t for t in failure_history[f.name] if now - t < BACKOFF_WINDOW]
                if len(recent_failures) >= BACKOFF_THRESHOLD:
                    # Quarantine to hard_fail
                    hard_fail_dir = PROCESSED / "hard_fail"
                    hard_fail_dir.mkdir(parents=True, exist_ok=True)
                    quarantine_path = hard_fail_dir / f"{f.name}.quarantined"
                    f.rename(quarantine_path)
                    print(f"  → QUARANTINED: {f.name} ({len(recent_failures)} failures in {BACKOFF_WINDOW}s)")
                    log_append(LOGDIR / "runs.log",
                              f"[{time.ctime()}] QUARANTINE: {f.name} after {len(recent_failures)} failures\n")
                    del failure_history[f.name]
                    continue

            try:
                ok, agent_result = run_repair(f)
                suffix = ".ok" if ok else ".fail"
                new_name = PROCESSED / (f.name + suffix)
                f.rename(new_name)
                print(f"  → {'SUCCESS' if ok else 'FAILED'}: Moved to {new_name}")

                # Track failures for backoff/quarantine
                if not ok:
                    if f.name not in failure_history:
                        failure_history[f.name] = []
                    failure_history[f.name].append(now)
                    log_append(LOGDIR / "runs.log",
                              f"[{time.ctime()}] FAILURE TRACKED: {f.name} (count: {len(failure_history[f.name])})\\n")

                # Bounce-back: Successful repairs become challengers
                if ok:
                    try:
                        meta = json.loads(new_name.read_text())
                        challenger_q = pathlib.Path("/tmp/toolgen_challengers")
                        challenger_q.mkdir(parents=True, exist_ok=True)
                        ts = int(time.time())
                        challenger = {
                            "ts": ts,
                            "source": "repairlab",
                            "bundle_dir": meta["bundle_dir"],
                            "spec_path": meta.get("spec_path", ""),
                            "lineage": "repairlab_fixed",
                            "original_epoch": meta.get("epoch", 0),
                            "original_fitness": meta.get("metrics", {}).get("fitness", 0.0),
                            # Phase 6 telemetry
                            "repair_strategy": agent_result.get("strategy"),
                            "repair_pattern_id": agent_result.get("pattern_id"),
                            "repair_attempts": agent_result.get("attempts"),
                            "repair_details": agent_result.get("details"),
                            "bundle_sha256": agent_result.get("bundle_sha256")
                        }
                        challenger_path = challenger_q / f"challenger_{ts}.json"
                        with open(challenger_path, "w") as fp:
                            json.dump(challenger, fp, indent=2)
                        print(f"  → CHALLENGER: Enqueued to {challenger_path}")
                        log_append(LOGDIR / "challengers.log",
                                  f"[{time.ctime()}] Challenger created: {challenger_path.name}\n")
                    except Exception as e:
                        print(f"  → Challenger creation failed: {e}")
                        log_append(LOGDIR / "error.log",
                                  f"[{time.ctime()}] Challenger error for {f}: {e}\n")
            except Exception as e:
                print(f"  → ERROR: {e}")
                log_append(LOGDIR / "error.log", f"[{time.ctime()}] Exception processing {f}: {e}\n")

        if not found_any and iteration % 12 == 0:  # Log every minute
            print(f"[Iteration {iteration}] No handoffs in queue. Waiting...")

        time.sleep(5)


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        print("\nWatcher stopped by user.")
        sys.exit(0)
