#!/usr/bin/env python3
"""
D-REAM Sidecar: Publishes candidate packs to dashboard and processes experiment queue.
"""
import os, time, json, requests, threading, argparse, pathlib, sys

DASH = os.getenv("DASH_URL", "http://d_ream_dashboard:8080")
AUTH = os.getenv("AUTH_TOKEN", "dev-token-change-me")
WORKER_ID = os.getenv("WORKER_ID", "sidecar-1")
DREAM_ARTIFACTS = os.getenv("DREAM_ARTIFACTS", "/dream_artifacts")
HDRS = {"Authorization": f"Bearer {AUTH}"}

def post_json(path, payload, timeout=15):
    r = requests.post(f"{DASH}{path}", headers=HDRS, json=payload, timeout=timeout)
    r.raise_for_status()
    return r.json()

def post_form(path, data, timeout=15):
    r = requests.post(f"{DASH}{path}", headers=HDRS, data=data, timeout=timeout)
    r.raise_for_status()
    return r.json()

def add_improvement(title, description, domain="general", score=0.0, meta=None):
    meta = meta or {}
    return post_json("/api/improvements", {"title": title, "description": description, "domain": domain, "score": score, "meta": meta})

def scan_dream_candidates():
    """Scan D-REAM artifacts/candidates/ and publish new packs as improvements."""
    candidates_dir = pathlib.Path(DREAM_ARTIFACTS) / "candidates"
    seen_runs = set()
    
    while True:
        try:
            if not candidates_dir.exists():
                print(f"[sidecar] Waiting for candidates dir: {candidates_dir}", file=sys.stderr)
                time.sleep(10)
                continue
            
            for run_dir in candidates_dir.iterdir():
                if not run_dir.is_dir():
                    continue
                
                run_id = run_dir.name
                if run_id in seen_runs:
                    continue
                
                pack_path = run_dir / "pack.json"
                admitted_path = run_dir / "admitted.json"
                
                if not pack_path.exists():
                    continue
                
                try:
                    with open(pack_path) as f:
                        pack = json.load(f)
                    
                    # Check if there are admitted candidates
                    admitted_count = 0
                    if admitted_path.exists():
                        with open(admitted_path) as f:
                            admitted_data = json.load(f)
                            admitted_count = len(admitted_data.get("admitted", []))
                    
                    # Only publish if there are admitted candidates
                    if admitted_count == 0:
                        seen_runs.add(run_id)
                        continue
                    
                    # Extract metadata
                    lineage = pack.get("lineage", {})
                    summary = pack.get("summary", {})
                    best_id = summary.get("best_id", "unknown")
                    
                    # Find best candidate
                    candidates = pack.get("candidates", [])
                    best_candidate = next((c for c in candidates if c.get("id") == best_id), None)
                    
                    if not best_candidate:
                        seen_runs.add(run_id)
                        continue
                    
                    # Extract metrics
                    metrics = best_candidate.get("metrics", {})
                    domain = best_candidate.get("domain", "general")
                    score = metrics.get("score", 0.0)
                    
                    # Build title and description
                    title = f"D-REAM {run_id[:8]}: {domain} optimization"
                    description = f"Episode: {lineage.get('episode_id', 'unknown')}\n"
                    description += f"Score: {score:.2f}, WER: {metrics.get('wer', 'N/A')}, "
                    description += f"VAD: {metrics.get('vad_boundary_ms', 'N/A')}ms, "
                    description += f"Latency: {metrics.get('latency_ms', 'N/A')}ms\n"
                    description += f"Admitted: {admitted_count}/{len(candidates)}"
                    
                    # Meta includes full lineage and run_id for adoption
                    meta = {
                        "run_id": run_id,
                        "lineage": lineage,
                        "admitted_count": admitted_count,
                        "total_candidates": len(candidates)
                    }
                    
                    # Publish to dashboard
                    add_improvement(title, description, domain, score, meta)
                    print(f"[sidecar] Published {run_id} to dashboard", file=sys.stderr)
                    seen_runs.add(run_id)
                    
                except Exception as e:
                    print(f"[sidecar] Error processing {run_id}: {e}", file=sys.stderr)
                    seen_runs.add(run_id)  # Mark as seen to avoid retry loop
        
        except Exception as e:
            print(f"[sidecar] Scan error: {e}", file=sys.stderr)
        
        time.sleep(5)  # Check for new candidates every 5 seconds

def claim_next():
    return post_form("/api/queue/claim", {"worker_id": WORKER_ID}).get("job")

def update_status(job_id, status, note=None):
    payload = {"status": status}
    if note is not None:
        payload["note"] = note
    r = requests.post(f"{DASH}/api/queue/{job_id}/status", headers=HDRS, json=payload, timeout=15)
    r.raise_for_status()

def run_job(job):
    t = job["type_key"]
    p = job["params"]
    ok, note = True, "done"
    try:
        if t == "stt_benchmark":
            os.system(f"/opt/kloros/tools/stt_bench '{p.get('dataset_path','')}' '{p.get('language','en')}'")
        elif t == "failure_injection":
            os.system(f"/opt/kloros/tools/inject_fault '{p.get('module','')}' '{p.get('mode','timeout')}'")
        elif t == "hyperparam_search":
            os.system(f"/opt/kloros/tools/dream/run_hp_search '{p.get('domain','cpu')}' '{int(p.get('generations',5))}'")
        elif t == "tts_retrain":
            os.system(f"/opt/kloros/tools/tts_retrain '{int(p.get('epochs',3))}' '{float(p.get('lr',1e-4))}'")
        elif t == "vad_sweep":
            os.system("/opt/kloros/tools/vad_sweep")
        else:
            ok, note = False, f"unknown type {t}"
    except Exception as e:
        ok, note = False, str(e)
    finally:
        update_status(job["id"], "succeeded" if ok else "failed", note)

def queue_worker(poll=2.0):
    while True:
        try:
            job = claim_next()
            if job:
                update_status(job["id"], "running", f"claimed by {WORKER_ID}")
                threading.Thread(target=run_job, args=(job,), daemon=True).start()
            else:
                time.sleep(poll)
        except Exception as e:
            print(f"[sidecar] queue loop error: {e}", file=sys.stderr)
            time.sleep(3)

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--no-intake", action="store_true", help="Disable candidate intake")
    args = parser.parse_args()

    if not args.no_intake:
        threading.Thread(target=scan_dream_candidates, daemon=True).start()
    queue_worker()

if __name__ == "__main__":
    main()
