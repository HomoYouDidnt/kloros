#!/usr/bin/env python3
"""
Synthetic workload driver for PHASE testing.

Simulates queue operations and measures latency metrics.
"""
import argparse
import json
import time
import random
import importlib.util
import sys


def load_module(path: str):
    """
    Dynamically load a Python module from a file path.

    Args:
        path: Path to the Python module

    Returns:
        Loaded module
    """
    spec = importlib.util.spec_from_file_location("candidate", path)
    if spec is None or spec.loader is None:
        raise ImportError(f"Cannot load module from {path}")

    module = importlib.util.module_from_spec(spec)
    sys.modules["candidate"] = module
    spec.loader.exec_module(module)
    return module


def run_workload(module, duration_sec: int, profile: str) -> dict:
    """
    Run synthetic workload against a candidate zooid.

    Args:
        module: Loaded candidate module
        duration_sec: Test duration in seconds
        profile: Workload profile ID

    Returns:
        Metrics dict with p95_ms, error_rate, throughput_qps, composite
    """
    start = time.time()
    latencies = []
    errors = 0
    requests = 0

    while time.time() - start < duration_sec:
        try:
            t0 = time.time()

            if hasattr(module, "process_request"):
                module.process_request()
            elif hasattr(module, "main"):
                pass
            else:
                time.sleep(random.uniform(0.001, 0.01))

            t1 = time.time()
            latencies.append((t1 - t0) * 1000)
            requests += 1

        except Exception as e:
            errors += 1

        time.sleep(random.uniform(0.05, 0.15))

    if not latencies:
        return {
            "p95_ms": 10000.0,
            "error_rate": 1.0,
            "throughput_qps": 0.0,
            "composite": 0.0
        }

    latencies.sort()
    p95_idx = int(len(latencies) * 0.95)
    p95_ms = latencies[p95_idx] if p95_idx < len(latencies) else latencies[-1]

    error_rate = errors / max(1, requests + errors)
    throughput_qps = requests / max(0.1, duration_sec)

    composite = max(0.0, min(1.0,
        (1.0 - min(1.0, p95_ms / 1000.0)) *
        (1.0 - error_rate) *
        min(1.0, throughput_qps / 100.0)
    ))

    return {
        "p95_ms": round(p95_ms, 2),
        "error_rate": round(error_rate, 4),
        "throughput_qps": round(throughput_qps, 2),
        "composite": round(composite, 4),
        "requests": requests,
        "errors": errors,
        "duration_sec": duration_sec,
        "profile": profile
    }


def main():
    parser = argparse.ArgumentParser(description="PHASE workload driver")
    parser.add_argument("--module", required=True, help="Path to candidate zooid module")
    parser.add_argument("--duration", type=int, required=True, help="Test duration in seconds")
    parser.add_argument("--profile", required=True, help="Workload profile ID")
    args = parser.parse_args()

    try:
        module = load_module(args.module)
        metrics = run_workload(module, args.duration, args.profile)
        print(json.dumps(metrics))
        sys.exit(0)

    except Exception as e:
        print(json.dumps({
            "p95_ms": 10000.0,
            "error_rate": 1.0,
            "throughput_qps": 0.0,
            "composite": 0.0,
            "error": str(e)
        }), file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()
