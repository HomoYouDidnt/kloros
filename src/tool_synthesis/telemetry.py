"""
Telemetry collection for skill execution.

Tracks latency, calls, errors, tokens, and cost for SLO enforcement.
"""

import time
import json
from pathlib import Path
from typing import Dict, List, Optional
from dataclasses import dataclass, field
from collections import defaultdict


# Pricing table (USD per 1M tokens) - updated January 2025
MODEL_PRICING = {
    # Claude models
    "claude-opus-4": {"input": 15.00, "output": 75.00},
    "claude-sonnet-4": {"input": 3.00, "output": 15.00},
    "claude-sonnet-4-5": {"input": 3.00, "output": 15.00},
    "claude-haiku-4": {"input": 0.25, "output": 1.25},
    "claude-3-5-sonnet": {"input": 3.00, "output": 15.00},
    "claude-3-opus": {"input": 15.00, "output": 75.00},
    "claude-3-sonnet": {"input": 3.00, "output": 15.00},
    "claude-3-haiku": {"input": 0.25, "output": 1.25},

    # OpenAI models
    "gpt-4-turbo": {"input": 10.00, "output": 30.00},
    "gpt-4": {"input": 30.00, "output": 60.00},
    "gpt-3.5-turbo": {"input": 0.50, "output": 1.50},
    "gpt-4o": {"input": 5.00, "output": 15.00},
    "gpt-4o-mini": {"input": 0.15, "output": 0.60},

    # Ollama/local models (free)
    "ollama": {"input": 0.00, "output": 0.00},
    "llama": {"input": 0.00, "output": 0.00},
    "mistral": {"input": 0.00, "output": 0.00},

    # Default fallback
    "default": {"input": 1.00, "output": 2.00}
}


def calculate_cost(tokens_in: int, tokens_out: int, model: str) -> float:
    """
    Calculate cost in USD for LLM call.

    Args:
        tokens_in: Input tokens
        tokens_out: Output tokens
        model: Model name (e.g., "claude-sonnet-4")

    Returns:
        Cost in USD
    """
    # Normalize model name (handle versioning variants)
    model_lower = model.lower()

    # Find matching pricing (check longer keys first for specificity)
    # This ensures "gpt-4o" matches before "gpt-4"
    pricing = None
    sorted_keys = sorted(MODEL_PRICING.keys(), key=len, reverse=True)
    for key in sorted_keys:
        if key in model_lower:
            pricing = MODEL_PRICING[key]
            break

    if pricing is None:
        pricing = MODEL_PRICING["default"]

    # Calculate cost (pricing is per 1M tokens)
    cost_in = (tokens_in / 1_000_000) * pricing["input"]
    cost_out = (tokens_out / 1_000_000) * pricing["output"]

    return cost_in + cost_out


