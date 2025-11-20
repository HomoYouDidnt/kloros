"""
Actuator bounds and candidate generation for config tuning.

Defines safe parameter ranges for autonomous config adjustments.
"""

from typing import Dict, List, Any, Optional
from dataclasses import dataclass
import logging

logger = logging.getLogger(__name__)


@dataclass
class ActuatorBounds:
    """Bounds for a single configuration parameter."""
    min_value: float
    max_value: float
    step: float
    param_name: str

    def clamp(self, value: float) -> float:
        """Clamp value to bounds and snap to step."""
        clamped = max(self.min_value, min(self.max_value, value))
        # Snap to nearest step
        stepped = round(clamped / self.step) * self.step
        return stepped

    def validate(self, value: float) -> bool:
        """Check if value is within bounds."""
        return self.min_value <= value <= self.max_value


# Actuator bounds registry (production-safe ranges)
ACTUATOR_BOUNDS = {
    "vllm.gpu_memory_utilization": ActuatorBounds(
        min_value=0.60,
        max_value=0.90,
        step=0.05,
        param_name="vllm.gpu_memory_utilization"
    ),
    "vllm.max_num_seqs": ActuatorBounds(
        min_value=2,
        max_value=16,
        step=2,
        param_name="vllm.max_num_seqs"
    ),
    "vllm.max_model_len": ActuatorBounds(
        min_value=1024,
        max_value=8192,
        step=512,
        param_name="vllm.max_model_len"
    ),
}


def validate_candidate(candidate: Dict[str, float]) -> tuple[bool, Optional[str]]:
    """
    Validate that all parameters in candidate are within bounds.

    Args:
        candidate: Dictionary of param_name -> value

    Returns:
        (is_valid, error_message)
    """
    for param_name, value in candidate.items():
        if param_name not in ACTUATOR_BOUNDS:
            return False, f"Unknown parameter: {param_name}"

        bounds = ACTUATOR_BOUNDS[param_name]
        if not bounds.validate(value):
            return False, f"{param_name}={value} out of bounds [{bounds.min_value}, {bounds.max_value}]"

    # Scope guard: max 2 params per candidate
    if len(candidate) > 2:
        return False, f"Candidate modifies {len(candidate)} params (max 2 allowed)"

    return True, None


def generate_candidates(
    seed_fix: Optional[Dict[str, float]] = None,
    subsystem: str = "vllm",
    context: Optional[Dict[str, Any]] = None,
    max_candidates: int = 6
) -> List[Dict[str, float]]:
    """
    Generate candidate configurations for testing.

    If seed_fix provided, use it as first candidate.
    Otherwise generate small grid based on subsystem and context.

    Args:
        seed_fix: Proposed fix to try first (e.g., {"vllm.gpu_memory_utilization": 0.80})
        subsystem: Subsystem being tuned ("vllm", "whisper", etc.)
        context: Error context (deficit_mb, model, etc.)
        max_candidates: Maximum candidates to generate

    Returns:
        List of candidate configurations (param_name -> value dicts)
    """
    candidates = []

    # Priority 1: If seed_fix provided, use it first
    if seed_fix:
        # Validate and clamp seed fix
        clamped_seed = {}
        for param_name, value in seed_fix.items():
            if param_name in ACTUATOR_BOUNDS:
                bounds = ACTUATOR_BOUNDS[param_name]
                clamped_seed[param_name] = bounds.clamp(value)
            else:
                logger.warning(f"Seed fix contains unknown parameter: {param_name}")

        if clamped_seed:
            valid, error = validate_candidate(clamped_seed)
            if valid:
                candidates.append(clamped_seed)
                logger.info(f"Seed fix added as candidate 1: {clamped_seed}")
            else:
                logger.error(f"Seed fix validation failed: {error}")

    # If we have a seed fix and it's valid, we can return just that
    # (single canary test, fastest path)
    if candidates:
        return candidates

    # No seed fix or invalid seed - generate tournament grid
    if subsystem == "vllm":
        candidates = _generate_vllm_candidates(context, max_candidates)
    else:
        logger.warning(f"No candidate generation strategy for subsystem: {subsystem}")

    return candidates[:max_candidates]


def _generate_vllm_candidates(
    context: Optional[Dict[str, Any]] = None,
    max_candidates: int = 6
) -> List[Dict[str, float]]:
    """
    Generate VLLM configuration candidates.

    Strategy: Prioritize memory_utilization adjustments first, then
    max_num_seqs reductions, then max_model_len clamping.

    Args:
        context: Error context with deficit_mb, current values, etc.
        max_candidates: Maximum candidates to generate

    Returns:
        List of candidate configs
    """
    candidates = []

    # Strategy 1: Try increasing gpu_memory_utilization
    # Start from 0.85 and work down in 0.05 steps
    for util in [0.85, 0.80, 0.75, 0.70]:
        candidates.append({"vllm.gpu_memory_utilization": util})

    # Strategy 2: Reduce max_num_seqs to decrease memory pressure
    for seqs in [8, 6, 4]:
        candidates.append({
            "vllm.gpu_memory_utilization": 0.80,
            "vllm.max_num_seqs": seqs
        })

    # Strategy 3: Clamp max_model_len (last resort)
    candidates.append({
        "vllm.gpu_memory_utilization": 0.80,
        "vllm.max_model_len": 4096
    })

    logger.info(f"Generated {len(candidates)} VLLM candidates")

    return candidates[:max_candidates]
