#!/usr/bin/env python3
"""
Audio CLI Tool Evaluator for D-REAM
Evaluates command-line audio analysis tools through subprocess execution.

Based on GPT's architectural recommendation for honest black-box testing.
"""

import json
import subprocess
import shlex
import hashlib
import os
import sys
import tempfile
import time
import shutil
import logging
from pathlib import Path
from typing import Dict, List, Any, Tuple, Optional

# Add dream path for absolute imports
sys.path.insert(0, '/home/kloros/src/dream')
from domains.domain_evaluator_base import DomainEvaluator

logger = logging.getLogger(__name__)

# Test audio corpus
AUDIO_CORPUS = [
    "/home/kloros/assets/asr_eval/glados_full_dataset/sample156.wav",
    "/home/kloros/assets/asr_eval/glados_full_dataset/sample219.wav",
    "/home/kloros/assets/asr_eval/glados_full_dataset/sample541.wav",
]

# Resource limits
TIMEOUT_SEC = 30
MEM_MB = 1024
CPU_CORES = 1


def _hash_file(p: str) -> str:
    """Hash file contents for caching."""
    h = hashlib.sha256()
    try:
        with open(p, "rb") as f:
            for chunk in iter(lambda: f.read(65536), b""):
                h.update(chunk)
        return h.hexdigest()[:16]
    except Exception:
        return "missing"


def _tool_hash(path: str) -> str:
    """Get hash of tool file."""
    return _hash_file(path)


def _corpus_hash(paths: List[str]) -> str:
    """Get combined hash of corpus."""
    h = hashlib.sha256()
    for p in paths:
        h.update(_hash_file(p).encode())
    return h.hexdigest()[:16]


def _run_cli(cmd: str, timeout_s: int, workdir: str) -> Dict:
    """
    Run CLI command with resource limits.

    Returns:
        Dict with {rc, elapsed_s, json, stderr}
    """
    # Use prlimit if available for memory/CPU caging
    prlimit = shutil.which("prlimit")
    if prlimit:
        # Cage memory and block excessive forking
        cmd = f"prlimit --nproc=256 --rss={MEM_MB*1024*1024} --cpu={timeout_s} -- {cmd}"

    env = os.environ.copy()
    env.setdefault("OMP_NUM_THREADS", "1")
    env.setdefault("MKL_NUM_THREADS", "1")

    start = time.time()
    try:
        proc = subprocess.run(
            cmd,
            shell=True,
            cwd=workdir,
            env=env,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            timeout=timeout_s
        )
        elapsed = time.time() - start
        out = proc.stdout.decode("utf-8", "ignore")
        err = proc.stderr.decode("utf-8", "ignore")

        # Try to parse JSON output
        try:
            payload = json.loads(out) if out.strip().startswith("{") else {}
        except Exception:
            payload = {}

        return {
            "rc": proc.returncode,
            "elapsed_s": elapsed,
            "json": payload,
            "stderr": err[:2000]
        }
    except subprocess.TimeoutExpired:
        return {
            "rc": -1,
            "elapsed_s": timeout_s,
            "json": {},
            "stderr": f"Command timed out after {timeout_s}s"
        }
    except Exception as e:
        return {
            "rc": -1,
            "elapsed_s": 0.0,
            "json": {},
            "stderr": f"Execution error: {str(e)}"
        }


