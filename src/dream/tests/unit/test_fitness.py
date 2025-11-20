#!/usr/bin/env python3
"""
Unit tests for fitness module.
"""

import unittest
import sys
from pathlib import Path

# Add parent directory to path
sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from fitness import FitnessWeights, CompositeFitness, DomainFitness


class TestCompositeFitness(unittest.TestCase):
    """Test composite fitness scoring."""

    def setUp(self):
        """Set up test fixtures."""
        self.weights = FitnessWeights(
            perf=1.0,
            stability=0.5,
            maxdd=3.0,
            turnover=0.1,
            corr=0.2,
            risk=1.0
        )
        self.fitness = CompositeFitness(
            self.weights,
            hard_caps={'maxdd': 0.6, 'risk': 0.8}
        )

    def test_hard_cap_returns_neg_inf(self):
        """Test that hard cap violation returns -inf."""
        metrics = {
            'perf': 1.0,
            'maxdd': 0.7,  # Exceeds cap of 0.6
            'risk': 0.5
        }
        score = self.fitness.score(metrics)
        self.assertEqual(score, float('-inf'))

    def test_aggregate_adds_stability(self):
        """Test that aggregate adds negative std to stability."""
        regime_metrics = [
            {'perf': 1.0, 'maxdd': 0.1},
            {'perf': 0.8, 'maxdd': 0.2},
            {'perf': 1.2, 'maxdd': 0.15}
        ]
        agg = self.fitness.aggregate(regime_metrics)
        
        # Check stability is negative std dev
        self.assertIn('stability', agg)
        self.assertLess(agg['stability'], 0)
        
        # Check aggregated values
        self.assertAlmostEqual(agg['perf'], 1.0, places=2)
        self.assertAlmostEqual(agg['maxdd'], 0.15, places=2)

    def test_score_calculation(self):
        """Test fitness score calculation."""
        metrics = {
            'perf': 1.0,
            'stability': -0.1,
            'maxdd': 0.2,
            'turnover': 0.3,
            'corr': 0.4,
            'risk': 0.5
        }
        
        expected = (
            1.0 * 1.0 +      # perf
            0.5 * (-0.1) +   # stability  
            -3.0 * 0.2 +     # maxdd
            -0.1 * 0.3 +     # turnover
            -0.2 * 0.4 +     # corr
            -1.0 * 0.5       # risk
        )
        
        score = self.fitness.score(metrics)
        self.assertAlmostEqual(score, expected, places=5)


class TestDomainFitness(unittest.TestCase):
    """Test domain-specific fitness functions."""

    def test_sharpe_ratio(self):
        """Test Sharpe ratio calculation."""
        returns = [0.01, 0.02, -0.01, 0.015, 0.005]
        sharpe = DomainFitness.calculate_sharpe(returns)
        self.assertGreater(sharpe, 0)

    def test_drawdown(self):
        """Test maximum drawdown calculation."""
        values = [100, 105, 95, 98, 102, 90, 95]
        dd = DomainFitness.calculate_drawdown(values)
        # Max drawdown from 105 to 90
        expected = (105 - 90) / 105
        self.assertAlmostEqual(dd, expected, places=5)

    def test_turnover(self):
        """Test turnover calculation."""
        old_pos = [0.3, 0.3, 0.4]
        new_pos = [0.4, 0.2, 0.4]
        turnover = DomainFitness.calculate_turnover(old_pos, new_pos)
        # |0.1| + |0.1| + |0| = 0.2, divided by 2
        self.assertAlmostEqual(turnover, 0.1, places=5)


if __name__ == '__main__':
    unittest.main()
