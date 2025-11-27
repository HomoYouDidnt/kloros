#!/usr/bin/env python3
"""
Common Benchmark Harness for KLoROS Audio Strategy Comparison
Measures TTFI, wake latency, CPU/RAM usage, and STT quality metrics.
"""

import time
import json
import os
import psutil
import sys
from rapidfuzz import fuzz
from vosk import Model, KaldiRecognizer
import numpy as np


TARGET_SR = 16000
WAKE_SET = ["kloros", "colors", "chorus", "close", "carlos", "clothes", "koros", "claw rose", "klo ros"]


def detect_wake(text: str) -> bool:
    """Detect wake words using fuzzy matching."""
    s = text.lower().strip()
    if not s:
        return False
    return max(fuzz.partial_ratio(s, w) for w in WAKE_SET) >= 85


def run_trial(import_path: str, trial_sec=20):
    """
    Run a single trial of the audio capture implementation.

    Args:
        import_path: Python module path to import (e.g., "cap_impl")
        trial_sec: Duration of trial in seconds
    """
    print(f"Starting trial: {import_path} for {trial_sec}s")

    # Dynamic import of the implementation under test
    try:
        cap = __import__(import_path.replace(".py", ""))
    except ImportError as e:
        print(f"Failed to import {import_path}: {e}")
        return {"error": f"Import failed: {e}", "impl": import_path}

    # Initialize Vosk model
    vosk_model_path = os.getenv("VOSK_MODEL", "/home/kloros/models/vosk/model")
    if not os.path.exists(vosk_model_path):
        # Try alternative paths
        alt_paths = [
            "/home/claude_temp/models/vosk/model",
            "/home/adam/KLoROS/models/vosk/model",
            "/opt/kloros/models/vosk/model"
        ]
        for path in alt_paths:
            if os.path.exists(path):
                vosk_model_path = path
                break
        else:
            return {"error": f"Vosk model not found in {vosk_model_path}", "impl": import_path}

    try:
        model = Model(vosk_model_path)
        rec = KaldiRecognizer(model, TARGET_SR)
        rec.SetWords(True)
    except Exception as e:
        return {"error": f"Vosk initialization failed: {e}", "impl": import_path}

    # Initialize statistics
    stats = {
        "t0": None,
        "ttfi_ms": None,
        "wake_ms": None,
        "callbacks": 0,
        "xruns": 0,
        "errors": 0,
        "nonempty_final": 0,
        "accepted_chunks": 0,
        "open_failures": 0,
        "last_error": None
    }

    t_start = time.perf_counter()

    def on_chunk(b: bytes):
        """Process audio chunks and collect metrics."""
        nonlocal stats

        # Record time-to-first-input
        if stats["t0"] is None:
            stats["t0"] = time.perf_counter()
            stats["ttfi_ms"] = int((stats["t0"] - t_start) * 1000)
            print(f"TTFI: {stats['ttfi_ms']}ms")

        try:
            # Process chunk with Vosk
            if len(b) > 0:
                ok = rec.AcceptWaveform(b)
                stats["accepted_chunks"] += int(ok)

                if ok:
                    res = json.loads(rec.Result())
                    txt = res.get("text", "").strip()
                    if txt:
                        stats["nonempty_final"] += 1
                        print(f"STT: '{txt}'")

                        # Check for wake word
                        if stats["wake_ms"] is None and detect_wake(txt):
                            stats["wake_ms"] = int((time.perf_counter() - t_start) * 1000)
                            print(f"WAKE DETECTED at {stats['wake_ms']}ms: '{txt}'")

            stats["callbacks"] += 1

        except Exception as e:
            stats["errors"] += 1
            stats["last_error"] = str(e)
            print(f"Chunk processing error: {e}")

    # Start capture
    print("Starting audio capture...")
    try:
        closer = cap.start_capture(on_chunk)
        if closer is None:
            stats["open_failures"] += 1
            return {
                "error": "start_capture returned None",
                "open_failures": 1,
                "impl": import_path
            }
    except Exception as e:
        stats["open_failures"] += 1
        stats["last_error"] = str(e)
        return {
            "error": f"Failed to start capture: {e}",
            "open_failures": 1,
            "impl": import_path
        }

    # Monitor system resources
    p = psutil.Process(os.getpid())
    cpu_samples, rss_samples = [], []

    end = t_start + trial_sec
    last_status = None

    try:
        while time.perf_counter() < end:
            try:
                cpu_samples.append(p.cpu_percent(interval=0.25))
                rss_samples.append(p.memory_info().rss)
            except Exception as e:
                stats["errors"] += 1
                last_status = f"Monitoring error: {e}"
                break

    except KeyboardInterrupt:
        print("Trial interrupted by user")
        last_status = "Interrupted"
    except Exception as e:
        stats["errors"] += 1
        last_status = f"{type(e).__name__}: {e}"
        print(f"Trial error: {e}")
    finally:
        # Stop capture
        try:
            if closer:
                closer()
                print("Capture stopped cleanly")
        except Exception as e:
            print(f"Error stopping capture: {e}")
            stats["errors"] += 1

    # Compile results
    result = {
        "ttfi_ms": stats["ttfi_ms"],
        "wake_ms": stats["wake_ms"],
        "callbacks": stats["callbacks"],
        "accepted_chunks": stats["accepted_chunks"],
        "nonempty_final": stats["nonempty_final"],
        "cpu_mean": round(float(np.mean(cpu_samples)) if cpu_samples else 0.0, 1),
        "rss_mb": round((max(rss_samples) if rss_samples else 0) / (1024 * 1024), 1),
        "errors": stats["errors"],
        "open_failures": stats["open_failures"],
        "last_status": last_status or stats["last_error"],
        "impl": import_path,
        "ts": time.strftime("%Y-%m-%d %H:%M:%S"),
        "trial_duration_s": trial_sec
    }

    # Calculate derived metrics
    if stats["callbacks"] > 0:
        result["dropout_rate"] = round(stats["errors"] / stats["callbacks"], 3)
        result["stt_acceptance_rate"] = round(stats["accepted_chunks"] / stats["callbacks"], 3)
    else:
        result["dropout_rate"] = 1.0
        result["stt_acceptance_rate"] = 0.0

    print(json.dumps(result, indent=2))
    return result


