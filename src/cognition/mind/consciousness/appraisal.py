"""
Appraisal System - Mapping Interoceptive Signals to Affects

This module implements transparent mathematical formulas that map
internal state signals to affective dimensions.

Based on GPT suggestions for Phase 2C.
"""

import math
import yaml
import os
from pathlib import Path
from typing import Dict, List, Tuple, Optional
from dataclasses import dataclass

from .models import Affect
from .interoception import InteroceptiveSignals


@dataclass
class AppraisalWeights:
    """
    Weights for appraisal formulas.

    These can be tuned by hand or stored in YAML for quick iteration.
    """
    # Valence formula weights
    valence_success: float = 0.6
    valence_error: float = -0.5
    valence_resource_strain: float = -0.3

    # Arousal formula weights
    arousal_surprise: float = 0.5
    arousal_deadline: float = 0.3
    arousal_backlog: float = 0.2

    # Dominance formula weights
    dominance_tool_success: float = 0.5
    dominance_retry: float = -0.4
    dominance_rate_limit: float = -0.3

    # Uncertainty formula weights
    uncertainty_epistemic: float = 0.5
    uncertainty_novelty: float = 0.4
    uncertainty_confidence: float = -0.3

    # Fatigue formula weights
    fatigue_context: float = 0.4
    fatigue_token: float = 0.3
    fatigue_cache_miss: float = 0.2
    fatigue_memory: float = 0.1

    # Curiosity formula weights (with sigmoid)
    curiosity_surprise: float = 0.5
    curiosity_novelty: float = 0.4
    curiosity_fatigue: float = -0.3
    curiosity_deadline: float = -0.2

    # EMA smoothing
    ema_alpha: float = 0.2  # 0.2 = smooth, 0.8 = responsive


