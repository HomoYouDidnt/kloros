#!/usr/bin/env python3
"""
D-REAM Evaluation Plan Module
Regime-based and hold-out evaluation strategies.
"""

from dataclasses import dataclass, field
from typing import List, Tuple, Optional, Iterator, Dict, Any
from datetime import datetime, timedelta
import logging

logger = logging.getLogger(__name__)


@dataclass
class RegimeWindow:
    """
    Evaluation regime with train/test windows.
    """
    name: str
    train: Tuple[str, str]  # (start_date, end_date)
    test: Tuple[str, str]   # (start_date, end_date)
    embargo_days: int = 0    # Gap between train and test
    metadata: Dict[str, Any] = field(default_factory=dict)

    def __post_init__(self):
        """Validate regime window."""
        # Parse dates for validation
        train_start = datetime.fromisoformat(self.train[0])
        train_end = datetime.fromisoformat(self.train[1])
        test_start = datetime.fromisoformat(self.test[0])
        test_end = datetime.fromisoformat(self.test[1])

        # Validate date ordering
        assert train_start < train_end, f"Invalid train window: {self.train}"
        assert test_start < test_end, f"Invalid test window: {self.test}"
        
        # Check embargo
        if self.embargo_days > 0:
            embargo_start = train_end + timedelta(days=1)
            embargo_end = embargo_start + timedelta(days=self.embargo_days)
            assert test_start >= embargo_end, \
                f"Test start {test_start} violates embargo (ends {embargo_end})"

    def get_train_days(self) -> int:
        """Calculate number of training days."""
        start = datetime.fromisoformat(self.train[0])
        end = datetime.fromisoformat(self.train[1])
        return (end - start).days + 1

    def get_test_days(self) -> int:
        """Calculate number of test days."""
        start = datetime.fromisoformat(self.test[0])
        end = datetime.fromisoformat(self.test[1])
        return (end - start).days + 1

    def describe(self) -> str:
        """Get human-readable description."""
        train_days = self.get_train_days()
        test_days = self.get_test_days()
        embargo_str = f" (embargo={self.embargo_days}d)" if self.embargo_days > 0 else ""
        return (f"{self.name}: train={train_days}d ({self.train[0]} to {self.train[1]}), "
               f"test={test_days}d ({self.test[0]} to {self.test[1]}){embargo_str}")


@dataclass
class EvaluationPlan:
    """
    Complete evaluation plan with multiple regimes.
    """
    windows: List[RegimeWindow]
    min_train_days: int = 365  # Minimum training period
    min_test_days: int = 30    # Minimum test period
    max_lookahead: int = 0     # Maximum lookahead bias check
    metadata: Dict[str, Any] = field(default_factory=dict)

    def __post_init__(self):
        """Validate evaluation plan."""
        if not self.windows:
            raise ValueError("Evaluation plan must have at least one regime")

        # Check minimum periods
        for window in self.windows:
            train_days = window.get_train_days()
            test_days = window.get_test_days()
            
            if train_days < self.min_train_days:
                logger.warning(f"Regime {window.name} has short training period: {train_days} days")
            if test_days < self.min_test_days:
                logger.warning(f"Regime {window.name} has short test period: {test_days} days")

    def iter(self) -> Iterator[RegimeWindow]:
        """Iterate over regime windows."""
        for window in self.windows:
            yield window

    def get_regime(self, name: str) -> Optional[RegimeWindow]:
        """Get regime by name."""
        for window in self.windows:
            if window.name == name:
                return window
        return None

    def describe(self) -> str:
        """Get plan description."""
        desc = f"Evaluation Plan: {len(self.windows)} regimes\n"
        for window in self.windows:
            desc += f"  - {window.describe()}\n"
        return desc