def main():
    """Main benchmark runner."""
    if len(sys.argv) < 2:
        print("Usage: python cap_bench.py <import_path> [trial_seconds]")
        print("Example: python cap_bench.py cap_impl 20")
        sys.exit(1)

    import_path = sys.argv[1]
    trial_sec = int(sys.argv[2]) if len(sys.argv) > 2 else 20

    print(f"KLoROS Audio Benchmark - Testing: {import_path}")
    print(f"Trial duration: {trial_sec} seconds")
    print(f"Target sample rate: {TARGET_SR} Hz")
    print(f"Wake words: {WAKE_SET}")
    print("-" * 50)

    result = run_trial(import_path, trial_sec)

    # Final summary
    if "error" not in result:
        print(f"\nSUMMARY for {import_path}:")
        print(f"  TTFI: {result['ttfi_ms']}ms")
        print(f"  Wake Detection: {result['wake_ms']}ms" if result['wake_ms'] else "  Wake Detection: NONE")
        print(f"  Callbacks: {result['callbacks']}")
        print(f"  STT Acceptance: {result['stt_acceptance_rate']*100:.1f}%")
        print(f"  CPU Usage: {result['cpu_mean']}%")
        print(f"  Memory: {result['rss_mb']}MB")
        print(f"  Errors: {result['errors']}")
        print(f"  Open Failures: {result['open_failures']}")
    else:
        print(f"\nFAILED: {result['error']}")


if __name__ == "__main__":
    main()