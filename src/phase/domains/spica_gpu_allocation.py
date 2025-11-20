"""
SPICA Derivative: GPU Resource Allocation

SPICA-based GPU allocation optimization with:
- VLLM memory utilization tuning
- Whisper model size selection
- Concurrent capacity measurement
- OOM event detection
- Latency profiling

KPIs: stt_latency_ms, llm_latency_ms, gpu_utilization, oom_events, concurrent_capacity
"""
import time
import hashlib
import uuid
import json
import logging
import subprocess
import re
import os
from pathlib import Path
from typing import Dict, List, Optional, Any
from dataclasses import dataclass, asdict
import sys

sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from spica.base import SpicaBase
from src.phase.report_writer import write_test_result

logger = logging.getLogger(__name__)

# Two-mode operation: predictive (no downtime) vs canary (real VLLM test)
MODE = os.environ.get("KLR_CANARY_MODE", "predictive").lower()
CANARY_PORT = int(os.environ.get("KLR_CANARY_PORT", "9011"))


@dataclass
class GPUAllocationTestConfig:
    """Configuration for GPU allocation domain tests."""
    vllm_memory_util_min: float = 0.30
    vllm_memory_util_max: float = 0.70
    whisper_models: List[str] = None
    test_duration_sec: int = 30
    max_oom_events: int = 0  # Zero tolerance for OOM
    target_gpu_util_pct: float = 70.0  # Target utilization
    max_stt_latency_ms: float = 500.0
    max_llm_latency_ms: float = 1000.0

    # Fitness weights (must sum to ~1.0)
    fitness_weight_stt_latency: float = 0.25
    fitness_weight_llm_latency: float = 0.25
    fitness_weight_capacity: float = 0.20
    fitness_weight_stability: float = 0.20  # OOM penalty
    fitness_weight_efficiency: float = 0.10  # GPU utilization balance

    def __post_init__(self):
        if self.whisper_models is None:
            self.whisper_models = ["tiny", "base", "small"]


@dataclass
class GPUAllocationTestResult:
    """Results from a single GPU allocation test."""
    test_id: str
    config_hash: str
    status: str
    vllm_memory_util: float
    whisper_model_size: str
    stt_latency_ms: float
    llm_latency_ms: float
    gpu_utilization_pct: float
    oom_events: int
    concurrent_capacity: int
    free_memory_mb: float
    test_duration_sec: float
    # Production-realistic validation fields
    validation_passed: bool = True
    validation_reason: str = ""
    production_services: Optional[Dict[str, Any]] = None