@dataclass
class SkillMetrics:
    """Metrics for a skill."""
    skill: str
    version: str
    calls: int = 0
    errors: int = 0
    latencies_ms: List[int] = field(default_factory=list)
    tokens_in: int = 0
    tokens_out: int = 0
    cost_usd: float = 0.0
    model_usage: Dict[str, int] = field(default_factory=dict)  # model -> call count
    last_updated: float = field(default_factory=time.time)

    def error_rate(self) -> float:
        """Calculate error rate."""
        if self.calls == 0:
            return 0.0
        return self.errors / self.calls

    def p50_latency(self) -> Optional[float]:
        """Calculate median latency."""
        if not self.latencies_ms:
            return None
        sorted_lat = sorted(self.latencies_ms)
        return sorted_lat[len(sorted_lat) // 2]

    def p95_latency(self) -> Optional[float]:
        """Calculate 95th percentile latency."""
        if not self.latencies_ms:
            return None
        sorted_lat = sorted(self.latencies_ms)
        idx = int(len(sorted_lat) * 0.95)
        return sorted_lat[idx]

    def p99_latency(self) -> Optional[float]:
        """Calculate 99th percentile latency."""
        if not self.latencies_ms:
            return None
        sorted_lat = sorted(self.latencies_ms)
        idx = int(len(sorted_lat) * 0.99)
        return sorted_lat[idx]

    def avg_latency(self) -> Optional[float]:
        """Calculate average latency."""
        if not self.latencies_ms:
            return None
        return sum(self.latencies_ms) / len(self.latencies_ms)

    def avg_cost_per_call(self) -> float:
        """Calculate average cost per call."""
        if self.calls == 0:
            return 0.0
        return self.cost_usd / self.calls


class TelemetryCollector:
    """Collects and aggregates skill execution telemetry."""

    def __init__(self, metrics_file: str = "/home/kloros/.kloros/telemetry/skill_metrics.jsonl"):
        self.metrics_file = Path(metrics_file)
        self.metrics_file.parent.mkdir(parents=True, exist_ok=True)

        # In-memory metrics (skill@version -> SkillMetrics)
        self.metrics: Dict[str, SkillMetrics] = {}

    def record_execution(
        self,
        skill: str,
        version: str,
        latency_ms: int,
        success: bool,
        tokens_in: int = 0,
        tokens_out: int = 0,
        model: Optional[str] = None
    ):
        """
        Record a skill execution.

        Args:
            skill: Skill name
            version: Skill version
            latency_ms: Execution latency in milliseconds
            success: Whether execution succeeded
            tokens_in: Input tokens (if LLM call)
            tokens_out: Output tokens (if LLM call)
            model: Model name (e.g., "claude-sonnet-4", "gpt-4o")
        """
        key = f"{skill}@{version}"

        if key not in self.metrics:
            self.metrics[key] = SkillMetrics(skill=skill, version=version)

        m = self.metrics[key]
        m.calls += 1
        m.latencies_ms.append(latency_ms)
        m.tokens_in += tokens_in
        m.tokens_out += tokens_out

        # Calculate and track cost
        if model and (tokens_in > 0 or tokens_out > 0):
            cost = calculate_cost(tokens_in, tokens_out, model)
            m.cost_usd += cost

            # Track model usage
            if model not in m.model_usage:
                m.model_usage[model] = 0
            m.model_usage[model] += 1

        if not success:
            m.errors += 1

        m.last_updated = time.time()

        # Persist to file
        self._append_to_file(m)

    def get_metrics(self, skill: str, version: str) -> Optional[SkillMetrics]:
        """Get metrics for a skill."""
        key = f"{skill}@{version}"
        return self.metrics.get(key)

    def _append_to_file(self, metrics: SkillMetrics):
        """Append metrics to file."""
        try:
            with open(self.metrics_file, 'a') as f:
                entry = {
                    "ts": time.time(),
                    "skill": metrics.skill,
                    "version": metrics.version,
                    "calls": metrics.calls,
                    "errors": metrics.errors,
                    "error_rate": metrics.error_rate(),
                    "p50_latency_ms": metrics.p50_latency(),
                    "p95_latency_ms": metrics.p95_latency(),
                    "p99_latency_ms": metrics.p99_latency(),
                    "avg_latency_ms": metrics.avg_latency(),
                    "tokens_in": metrics.tokens_in,
                    "tokens_out": metrics.tokens_out,
                    "cost_usd": round(metrics.cost_usd, 6),
                    "avg_cost_per_call": round(metrics.avg_cost_per_call(), 6),
                    "model_usage": metrics.model_usage,
                }
                f.write(json.dumps(entry) + '\n')
        except Exception as e:
            # Silently fail (telemetry should not break execution)
            pass

    def load_metrics_from_file(self, skill: str, version: str) -> Optional[SkillMetrics]:
        """Load metrics from file."""
        if not self.metrics_file.exists():
            return None

        try:
            with open(self.metrics_file, 'r') as f:
                lines = f.readlines()

            # Find most recent entry for this skill
            for line in reversed(lines):
                try:
                    entry = json.loads(line.strip())
                    if entry.get("skill") == skill and entry.get("version") == version:
                        # Reconstruct SkillMetrics (approximate)
                        m = SkillMetrics(
                            skill=skill,
                            version=version,
                            calls=entry.get("calls", 0),
                            errors=entry.get("errors", 0),
                            tokens_in=entry.get("tokens_in", 0),
                            tokens_out=entry.get("tokens_out", 0),
                            cost_usd=entry.get("cost_usd", 0.0),
                            model_usage=entry.get("model_usage", {})
                        )
                        return m
                except json.JSONDecodeError:
                    continue

        except Exception:
            pass

        return None

    def get_cost_summary(self) -> Dict[str, float]:
        """
        Get cost summary across all skills.

        Returns:
            Dict mapping skill names to total cost
        """
        summary = {}
        for key, metrics in self.metrics.items():
            summary[key] = metrics.cost_usd
        return summary


# Global collector instance
_collector: Optional[TelemetryCollector] = None


def get_telemetry_collector() -> TelemetryCollector:
    """Get or create global telemetry collector."""
    global _collector
    if _collector is None:
        _collector = TelemetryCollector()
    return _collector