class RegimeGenerator:
    """Generate evaluation regimes programmatically."""

    @staticmethod
    def walk_forward(start_date: str,
                    end_date: str,
                    train_months: int = 36,
                    test_months: int = 12,
                    step_months: int = 12,
                    embargo_days: int = 5) -> EvaluationPlan:
        """
        Generate walk-forward evaluation regimes.

        Args:
            start_date: Overall start date (YYYY-MM-DD)
            end_date: Overall end date (YYYY-MM-DD)
            train_months: Training window size
            test_months: Test window size
            step_months: Step size between regimes
            embargo_days: Days between train and test

        Returns:
            EvaluationPlan with generated regimes
        """
        regimes = []
        current = datetime.fromisoformat(start_date)
        end = datetime.fromisoformat(end_date)

        regime_num = 1
        while True:
            # Define train window
            train_start = current
            train_end = train_start + timedelta(days=train_months * 30) - timedelta(days=1)
            
            # Define test window (with embargo)
            test_start = train_end + timedelta(days=embargo_days + 1)
            test_end = test_start + timedelta(days=test_months * 30) - timedelta(days=1)
            
            # Check if we exceed the end date
            if test_end > end:
                break

            # Create regime
            regime = RegimeWindow(
                name=f"WF{regime_num:02d}_{train_start.year}-{test_start.year}",
                train=(train_start.date().isoformat(), train_end.date().isoformat()),
                test=(test_start.date().isoformat(), test_end.date().isoformat()),
                embargo_days=embargo_days
            )
            regimes.append(regime)

            # Step forward
            current += timedelta(days=step_months * 30)
            regime_num += 1

        return EvaluationPlan(windows=regimes)

    @staticmethod
    def k_fold_time_series(start_date: str,
                          end_date: str,
                          n_folds: int = 5,
                          embargo_days: int = 5) -> EvaluationPlan:
        """
        Generate time-series aware k-fold cross-validation.

        Args:
            start_date: Overall start date
            end_date: Overall end date
            n_folds: Number of folds
            embargo_days: Days between train and test

        Returns:
            EvaluationPlan with k-fold regimes
        """
        regimes = []
        start = datetime.fromisoformat(start_date)
        end = datetime.fromisoformat(end_date)
        total_days = (end - start).days + 1

        # Calculate fold size
        fold_days = total_days // n_folds

        for fold in range(n_folds - 1):  # Last fold is always test
            # Training: all data before this fold's test set
            test_fold_start = start + timedelta(days=(fold + 1) * fold_days)
            test_fold_end = test_fold_start + timedelta(days=fold_days - 1)
            
            train_start = start
            train_end = test_fold_start - timedelta(days=embargo_days + 1)

            # Ensure we have enough training data
            if (train_end - train_start).days < 30:
                continue

            regime = RegimeWindow(
                name=f"Fold{fold+1}of{n_folds}",
                train=(train_start.date().isoformat(), train_end.date().isoformat()),
                test=(test_fold_start.date().isoformat(), test_fold_end.date().isoformat()),
                embargo_days=embargo_days
            )
            regimes.append(regime)

        if not regimes:
            raise ValueError(f"Unable to generate valid folds for date range")

        return EvaluationPlan(windows=regimes)


def create_plan_from_config(config: Dict) -> EvaluationPlan:
    """
    Create evaluation plan from configuration.

    Args:
        config: Configuration dictionary with 'regimes' list

    Returns:
        Configured EvaluationPlan
    """
    regime_configs = config.get('regimes', [])
    if not regime_configs:
        raise ValueError("No regimes defined in config")

    windows = []
    for regime_cfg in regime_configs:
        window = RegimeWindow(
            name=regime_cfg['name'],
            train=tuple(regime_cfg['train']),
            test=tuple(regime_cfg['test']),
            embargo_days=regime_cfg.get('embargo_days', 0),
            metadata=regime_cfg.get('metadata', {})
        )
        windows.append(window)

    plan_metadata = config.get('metadata', {})
    min_train_days = config.get('min_train_days', 365)
    min_test_days = config.get('min_test_days', 30)

    return EvaluationPlan(
        windows=windows,
        min_train_days=min_train_days,
        min_test_days=min_test_days,
        metadata=plan_metadata
    )


class RegimeEvaluator:
    """Helper class for regime-based evaluation."""

    def __init__(self, plan: EvaluationPlan):
        """
        Initialize evaluator with plan.

        Args:
            plan: Evaluation plan to execute
        """
        self.plan = plan
        self.results = {}

    def evaluate(self, evaluator_func, candidate) -> Dict[str, Any]:
        """
        Evaluate candidate across all regimes.

        Args:
            evaluator_func: Function(candidate, regime) -> metrics dict
            candidate: Candidate to evaluate

        Returns:
            Dictionary with per-regime and aggregate results
        """
        regime_results = []

        for regime in self.plan.iter():
            logger.info(f"Evaluating on regime: {regime.name}")
            
            try:
                metrics = evaluator_func(candidate, regime)
                regime_results.append({
                    'regime': regime.name,
                    'metrics': metrics,
                    'train_days': regime.get_train_days(),
                    'test_days': regime.get_test_days()
                })
            except Exception as e:
                logger.error(f"Evaluation failed for regime {regime.name}: {e}")
                regime_results.append({
                    'regime': regime.name,
                    'error': str(e)
                })

        return {
            'candidate': candidate,
            'regime_results': regime_results,
            'n_regimes': len(regime_results),
            'n_successful': sum(1 for r in regime_results if 'metrics' in r)
        }
