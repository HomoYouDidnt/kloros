#!/usr/bin/env python3
"""
Unit tests for novelty module.
"""

import unittest
import numpy as np
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from novelty import BehaviorArchive, correlation_penalty, pareto_front


class TestBehaviorArchive(unittest.TestCase):
    """Test behavior archive for novelty calculation."""

    def setUp(self):
        """Set up test archive."""
        self.archive = BehaviorArchive(k=3, max_size=10)

    def test_novelty_increases_with_distance(self):
        """Test that novelty increases with distance from archive."""
        # Add some behaviors to archive
        self.archive.add(np.array([0, 0, 0]))
        self.archive.add(np.array([1, 0, 0]))
        self.archive.add(np.array([0, 1, 0]))

        # Test close behavior (low novelty)
        close_vec = np.array([0.1, 0.1, 0])
        close_novelty = self.archive.novelty(close_vec)

        # Test far behavior (high novelty)
        far_vec = np.array([10, 10, 10])
        far_novelty = self.archive.novelty(far_vec)

        self.assertGreater(far_novelty, close_novelty)

    def test_archive_size_limit(self):
        """Test that archive respects max size."""
        for i in range(15):
            self.archive.add(np.array([i, i, i]))
        
        self.assertLessEqual(len(self.archive.vectors), 10)


class TestCorrelationPenalty(unittest.TestCase):
    """Test correlation penalty calculation."""

    def test_penalty_in_range(self):
        """Test correlation penalty is in [0,1]."""
        candidate = np.array([1, 2, 3])
        champions = [
            np.array([1, 2, 3]),  # Identical
            np.array([2, 4, 6]),  # Perfectly correlated
            np.array([-1, -2, -3])  # Negatively correlated
        ]

        penalty = correlation_penalty(candidate, champions)
        self.assertGreaterEqual(penalty, 0.0)
        self.assertLessEqual(penalty, 1.0)

    def test_empty_champions(self):
        """Test with no champions."""
        candidate = np.array([1, 2, 3])
        penalty = correlation_penalty(candidate, [])
        self.assertEqual(penalty, 0.0)


class TestParetoFront(unittest.TestCase):
    """Test Pareto front calculation."""

    def test_pareto_front_2d(self):
        """Test Pareto front with 2 objectives."""
        points = [
            {'a': 1, 'b': 1},
            {'a': 2, 'b': 2},  # Dominates first
            {'a': 3, 'b': 1},  # Non-dominated
            {'a': 1, 'b': 3},  # Non-dominated
        ]

        front = pareto_front(points, ['a', 'b'], maximize=True)
        
        # Points 1, 2, 3 should be on front
        self.assertIn(1, front)  # (2,2)
        self.assertIn(2, front)  # (3,1)
        self.assertIn(3, front)  # (1,3)
        self.assertNotIn(0, front)  # (1,1) is dominated

    def test_single_point(self):
        """Test with single point."""
        points = [{'x': 1, 'y': 2}]
        front = pareto_front(points, ['x', 'y'])
        self.assertEqual(front, [0])


if __name__ == '__main__':
    unittest.main()