class AudioCLIToolEvaluator(DomainEvaluator):
    """Evaluates CLI audio tools through subprocess execution."""

    def __init__(self):
        super().__init__("audio_cli_tool")

        # Cache directory for evaluation results
        self.cache_dir = Path("/home/kloros/artifacts/dream/cache")
        self.cache_dir.mkdir(parents=True, exist_ok=True)

        # Available tools (versioned paths)
        self.tools = {
            "noise_floor": "/home/kloros/tools/audio/noise_floor/current/noise_floor.py",
            "latency_jitter": "/home/kloros/tools/audio/latency_jitter/current/latency_jitter.py",
            "clip_scan": "/home/kloros/tools/audio/clip_scan/current/clip_scan.py",
        }

    def get_genome_spec(self) -> Dict[str, Tuple[Any, Any, Any]]:
        """Get genome specification for tool evolution."""
        return {
            # Which tool to evaluate
            'tool_idx': (0, len(self.tools) - 1, 1),

            # Tool arguments (categorical toggles)
            'mode_fast': (0, 1, 1),         # --mode fast
            'mode_accurate': (0, 1, 1),     # --mode accurate
            'verbose': (0, 1, 1),           # --verbose

            # Tunable parameters (if tool supports them)
            'threshold': (0.001, 0.1, 0.001),  # Detection threshold
            'window_ms': (10, 100, 10),        # Analysis window
        }

    def get_safety_constraints(self) -> Dict[str, Any]:
        """Get safety constraints."""
        return {
            'max_fail_rate': {'max': 0.1},           # Max 10% failures
            'max_latency_ms_p95': {'max': 5000},     # Max 5s latency
            'min_success_rate': {'min': 0.9},        # Min 90% success
        }

    def get_default_weights(self) -> Dict[str, float]:
        """Get default fitness weights."""
        return {
            'fail_rate': -0.40,          # Minimize failures (critical)
            'latency_ms_p95': -0.30,     # Minimize latency
            'f1_score': 0.20,            # Maximize accuracy
            'qps': 0.10,                 # Maximize throughput
        }

    def normalize_metric(self, metric_name: str, value: float) -> float:
        """Normalize metric to [0, 1] range."""
        ranges = {
            'fail_rate': (0, 1),
            'latency_ms_p95': (0, 10000),
            'f1_score': (0, 1),
            'qps': (0, 100),
        }

        if metric_name in ranges:
            min_val, max_val = ranges[metric_name]
            normalized = (value - min_val) / (max_val - min_val)
            return max(0, min(1, normalized))
        return value

    def apply_configuration(self, config: Dict[str, Any]) -> bool:
        """
        Apply configuration (prepare tool path and args).

        Note: This doesn't modify the tool - just sets up execution params.
        """
        try:
            # Get tool to evaluate
            tool_idx = int(config.get('tool_idx', 0))
            tool_names = list(self.tools.keys())
            tool_name = tool_names[tool_idx]
            tool_path = self.tools[tool_name]

            # Store configuration for run_probes
            # Note: baseline tools don't have --mode or --verbose flags
            # These config parameters are tracked for evolution but not passed to current tools
            self.current_tool_path = tool_path
            self.current_tool_name = tool_name
            self.current_config = config

            # Build args for tool-specific parameters
            args = []

            # Tool-specific parameters that DO exist
            if tool_name == "noise_floor":
                # noise_floor supports: --segment-duration
                segment_dur = config.get('window_ms', 50) / 1000.0  # Convert to seconds
                args.append(f"--segment-duration {segment_dur}")
            elif tool_name == "clip_scan":
                # clip_scan supports: --threshold
                threshold = config.get('threshold', 0.02)
                args.append(f"--threshold {threshold}")
            # latency_jitter has its own parameters (would be added as needed)

            self.current_tool_args = " ".join(args)

            return True

        except Exception as e:
            logger.error(f"Failed to apply configuration: {e}")
            return False

    def run_probes(self, config: Dict[str, Any]) -> Dict[str, float]:
        """
        Run CLI tool against audio corpus.

        Args:
            config: Configuration parameters

        Returns:
            Dict of measured metrics
        """
        # Apply configuration first
        if not self.apply_configuration(config):
            return self._default_metrics(failed=True)

        # Check cache
        cache_key = f"{_tool_hash(self.current_tool_path)}:{_corpus_hash(AUDIO_CORPUS)}:{self.current_tool_args}"
        cache_file = self.cache_dir / f"tool_{hashlib.sha256(cache_key.encode()).hexdigest()[:20]}.json"

        if cache_file.exists():
            logger.info(f"Using cached metrics for {self.current_tool_name}")
            return json.loads(cache_file.read_text())

        # Run tool against corpus
        agg = {"fail": 0, "lat_ms_p95": 0.0, "f1": 0.0, "qps": 0.0}

        with tempfile.TemporaryDirectory(prefix="audcli_") as tmp:
            for wav in AUDIO_CORPUS:
                if not Path(wav).exists():
                    logger.warning(f"Corpus file missing: {wav}")
                    continue

                # Create output file in temp directory
                out_file = Path(tmp) / f"result_{Path(wav).stem}.json"

                # Build command - tools expect: tool.py <audio_file> --out <json_file>
                cmd = f"python3 {shlex.quote(self.current_tool_path)} {shlex.quote(wav)} --out {shlex.quote(str(out_file))} {self.current_tool_args}"

                # Execute
                res = _run_cli(cmd, TIMEOUT_SEC, tmp)

                if res["rc"] != 0:
                    agg["fail"] += 1
                    logger.warning(f"Tool failed on {wav}: {res['stderr']}")
                    continue

                # Read metrics from output JSON file
                try:
                    m = json.loads(out_file.read_text()) if out_file.exists() else {}
                except Exception as e:
                    logger.warning(f"Failed to read output JSON: {e}")
                    m = {}

                # Extract metrics based on tool type
                # noise_floor: has "raw", "a_weighted", "dynamic_range"
                # latency_jitter: has latency/jitter measurements
                # clip_scan: has clip detection metrics

                # Convert tool-specific metrics to common evaluation schema
                # We measure: execution success, processing time, and tool-specific quality
                elapsed_ms = res["elapsed_s"] * 1000
                agg["lat_ms_p95"] = max(agg["lat_ms_p95"], elapsed_ms)  # Track p95

                # Tool-specific quality metrics (normalized to 0-1 score)
                if self.current_tool_name == "noise_floor":
                    # Quality = can we get a reasonable noise floor measurement?
                    raw_db = m.get("raw", {}).get("rms_mean_db", -200)
                    if -120 < raw_db < 0:  # Reasonable range
                        agg["f1"] += 1.0
                elif self.current_tool_name == "latency_jitter":
                    # Quality = latency/jitter detection accuracy
                    lat = m.get("latency_ms_p95", 0)
                    if 0 < lat < 1000:  # Reasonable latency
                        agg["f1"] += 1.0
                elif self.current_tool_name == "clip_scan":
                    # Quality = clip detection worked
                    clips = m.get("clips_detected", 0)
                    if clips >= 0:  # Valid output
                        agg["f1"] += 1.0

                # Pseudo QPS ~ processed duration / elapsed
                processed_ms = float(m.get("processed_ms", 0.0))
                qps = (processed_ms / 1000.0) / max(res["elapsed_s"], 1e-3) if processed_ms > 0 else 0.0
                agg["qps"] += qps

        # Calculate aggregated metrics
        n = max(1, len([p for p in AUDIO_CORPUS if Path(p).exists()]))

        metrics = {
            "fail_rate": agg["fail"] / n,
            "latency_ms_p95": agg["lat_ms_p95"],  # Already p95 (max)
            "f1_score": agg["f1"] / n,
            "qps": agg["qps"] / n,
        }

        # Cache results
        cache_file.write_text(json.dumps(metrics))

        return metrics

    def _default_metrics(self, failed: bool = False) -> Dict[str, float]:
        """Return default metrics on failure."""
        if failed:
            return {
                "fail_rate": 1.0,
                "latency_ms_p95": 10000.0,
                "f1_score": 0.0,
                "qps": 0.0,
            }
        return {
            "fail_rate": 0.0,
            "latency_ms_p95": 1000.0,
            "f1_score": 0.5,
            "qps": 1.0,
        }


# Test function
def test_cli_evaluator():
    """Test the CLI tool evaluator."""
    evaluator = AudioCLIToolEvaluator()

    test_config = {
        'tool_idx': 0,  # noise_floor
        'mode_fast': 1,
        'verbose': 0,
        'threshold': 0.02,
        'window_ms': 50,
    }

    print(f"Testing Audio CLI Tool evaluator with config: {json.dumps(test_config, indent=2)}")

    # Run evaluation
    result = evaluator.evaluate(test_config)

    print(f"\nEvaluation Results:")
    print(f"Fitness: {result['fitness']:.3f}")
    print(f"Safe: {result['safe']}")
    if result.get('violations'):
        print(f"Violations: {result['violations']}")
    print(f"Metrics: {json.dumps(result['metrics'], indent=2)}")


if __name__ == '__main__':
    test_cli_evaluator()
