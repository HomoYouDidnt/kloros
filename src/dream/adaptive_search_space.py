from __future__ import annotations
import itertools
import logging
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, List, Tuple, Any, Optional
from functools import reduce
import operator

import numpy as np

logger = logging.getLogger(__name__)


@dataclass
class ParamSafety:
    min: Optional[float] = None
    max: Optional[float] = None
    max_values: Optional[int] = None

@dataclass
class ParamSafety:
    min: Optional[float] = None
    max: Optional[float] = None
    max_values: Optional[int] = None


class AdaptiveSearchSpaceManager:
    """Manages dynamic search space adaptation based on the fitness landscape.

    The manager is *pure* (no I/O side effects) and returns updated search spaces.
    It supports numeric (int/float) and categorical parameters.

    YAML structure per-parameter (example):
        threshold:
          initial: [0.01, 0.02, 0.05]
          expansion:
            plateau: {enabled: true, patience: 3, action: expand_bounds, factor: 2.0}
            boundary: {enabled: true, action: extend_edge, extension: 3}
            coverage: {enabled: true, threshold: 0.75, action: subdivide}
          safety: {min: 0.0001, max: 1.0, max_values: 20}

    Notes:
        - For categorical params, only `boundary`/`coverage` triggers apply, and actions
          are limited to *pruning* unpromising values (abandon_region) or keeping diversity.
    """

    def __init__(self, config: Dict[str, Any]):
        """Initialize manager with an experiment config subtree.

        Args:
            config: Experiment config with `search_space` and optional `adaptive` fields.
        """
        self.config = config
        self.space_cfg: Dict[str, Any] = config.get("search_space", {})
        self.adaptive_enabled: bool = bool(self.space_cfg.get("adaptive", False))
        # Per-parameter definitions (may contain `initial`, `expansion`, `safety`)
        self.params_cfg: Dict[str, Any] = {
            k: v for k, v in self.space_cfg.items()
            if isinstance(v, dict) and any(x in v for x in ("initial", "expansion", "safety"))
        }
        # Runtime trigger cache
        self._last_trigger: Optional[str] = None

    # -------------------- Public API --------------------
    def should_adapt(
        self,
        generation: int,
        fitness_history: List[float],
        best_config: Dict[str, Any],
        evaluated_configs: Optional[List[Dict[str, Any]]] = None,
    ) -> bool:
        """Check if search space should be adapted.

        Args:
            generation: Current generation index (0-based).
            fitness_history: Historical best fitness per generation.
            best_config: Best params at this generation.
            evaluated_configs: All evaluated param dicts so far (optional).

        Returns:
            True if any adaptation trigger fires.
        """
        if not self.adaptive_enabled or generation < 0:
            return False

        # Trigger order: plateau -> boundary -> coverage
        if self._detect_plateau(fitness_history):
            self._last_trigger = "plateau"
            return True
        if self._detect_boundary_convergence(best_config):
            self._last_trigger = "boundary"
            return True
        if evaluated_configs is not None and self._detect_high_coverage(evaluated_configs):
            self._last_trigger = "coverage"
            return True
        return False

    def get_trigger(self) -> Optional[str]:
        return self._last_trigger

    def adapt_space(
        self,
        trigger: str,
        fitness_history: List[float],
        best_config: Dict[str, Any],
        current_space: Dict[str, List[Any]],
    ) -> Dict[str, List[Any]]:
        """Adapt search space based on the given trigger.

        Args:
            trigger: One of {"plateau","boundary","coverage"}
            fitness_history: Best fitness per generation
            best_config: Best parameter assignment
            current_space: Current discrete search space {param: [values...]}

        Returns:
            Updated search space dict (copy). Values are deduplicated and sorted where numeric.
        """
        new_space = {k: list(v) for k, v in current_space.items() if k in self.params_cfg}
        if trigger == "plateau":
            for p in self.params_cfg:
                rule = self._get_rule(p, "plateau")
                if not rule:
                    continue
                action = (rule.get("action") or "expand_bounds").lower()
                if action == "expand_bounds":
                    factor = float(rule.get("factor", 1.5))
                    new_space[p] = self._expand_bounds(p, new_space[p], factor)
                elif action == "subdivide":
                    new_space[p] = self._subdivide_range(p, new_space[p], best_config.get(p))
        elif trigger == "boundary":
            for p in self.params_cfg:
                rule = self._get_rule(p, "boundary")
                if not rule:
                    continue
                action = (rule.get("action") or "extend_edge").lower()
                if action in ("extend_edge", "expand_bounds"):
                    ext = int(rule.get("extension", 2))
                    new_space[p] = self._extend_edge_toward_best(p, new_space[p], best_config.get(p), ext)
        elif trigger == "coverage":
            for p in self.params_cfg:
                rule = self._get_rule(p, "coverage")
                if not rule:
                    continue
                action = (rule.get("action") or "subdivide").lower()
                if action == "subdivide":
                    new_space[p] = self._subdivide_range(p, new_space[p], best_config.get(p))
                elif action == "abandon_region":
                    new_space[p] = self._abandon_region(p, new_space[p], fitness_history)

        # Safety & normalization
        valid, msgs = self.validate_bounds(new_space)
        if not valid:
            logger.info("Adaptation blocked by safety checks: %s", msgs)
            return current_space
        return self._normalize(new_space)

    def validate_bounds(self, new_space: Dict[str, List[Any]]) -> Tuple[bool, List[str]]:
        """Validate new space respects safety limits.

        Returns:
            (is_valid, violation_messages)
        """
        violations: List[str] = []
        # type & size checks
        if not self._validate_types(new_space):
            violations.append("type_validation_failed")
        if not self._check_max_size(new_space):
            violations.append("max_size_exceeded")
        # per-param absolute bounds
        for p, vals in new_space.items():
            ok, msg = self._check_absolute_bounds(p, vals)
            if not ok:
                violations.append(f"{p}:{msg}")
        return (len(violations) == 0, violations)

    # -------------------- Trigger detection --------------------
    def _detect_plateau(self, fitness_history: List[float]) -> bool:
        # Use per-param config; if any has plateau enabled, apply global patience=min(patiences)
        patiences = [self._get_rule(p, "plateau").get("patience", 0)
                     for p in self.params_cfg if self._get_rule(p, "plateau").get("enabled")]
        if not patiences:
            return False
        patience = int(min(patiences))
        if patience <= 0 or len(fitness_history) < patience + 1:
            return False
        tail = fitness_history[-(patience + 1):]
        # improvement means strictly greater max in the tail's last element vs previous
        return max(tail[:-1]) >= tail[-1]

    def _detect_boundary_convergence(self, best_config: Dict[str, Any]) -> bool:
        hit = False
        for p, cfg in self.params_cfg.items():
            vals = self._current_values_for_param(p)
            if not vals:
                continue
            if best_config.get(p) in (min(vals), max(vals)):
                rule = self._get_rule(p, "boundary")
                if rule.get("enabled"):
                    hit = True
        return hit

    def _detect_high_coverage(self, evaluated_configs: List[Dict[str, Any]]) -> bool:
        # Coverage measured as fraction of cartesian combos seen.
        # Approximate: product of unique counts per param, then seen set cardinality.
        keys = list(self.params_cfg.keys())
        if not keys:
            return False
        # build set of tuples of values in order of keys
        seen = {tuple(cfg.get(k) for k in keys) for cfg in evaluated_configs}
        # theoretical combos
        sizes = [len(self._current_values_for_param(k)) or 1 for k in keys]
        total = int(np.product(sizes))
        if total == 0:
            return False
        frac = len(seen) / total
        # any param with coverage trigger set uses the *max* threshold to be conservative
        thresholds = [self._get_rule(k, "coverage").get("threshold", 1.1)
                      for k in keys if self._get_rule(k, "coverage").get("enabled")]
        if not thresholds:
            return False
        thresh = max(thresholds)
        return frac >= float(thresh)

    # -------------------- Mutations --------------------
    def _expand_bounds(self, param: str, values: List[Any], factor: float) -> List[Any]:
        vals = self._coerce_numeric(values)
        if len(vals) < 2:
            return vals
        lo, hi = min(vals), max(vals)
        span = hi - lo
        new_lo = lo - span * (factor - 1.0)
        new_hi = hi + span * (factor - 1.0)
        out = set(vals + [new_lo, new_hi])
        return sorted(out)

    def _subdivide_range(self, param: str, values: List[Any], best_value: Any) -> List[Any]:
        vals = self._coerce_numeric(values)
        if len(vals) < 2:
            return vals
        vals_sorted = sorted(vals)
        # Insert midpoints between nearest neighbors around best_value
        if best_value is None:
            # global refine: add midpoints everywhere
            mids = [(a + b) / 2.0 for a, b in zip(vals_sorted[:-1], vals_sorted[1:])]
            return sorted(set(vals_sorted + mids))
        # find closest segment
        idx = np.searchsorted(vals_sorted, float(best_value))
        idx = max(1, min(idx, len(vals_sorted) - 1))
        a, b = vals_sorted[idx - 1], vals_sorted[idx]
        mids = [(a + b) / 2.0, a + (b - a) / 4.0, a + 3 * (b - a) / 4.0]
        return sorted(set(vals_sorted + mids))

    def _extend_edge_toward_best(self, param: str, values: List[Any], best_value: Any, extension: int) -> List[Any]:
        vals = self._coerce_numeric(values)
        vals_sorted = sorted(vals)
        if best_value is None or best_value == vals_sorted[0]:
            step = (vals_sorted[-1] - vals_sorted[0]) / max(1, len(vals_sorted) - 1)
            new_vals = [vals_sorted[0] - step * i for i in range(1, extension + 1)]
            return sorted(set(vals_sorted + new_vals))
        if best_value == vals_sorted[-1]:
            step = (vals_sorted[-1] - vals_sorted[0]) / max(1, len(vals_sorted) - 1)
            new_vals = [vals_sorted[-1] + step * i for i in range(1, extension + 1)]
            return sorted(set(vals_sorted + new_vals))
        return vals_sorted

    def _abandon_region(self, param: str, values: List[Any], fitness_history: List[float]) -> List[Any]:
        # Simple strategy: keep middle quantiles, drop extremes if fitness stagnates.
        vals = self._coerce_numeric(values)
        if len(vals) <= 3:
            return vals
        q1, q3 = np.quantile(vals, 0.25), np.quantile(vals, 0.75)
        pruned = [v for v in vals if q1 <= v <= q3]
        return sorted(set(pruned))

    # -------------------- Safety & normalization --------------------
    def _check_absolute_bounds(self, param: str, new_values: List[Any]) -> Tuple[bool, str]:
        safety = self._get_safety(param)
        numeric = self._coerce_numeric(new_values, allow_categorical=True)
        if numeric is None:
            return True, "categorical"
        lo = min(numeric)
        hi = max(numeric)
        if safety.min is not None and lo < safety.min:
            return False, f"below_min({lo} < {safety.min})"
        if safety.max is not None and hi > safety.max:
            return False, f"above_max({hi} > {safety.max})"
        if safety.max_values is not None and len(new_values) > safety.max_values:
            return False, f"max_values_exceeded({len(new_values)} > {safety.max_values})"
        return True, "ok"

    def _check_max_size(self, space: Dict[str, List[Any]], global_cap: int = 100000) -> bool:
        # Cap total cartesian combinations to avoid explosion.
        sizes = [max(1, len(v)) for v in space.values()]
        # Overflow-safe product using Python big-ints
        total = reduce(operator.mul, sizes, 1) if sizes else 0
        return total <= global_cap

    def _validate_types(self, space: Dict[str, List[Any]]) -> bool:
        # Ensure lists and scalar types are consistent.
        for k, v in space.items():
            if not isinstance(v, list):
                return False
            if len(v) == 0:
                return False
        return True

    def _normalize(self, space: Dict[str, List[Any]]) -> Dict[str, List[Any]]:
        norm: Dict[str, List[Any]] = {}
        for k, vals in space.items():
            # dedupe
            if all(isinstance(x, (int, float, np.floating)) for x in vals):
                s = sorted(set(float(x) for x in vals))
                norm[k] = [int(x) if self._is_int_like(x) else float(x) for x in s]
            else:
                # categorical — preserve insertion order while deduping
                seen = []
                for x in vals:
                    if x not in seen:
                        seen.append(x)
                norm[k] = seen
        return norm

    # -------------------- Helpers --------------------
    def _get_rule(self, param: str, kind: str) -> Dict[str, Any]:
        cfg = self.params_cfg.get(param, {})
        exp = cfg.get("expansion", {})
        rule = exp.get(kind, {}) if isinstance(exp, dict) else {}
        return rule if rule.get("enabled") else {}

    def _get_safety(self, param: str) -> ParamSafety:
        cfg = self.params_cfg.get(param, {})
        s = cfg.get("safety", {}) if isinstance(cfg, dict) else {}
        return ParamSafety(
            min=s.get("min"), max=s.get("max"), max_values=s.get("max_values")
        )

    def _current_values_for_param(self, param: str) -> List[Any]:
        cfg = self.params_cfg.get(param, {})
        # Prefer `initial` for base; runner should pass current space to adapt_space
        if isinstance(cfg, dict) and "initial" in cfg:
            return list(cfg["initial"]) if isinstance(cfg["initial"], list) else []
        return []

    @staticmethod
    def _coerce_numeric(vals: List[Any], allow_categorical: bool = False) -> Optional[List[float]]:
        out: List[float] = []
        for v in vals:
            if isinstance(v, (int, float, np.floating)):
                out.append(float(v))
            else:
                if allow_categorical:
                    return None
                raise TypeError("non-numeric value in numeric operation")
        return out

    @staticmethod
    def _is_int_like(x: float) -> bool:
        return abs(x - round(x)) < 1e-9