class AppraisalSystem:
    """
    Transparent appraisal system mapping signals to affects.

    Uses simple linear combinations + a few saturating functions (sigmoid)
    to maintain interpretability while capturing nonlinear dynamics.
    """

    def __init__(self, weights: Optional[AppraisalWeights] = None,
                 config_path: Optional[Path] = None):
        """
        Initialize appraisal system.

        Args:
            weights: AppraisalWeights object (uses defaults if None)
            config_path: Path to YAML config file for weights
        """
        if config_path and config_path.exists():
            self.weights = self._load_weights_from_yaml(config_path)
        elif weights:
            self.weights = weights
        else:
            self.weights = AppraisalWeights()

        # Previous affect state for EMA smoothing
        self.previous_affect = Affect()

        # Evidence tracking for reporting
        self.last_evidence: List[str] = []

    def _load_weights_from_yaml(self, path: Path) -> AppraisalWeights:
        """Load appraisal weights from YAML file."""
        with open(path, 'r') as f:
            config = yaml.safe_load(f)

        return AppraisalWeights(**config.get('appraisal_weights', {}))

    def save_weights_to_yaml(self, path: Path):
        """Save current weights to YAML file."""
        config = {
            'appraisal_weights': {
                'valence_success': self.weights.valence_success,
                'valence_error': self.weights.valence_error,
                'valence_resource_strain': self.weights.valence_resource_strain,
                'arousal_surprise': self.weights.arousal_surprise,
                'arousal_deadline': self.weights.arousal_deadline,
                'arousal_backlog': self.weights.arousal_backlog,
                'dominance_tool_success': self.weights.dominance_tool_success,
                'dominance_retry': self.weights.dominance_retry,
                'dominance_rate_limit': self.weights.dominance_rate_limit,
                'uncertainty_epistemic': self.weights.uncertainty_epistemic,
                'uncertainty_novelty': self.weights.uncertainty_novelty,
                'uncertainty_confidence': self.weights.uncertainty_confidence,
                'fatigue_context': self.weights.fatigue_context,
                'fatigue_token': self.weights.fatigue_token,
                'fatigue_cache_miss': self.weights.fatigue_cache_miss,
                'fatigue_memory': self.weights.fatigue_memory,
                'curiosity_surprise': self.weights.curiosity_surprise,
                'curiosity_novelty': self.weights.curiosity_novelty,
                'curiosity_fatigue': self.weights.curiosity_fatigue,
                'curiosity_deadline': self.weights.curiosity_deadline,
                'ema_alpha': self.weights.ema_alpha,
            }
        }

        with open(path, 'w') as f:
            yaml.dump(config, f, default_flow_style=False)

    @staticmethod
    def sigmoid(x: float, scale: float = 1.0) -> float:
        """Sigmoid function for smooth saturation."""
        return 1.0 / (1.0 + math.exp(-scale * x))

    @staticmethod
    def clamp(value: float, min_val: float, max_val: float) -> float:
        """Clamp value to range."""
        return max(min_val, min(max_val, value))

    def compute_valence(self, signals: InteroceptiveSignals) -> Tuple[float, List[str]]:
        """
        Compute valence (pleasure/displeasure) from signals.

        Formula:
            valence = +w1*success_rate - w2*error_rate - w3*resource_strain

        Returns:
            (valence, evidence_list)
        """
        evidence = []

        # Resource strain combines multiple pressures
        resource_strain = (
            signals.token_budget_pressure +
            signals.context_length_pressure +
            signals.memory_pressure
        ) / 3.0

        valence = (
            self.weights.valence_success * signals.success_rate +
            self.weights.valence_error * signals.error_rate +
            self.weights.valence_resource_strain * resource_strain
        )

        # Clamp to [-1, 1]
        valence = self.clamp(valence, -1.0, 1.0)

        # Build evidence
        if signals.success_rate > 0.7:
            evidence.append(f"high success rate ({signals.success_rate:.2f})")
        if signals.error_rate > 0.3:
            evidence.append(f"elevated errors ({signals.error_rate:.2f})")
        if resource_strain > 0.6:
            evidence.append(f"resource strain ({resource_strain:.2f})")

        return valence, evidence

    def compute_arousal(self, signals: InteroceptiveSignals) -> Tuple[float, List[str]]:
        """
        Compute arousal (activation/energy) from signals.

        Formula:
            arousal = +u1*surprise + u2*deadline_pressure + u3*queue_backlog

        Returns:
            (arousal, evidence_list)
        """
        evidence = []

        # Deadline pressure (not directly measured, infer from error rate + retries)
        deadline_pressure = min(1.0, (signals.retry_count + signals.timeout_rate) / 2.0)

        arousal = (
            self.weights.arousal_surprise * signals.surprise +
            self.weights.arousal_deadline * deadline_pressure +
            self.weights.arousal_backlog * signals.queue_backlog
        )

        # Clamp to [0, 1]
        arousal = self.clamp(arousal, 0.0, 1.0)

        # Build evidence
        if signals.surprise > 0.5:
            evidence.append(f"high surprise ({signals.surprise:.2f})")
        if deadline_pressure > 0.5:
            evidence.append(f"deadline pressure ({deadline_pressure:.2f})")
        if signals.queue_backlog > 0.5:
            evidence.append(f"task backlog ({signals.queue_backlog:.2f})")

        return arousal, evidence

    def compute_dominance(self, signals: InteroceptiveSignals) -> Tuple[float, List[str]]:
        """
        Compute dominance (control/efficacy) from signals.

        Formula:
            dominance = +d1*tool_success - d2*retry_ratio - d3*rate_limit_pressure

        Returns:
            (dominance, evidence_list)
        """
        evidence = []

        # Tool success is inverse of error rate
        tool_success = 1.0 - signals.error_rate

        # Retry ratio
        retry_ratio = min(1.0, signals.retry_count / 5.0)  # 5+ retries = 1.0

        # Rate limit pressure (infer from timeouts + exceptions)
        rate_limit_pressure = (signals.timeout_rate + signals.exception_rate) / 2.0

        dominance = (
            self.weights.dominance_tool_success * tool_success +
            self.weights.dominance_retry * retry_ratio +
            self.weights.dominance_rate_limit * rate_limit_pressure
        )

        # Clamp to [-1, 1]
        dominance = self.clamp(dominance, -1.0, 1.0)

        # Build evidence
        if tool_success > 0.8:
            evidence.append(f"high tool success ({tool_success:.2f})")
        if retry_ratio > 0.4:
            evidence.append(f"frequent retries ({signals.retry_count})")
        if rate_limit_pressure > 0.3:
            evidence.append(f"stability issues ({rate_limit_pressure:.2f})")

        return dominance, evidence

    def compute_uncertainty(self, signals: InteroceptiveSignals) -> Tuple[float, List[str]]:
        """
        Compute epistemic uncertainty from signals.

        Formula:
            uncertainty = +q1*epistemic_uncert + q2*novelty - q3*confidence

        Returns:
            (uncertainty, evidence_list)
        """
        evidence = []

        # Epistemic uncertainty (low confidence + high novelty)
        epistemic_uncert = 1.0 - signals.confidence

        uncertainty = (
            self.weights.uncertainty_epistemic * epistemic_uncert +
            self.weights.uncertainty_novelty * signals.novelty_score +
            self.weights.uncertainty_confidence * signals.confidence
        )

        # Clamp to [0, 1]
        uncertainty = self.clamp(uncertainty, 0.0, 1.0)

        # Build evidence
        if epistemic_uncert > 0.5:
            evidence.append(f"low confidence ({signals.confidence:.2f})")
        if signals.novelty_score > 0.5:
            evidence.append(f"novel situation ({signals.novelty_score:.2f})")

        return uncertainty, evidence

    def compute_fatigue(self, signals: InteroceptiveSignals) -> Tuple[float, List[str]]:
        """
        Compute cognitive fatigue/resource strain.

        Formula:
            fatigue = +f1*context_pressure + f2*token_pressure +
                      f3*cache_miss_rate + f4*memory_pressure

        Returns:
            (fatigue, evidence_list)
        """
        evidence = []

        cache_miss_rate = 1.0 - signals.cache_hit_rate

        fatigue = (
            self.weights.fatigue_context * signals.context_length_pressure +
            self.weights.fatigue_token * signals.token_budget_pressure +
            self.weights.fatigue_cache_miss * cache_miss_rate +
            self.weights.fatigue_memory * signals.memory_pressure
        )

        # Clamp to [0, 1]
        fatigue = self.clamp(fatigue, 0.0, 1.0)

        # Build evidence
        if signals.context_length_pressure > 0.7:
            evidence.append(f"context pressure ({signals.context_length_pressure:.2f})")
        if signals.token_budget_pressure > 0.7:
            evidence.append(f"token pressure ({signals.token_budget_pressure:.2f})")
        if cache_miss_rate > 0.5:
            evidence.append(f"cache misses ({cache_miss_rate:.2f})")

        return fatigue, evidence

    def compute_curiosity(self, signals: InteroceptiveSignals,
                          fatigue: float) -> Tuple[float, List[str]]:
        """
        Compute curiosity (information seeking drive).

        Formula with sigmoid:
            curiosity = σ(c1*surprise + c2*novelty - c3*fatigue - c4*deadline)

        Returns:
            (curiosity, evidence_list)
        """
        evidence = []

        # Deadline pressure
        deadline_pressure = min(1.0, (signals.retry_count + signals.timeout_rate) / 2.0)

        # Linear combination
        curiosity_raw = (
            self.weights.curiosity_surprise * signals.surprise +
            self.weights.curiosity_novelty * signals.novelty_score +
            self.weights.curiosity_fatigue * fatigue +
            self.weights.curiosity_deadline * deadline_pressure
        )

        # Apply sigmoid for smooth saturation
        curiosity = self.sigmoid(curiosity_raw, scale=2.0)

        # Build evidence
        if signals.surprise > 0.5:
            evidence.append(f"surprising situation ({signals.surprise:.2f})")
        if signals.novelty_score > 0.5:
            evidence.append(f"novel context ({signals.novelty_score:.2f})")
        if fatigue > 0.7:
            evidence.append(f"high fatigue suppressing curiosity ({fatigue:.2f})")

        return curiosity, evidence

    def appraise(self, signals: InteroceptiveSignals) -> Tuple[Affect, List[str]]:
        """
        Full appraisal: map interoceptive signals to affective state.

        Args:
            signals: Current interoceptive signals

        Returns:
            (affect, evidence_list)
        """
        all_evidence = []

        # Compute each dimension
        valence, val_evidence = self.compute_valence(signals)
        arousal, aro_evidence = self.compute_arousal(signals)
        dominance, dom_evidence = self.compute_dominance(signals)
        uncertainty, unc_evidence = self.compute_uncertainty(signals)
        fatigue, fat_evidence = self.compute_fatigue(signals)
        curiosity, cur_evidence = self.compute_curiosity(signals, fatigue)

        # Combine evidence
        all_evidence.extend(val_evidence)
        all_evidence.extend(aro_evidence)
        all_evidence.extend(dom_evidence)
        all_evidence.extend(unc_evidence)
        all_evidence.extend(fat_evidence)
        all_evidence.extend(cur_evidence)

        # Create raw affect
        affect_raw = Affect(
            valence=valence,
            arousal=arousal,
            dominance=dominance,
            uncertainty=uncertainty,
            fatigue=fatigue,
            curiosity=curiosity
        )

        # Apply EMA smoothing
        alpha = self.weights.ema_alpha
        affect_smooth = Affect(
            valence=alpha * valence + (1 - alpha) * self.previous_affect.valence,
            arousal=alpha * arousal + (1 - alpha) * self.previous_affect.arousal,
            dominance=alpha * dominance + (1 - alpha) * self.previous_affect.dominance,
            uncertainty=alpha * uncertainty + (1 - alpha) * self.previous_affect.uncertainty,
            fatigue=alpha * fatigue + (1 - alpha) * self.previous_affect.fatigue,
            curiosity=alpha * curiosity + (1 - alpha) * self.previous_affect.curiosity
        )

        # Update previous state
        self.previous_affect = affect_smooth

        # Store evidence
        self.last_evidence = all_evidence

        return affect_smooth, all_evidence

    def get_affect_description(self, affect: Affect) -> str:
        """
        Generate natural language description of affect state.

        Args:
            affect: Affect state

        Returns:
            Natural language description
        """
        parts = []

        # Valence
        if affect.valence > 0.5:
            parts.append("positive")
        elif affect.valence < -0.5:
            parts.append("negative")
        else:
            parts.append("neutral")

        # Arousal
        if affect.arousal > 0.7:
            parts.append("highly energized")
        elif affect.arousal > 0.4:
            parts.append("activated")
        else:
            parts.append("calm")

        # Dominance
        if affect.dominance > 0.5:
            parts.append("in control")
        elif affect.dominance < -0.5:
            parts.append("constrained")

        # Uncertainty
        if affect.uncertainty > 0.7:
            parts.append("uncertain")

        # Fatigue
        if affect.fatigue > 0.7:
            parts.append("fatigued")

        # Curiosity
        if affect.curiosity > 0.7:
            parts.append("curious")

        return ", ".join(parts)