class SpicaGPUAllocation(SpicaBase):
    """SPICA derivative for GPU resource allocation testing."""

    def __init__(self, spica_id: Optional[str] = None, config: Optional[Dict] = None,
                 test_config: Optional[GPUAllocationTestConfig] = None,
                 parent_id: Optional[str] = None, generation: int = 0,
                 mutations: Optional[Dict] = None):
        if spica_id is None:
            spica_id = f"spica-gpu-{uuid.uuid4().hex[:8]}"

        base_config = config or {}
        if test_config:
            base_config.update({
                'vllm_memory_util_min': test_config.vllm_memory_util_min,
                'vllm_memory_util_max': test_config.vllm_memory_util_max,
                'whisper_models': test_config.whisper_models,
                'test_duration_sec': test_config.test_duration_sec,
                'max_oom_events': test_config.max_oom_events,
                'target_gpu_util_pct': test_config.target_gpu_util_pct,
                'fitness_weight_stt_latency': test_config.fitness_weight_stt_latency,
                'fitness_weight_llm_latency': test_config.fitness_weight_llm_latency,
                'fitness_weight_capacity': test_config.fitness_weight_capacity,
                'fitness_weight_stability': test_config.fitness_weight_stability,
                'fitness_weight_efficiency': test_config.fitness_weight_efficiency
            })

        super().__init__(
            spica_id=spica_id,
            domain="gpu_allocation",
            config=base_config,
            parent_id=parent_id,
            generation=generation,
            mutations=mutations
        )

        self.test_config = test_config or GPUAllocationTestConfig()
        self.results: List[GPUAllocationTestResult] = []

    def get_production_services(self) -> Dict[str, Any]:
        """Detect running production services and their GPU memory usage.
        
        This enables production-realistic testing by accounting for actual
        services that will compete for GPU memory.
        """
        services = {
            "kloros": {"running": False, "memory_mb": 0, "pid": None},
            "judge": {"running": False, "memory_mb": 0, "pid": None},
            "ollama": {"running": False, "memory_mb": 0, "pid": None},
            "other": {"count": 0, "memory_mb": 0}
        }

        try:
            cmd = ['nvidia-smi', '--query-compute-apps=pid,process_name,used_memory',
                   '--format=csv,noheader,nounits']
            result = subprocess.run(cmd, capture_output=True, text=True, timeout=5)

            if result.returncode == 0:
                for line in result.stdout.strip().split('\n'):
                    if line:
                        parts = line.split(', ')
                        if len(parts) >= 3:
                            pid, name, memory = int(parts[0]), parts[1], int(parts[2])

                            # Identify known production services
                            if 'vllm' in name.lower() or 'EngineCore' in name:
                                services["judge"] = {"running": True, "memory_mb": memory, "pid": pid}
                            elif 'ollama' in name.lower():
                                services["ollama"] = {"running": True, "memory_mb": memory, "pid": pid}
                            elif 'python' in name.lower():
                                # Check if it's the kloros service
                                try:
                                    cmd_result = subprocess.run(['ps', '-p', str(pid), '-o', 'cmd='],
                                                              capture_output=True, text=True, timeout=2)
                                    if 'kloros_voice' in cmd_result.stdout:
                                        services["kloros"] = {"running": True, "memory_mb": memory, "pid": pid}
                                    else:
                                        services["other"]["count"] += 1
                                        services["other"]["memory_mb"] += memory
                                except:
                                    services["other"]["count"] += 1
                                    services["other"]["memory_mb"] += memory
                            else:
                                services["other"]["count"] += 1
                                services["other"]["memory_mb"] += memory

            logger.info(f"Production services detected: "
                       f"kloros={services['kloros']['running']}, "
                       f"judge={services['judge']['running']}, "
                       f"ollama={services['ollama']['running']}, "
                       f"other={services['other']['count']} processes")

        except Exception as e:
            logger.error(f"Failed to detect production services: {e}")

        return services

    def validate_vllm_allocation(self, vllm_memory_util: float, gpu_state: Dict[str, Any]) -> Dict[str, Any]:
        """Validate if VLLM can allocate the requested memory with production services running.

        This prevents the "No available memory for cache blocks" error we encountered.

        Key constraints:
        1. Model size check: VLLM allocation must fit the model (~5700MB for Qwen2.5-7B-AWQ)
        2. KV cache space: Need additional ~370MB minimum for cache blocks
        3. Persistent services: Kloros, Ollama stay loaded (not restarted)
        4. Contiguous memory: VLLM needs contiguous allocation
        """
        validation = {
            "valid": False,
            "reason": "",
            "estimated_vllm_mb": 0,
            "estimated_model_mb": 0,
            "estimated_kv_cache_mb": 0,
            "required_total_mb": 0,
            "persistent_services_mb": 0,
            "available_for_vllm_mb": 0
        }

        try:
            total_mb = gpu_state["total_mb"]
            used_mb = gpu_state["used_mb"]
            free_mb = gpu_state["free_mb"]
            services = gpu_state.get("production_services", {})

            # Model size for Qwen2.5-7B-AWQ (from production data)
            # At 50% allocation (~6134MB), model uses ~5764MB, leaving ~370MB for KV cache
            estimated_model_mb = 5700  # Conservative estimate

            # VLLM allocation is % of TOTAL GPU, not available GPU
            estimated_vllm_mb = total_mb * vllm_memory_util

            # Minimum KV cache requirement (from production: 370MB at 50%)
            # Scale proportionally, but enforce minimum
            min_kv_cache_mb = 370

            # Check 1: Does VLLM allocation fit the model + minimum KV cache?
            required_in_allocation = estimated_model_mb + min_kv_cache_mb
            if estimated_vllm_mb < required_in_allocation:
                validation["valid"] = False
                deficit = required_in_allocation - estimated_vllm_mb
                validation["reason"] = (
                    f"VLLM allocation ({estimated_vllm_mb:.0f}MB) too small for model+cache "
                    f"(need {required_in_allocation:.0f}MB, deficit: {deficit:.0f}MB)"
                )
                validation.update({
                    "estimated_vllm_mb": estimated_vllm_mb,
                    "estimated_model_mb": estimated_model_mb,
                    "estimated_kv_cache_mb": min_kv_cache_mb
                })
                logger.warning(f"VLLM validation failed: {validation['reason']}")
                return validation

            # Calculate actual KV cache space available within allocation
            kv_cache_in_allocation = estimated_vllm_mb - estimated_model_mb

            # Check 2: Account for persistent services (kloros, ollama, other - NOT judge)
            persistent_mb = 0
            persistent_mb += services.get("kloros", {}).get("memory_mb", 0)
            persistent_mb += services.get("ollama", {}).get("memory_mb", 0)
            persistent_mb += services.get("other", {}).get("memory_mb", 0)

            # Available memory for VLLM = Total - Persistent services
            available_for_vllm = total_mb - persistent_mb

            # Check 3: Can we fit VLLM allocation with persistent services?
            if available_for_vllm < estimated_vllm_mb:
                validation["valid"] = False
                deficit = estimated_vllm_mb - available_for_vllm
                validation["reason"] = (
                    f"Insufficient GPU memory with persistent services: "
                    f"need {estimated_vllm_mb:.0f}MB, have {available_for_vllm:.0f}MB "
                    f"(persistent services: {persistent_mb:.0f}MB, deficit: {deficit:.0f}MB)"
                )
                validation.update({
                    "estimated_vllm_mb": estimated_vllm_mb,
                    "estimated_model_mb": estimated_model_mb,
                    "estimated_kv_cache_mb": kv_cache_in_allocation,
                    "persistent_services_mb": persistent_mb,
                    "available_for_vllm_mb": available_for_vllm
                })
                logger.warning(f"VLLM validation failed: {validation['reason']}")
                return validation

            # All checks passed
            validation.update({
                "valid": True,
                "reason": (
                    f"Valid: {estimated_vllm_mb:.0f}MB allocation fits model ({estimated_model_mb:.0f}MB) "
                    f"+ KV cache ({kv_cache_in_allocation:.0f}MB) with persistent services ({persistent_mb:.0f}MB)"
                ),
                "estimated_vllm_mb": estimated_vllm_mb,
                "estimated_model_mb": estimated_model_mb,
                "estimated_kv_cache_mb": kv_cache_in_allocation,
                "persistent_services_mb": persistent_mb,
                "available_for_vllm_mb": available_for_vllm
            })

            logger.info(f"VLLM validation: util={vllm_memory_util:.0%}, "
                       f"allocation={estimated_vllm_mb:.0f}MB, model={estimated_model_mb:.0f}MB, "
                       f"kv_cache={kv_cache_in_allocation:.0f}MB, persistent={persistent_mb:.0f}MB, "
                       f"valid={validation['valid']}")

        except Exception as e:
            logger.error(f"VLLM validation failed: {e}")
            validation["reason"] = f"Validation error: {e}"

        return validation

    def run_canary_validation(self, candidate: Dict[str, Any]) -> Dict[str, Any]:
        """Test candidate configuration against live canary VLLM instance.

        This mode requires gpu_canary_runner to have started a canary VLLM
        on CANARY_PORT with the candidate parameters.

        Returns:
            Dict with validation results and real latency metrics
        """
        import requests

        validation = {
            "valid": False,
            "mode": "canary",
            "reason": "",
            "health_ok": False,
            "llm_latency_ms": 999.0,
            "oom_events": 0
        }

        try:
            # Check canary health endpoint
            health_start = time.time()
            r = requests.get(f"http://127.0.0.1:{CANARY_PORT}/health", timeout=5)
            r.raise_for_status()
            validation["health_ok"] = True

            # Test inference with real completion
            inference_start = time.time()
            completion = requests.post(
                f"http://127.0.0.1:{CANARY_PORT}/v1/completions",
                json={
                    "model": "/home/kloros/models/llm/current",
                    "prompt": "Test query for canary validation",
                    "max_tokens": 16,
                    "temperature": 0.0
                },
                timeout=10
            )
            completion.raise_for_status()
            latency_ms = (time.time() - inference_start) * 1000.0

            # Check for OOM events during test
            oom_events = self.check_oom_events()

            # Validate pass gates
            if oom_events == 0 and latency_ms < 2000:  # 2s max latency
                validation.update({
                    "valid": True,
                    "reason": f"Canary validation passed: latency={latency_ms:.1f}ms, oom=0",
                    "llm_latency_ms": latency_ms,
                    "oom_events": oom_events
                })
                logger.info(f"Canary validation passed: {validation}")
            else:
                validation.update({
                    "valid": False,
                    "reason": f"Canary validation failed: latency={latency_ms:.1f}ms, oom={oom_events}",
                    "llm_latency_ms": latency_ms,
                    "oom_events": oom_events
                })
                logger.warning(f"Canary validation failed: {validation}")

        except requests.exceptions.RequestException as e:
            validation["reason"] = f"Canary endpoint error: {e}"
            logger.error(f"Canary validation failed: {e}")
        except Exception as e:
            validation["reason"] = f"Canary validation exception: {e}"
            logger.error(f"Canary validation exception: {e}")

        return validation

    def get_gpu_state(self) -> Dict[str, Any]:
        """Get current GPU memory and process state."""
        try:
            cmd = ['nvidia-smi', '--query-compute-apps=pid,process_name,used_memory',
                   '--format=csv,noheader,nounits']
            result = subprocess.run(cmd, capture_output=True, text=True, timeout=5)

            processes = []
            total_used_mb = 0

            if result.returncode == 0:
                for line in result.stdout.strip().split('\n'):
                    if line:
                        parts = line.split(', ')
                        if len(parts) >= 3:
                            processes.append({
                                "pid": int(parts[0]),
                                "name": parts[1],
                                "memory_mb": int(parts[2])
                            })
                            total_used_mb += int(parts[2])

            cmd = ['nvidia-smi', '--query-gpu=memory.total,memory.used',
                   '--format=csv,noheader,nounits', '-i', '0']
            result = subprocess.run(cmd, capture_output=True, text=True, timeout=5)

            if result.returncode == 0:
                total, used = map(int, result.stdout.strip().split(', '))
                state = {
                    "total_mb": total,
                    "used_mb": used,
                    "free_mb": total - used,
                    "utilization_pct": (used / total) * 100,
                    "processes": processes
                }
                # Add production services info for production-realistic testing
                state["production_services"] = self.get_production_services()
                return state

        except Exception as e:
            logger.error(f"Failed to get GPU state: {e}")

        return {"total_mb": 0, "used_mb": 0, "free_mb": 0, "utilization_pct": 0, "processes": [], "production_services": {}}

    def measure_stt_latency(self, whisper_size: str = "small") -> float:
        """Measure Whisper STT latency."""
        try:
            test_script = f"""
import time
import warnings
warnings.filterwarnings('ignore')
import numpy as np
import whisper

audio = np.random.randn(16000 * 3).astype(np.float32)
model = whisper.load_model('{whisper_size}')

# Warmup
_ = model.transcribe(audio, fp16=True)

# Measure
start = time.time()
_ = model.transcribe(audio, fp16=True)
latency_ms = (time.time() - start) * 1000

print(f"LATENCY={{latency_ms:.1f}}")
"""
            # Set CUDA environment for subprocess
            env = os.environ.copy()
            env['CUDA_VISIBLE_DEVICES'] = '0'
            
            result = subprocess.run(
                ['/home/kloros/.venv/bin/python3', '-c', test_script],
                capture_output=True, text=True, timeout=30, env=env
            )

            match = re.search(r'LATENCY=([\d.]+)', result.stdout)
            return float(match.group(1)) if match else 999.0

        except Exception as e:
            logger.error(f"STT latency measurement failed: {e}")
            return 999.0

    def measure_llm_latency(self) -> float:
        """Measure LLM inference latency via Ollama."""
        try:
            from src.config.models_config import get_ollama_url, get_ollama_model
            ollama_url = get_ollama_url() + "/api/generate"
            ollama_model = get_ollama_model()

            test_script = f"""
import json, time, urllib.request

data = json.dumps({{"model": "{ollama_model}", "prompt": "Test", "stream": False}}).encode()
req = urllib.request.Request("{ollama_url}", data=data,
                              headers={{"Content-Type": "application/json"}})
start = time.time()
with urllib.request.urlopen(req, timeout=15) as resp:
    latency_ms = (time.time() - start) * 1000
    print(f"LATENCY={{latency_ms:.1f}}")
"""
            # Set CUDA environment for subprocess
            env = os.environ.copy()
            env['CUDA_VISIBLE_DEVICES'] = '0'
            
            result = subprocess.run(
                ['/home/kloros/.venv/bin/python3', '-c', test_script],
                capture_output=True, text=True, timeout=20, env=env
            )

            match = re.search(r'LATENCY=([\d.]+)', result.stdout)
            return float(match.group(1)) if match else 999.0

        except Exception as e:
            logger.error(f"LLM latency measurement failed: {e}")
            return 999.0

    def check_oom_events(self) -> int:
        """Check for GPU OOM events."""
        try:
            result = subprocess.run(['sudo', 'dmesg', '-T'], capture_output=True,
                                    text=True, timeout=5)
            if result.returncode == 0:
                return result.stdout.lower().count('cuda out of memory')
            return 0
        except:
            return 0

    def run_test(self, candidate: Dict[str, Any]) -> GPUAllocationTestResult:
        """Run single GPU allocation test with production-realistic validation."""
        test_id = f"gpu-{uuid.uuid4().hex[:8]}"
        config_hash = hashlib.sha256(json.dumps(candidate, sort_keys=True).encode()).hexdigest()[:16]

        vllm_util = candidate.get("vllm_memory_util", 0.50)
        whisper_model = candidate.get("whisper_model_size", "small")

        # Validate bounds
        if not (self.test_config.vllm_memory_util_min <= vllm_util <= self.test_config.vllm_memory_util_max):
            logger.error(f"VLLM util {vllm_util} out of bounds")
            return GPUAllocationTestResult(
                test_id=test_id, config_hash=config_hash, status="invalid",
                vllm_memory_util=vllm_util, whisper_model_size=whisper_model,
                stt_latency_ms=999.0, llm_latency_ms=999.0, gpu_utilization_pct=100.0,
                oom_events=999, concurrent_capacity=0, free_memory_mb=0, test_duration_sec=0,
                validation_passed=False, validation_reason="VLLM util out of bounds"
            )

        start_time = time.time()

        # Get baseline state (includes production services)
        gpu_state = self.get_gpu_state()
        production_services = gpu_state.get("production_services", {})

        # TWO-MODE VALIDATION: Predictive (no downtime) vs Canary (real test)
        if MODE == "canary":
            logger.info(f"Running canary mode validation for {candidate}")
            validation = self.run_canary_validation(candidate)
        else:
            logger.info(f"Running predictive mode validation for {candidate}")
            validation = self.validate_vllm_allocation(vllm_util, gpu_state)

        if not validation.get("valid", False):
            # Return early - this config would fail in production
            logger.warning(f"Pre-flight validation failed for {candidate}: {validation['reason']}")
            duration = time.time() - start_time
            return GPUAllocationTestResult(
                test_id=test_id,
                config_hash=config_hash,
                status="invalid_production",  # Distinct from bounds invalid
                vllm_memory_util=vllm_util,
                whisper_model_size=whisper_model,
                stt_latency_ms=999.0,
                llm_latency_ms=999.0,
                gpu_utilization_pct=gpu_state["utilization_pct"],
                oom_events=0,
                concurrent_capacity=0,
                free_memory_mb=gpu_state["free_mb"],
                test_duration_sec=duration,
                validation_passed=False,
                validation_reason=validation["reason"],
                production_services=production_services
            )

        # Validation passed - proceed with measurements
        logger.info(f"Pre-flight validation passed for {candidate}: {validation['reason']}")

        # Measure latencies (using current system state as proxy)
        stt_latency = self.measure_stt_latency(whisper_model)
        llm_latency = self.measure_llm_latency()

        # Check for OOM
        oom_events = self.check_oom_events()

        # Estimate concurrent capacity (simplified)
        free_memory_mb = gpu_state["free_mb"]
        concurrent_capacity = max(1, int(free_memory_mb / 200))  # ~200MB per request

        duration = time.time() - start_time

        result = GPUAllocationTestResult(
            test_id=test_id,
            config_hash=config_hash,
            status="pass" if oom_events == 0 else "fail",
            vllm_memory_util=vllm_util,
            whisper_model_size=whisper_model,
            stt_latency_ms=stt_latency,
            llm_latency_ms=llm_latency,
            gpu_utilization_pct=gpu_state["utilization_pct"],
            oom_events=oom_events,
            concurrent_capacity=concurrent_capacity,
            free_memory_mb=free_memory_mb,
            test_duration_sec=duration,
            validation_passed=True,
            validation_reason=validation["reason"],
            production_services=production_services
        )

        self.results.append(result)
        logger.info(f"GPU allocation test: {asdict(result)}")

        return result

    def compute_fitness(self, result: GPUAllocationTestResult) -> float:
        """Compute fitness score for a GPU allocation configuration."""
        if result.status != "pass" or result.oom_events > 0 or not result.validation_passed:
            return 0.0  # Zero fitness for failures or invalid production configs

        # Normalize metrics to [0, 1]
        stt_norm = 1.0 - min(result.stt_latency_ms / self.test_config.max_stt_latency_ms, 1.0)
        llm_norm = 1.0 - min(result.llm_latency_ms / self.test_config.max_llm_latency_ms, 1.0)
        capacity_norm = min(result.concurrent_capacity / 20.0, 1.0)  # Cap at 20 concurrent
        stability_norm = 1.0  # Pass already guaranteed OOM == 0

        # GPU utilization: prefer ~70%, penalize too low or too high
        util_deviation = abs(result.gpu_utilization_pct - self.test_config.target_gpu_util_pct)
        efficiency_norm = 1.0 - min(util_deviation / 50.0, 1.0)

        # Weighted sum
        fitness = (
            stt_norm * self.test_config.fitness_weight_stt_latency +
            llm_norm * self.test_config.fitness_weight_llm_latency +
            capacity_norm * self.test_config.fitness_weight_capacity +
            stability_norm * self.test_config.fitness_weight_stability +
            efficiency_norm * self.test_config.fitness_weight_efficiency
        )

        return fitness

    def evaluate(self, candidate: Dict[str, Any]) -> Dict[str, Any]:
        """Evaluate a candidate GPU allocation configuration."""
        result = self.run_test(candidate)
        fitness = self.compute_fitness(result)

        return {
            "stt_latency_ms": result.stt_latency_ms,
            "llm_latency_ms": result.llm_latency_ms,
            "gpu_utilization": result.gpu_utilization_pct,
            "oom_events": result.oom_events,
            "concurrent_capacity": result.concurrent_capacity,
            "fitness": fitness,
            "status": result.status
        }


def test_gpu_allocation():
    """Test the GPU allocation evaluator."""
    evaluator = SpicaGPUAllocation()

    candidate = {
        "vllm_memory_util": 0.50,
        "whisper_model_size": "small"
    }

    print("Testing GPU Allocation Evaluator (SPICA)")
    print("=" * 60)
    print(f"Candidate: {json.dumps(candidate, indent=2)}")

    metrics = evaluator.evaluate(candidate)

    print("\nResults:")
    print(json.dumps(metrics, indent=2))


if __name__ == "__main__":
    test_gpu_allocation()
