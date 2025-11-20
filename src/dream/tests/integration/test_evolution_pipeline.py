#!/usr/bin/env python3
"""
Integration test for complete evolution pipeline.
"""

import unittest
import tempfile
import shutil
from pathlib import Path
import sys
import json

sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from fitness import CompositeFitness, FitnessWeights
from novelty import BehaviorArchive, pareto_front
from evaluation_plan import EvaluationPlan, RegimeWindow
from telemetry.logger import EventLogger
from telemetry.manifest import RunManifest
from safety.gate import SafetyConfig, SafetyGate
from utils.random_state import RandomState


class TestEvolutionPipeline(unittest.TestCase):
    """Test complete evolution pipeline integration."""

    def setUp(self):
        """Set up test environment."""
        self.test_dir = Path(tempfile.mkdtemp())
        
        # Set up components
        self.rng = RandomState(seed=42)
        self.archive = BehaviorArchive(k=5)
        self.fitness = CompositeFitness(
            FitnessWeights(perf=1.0, stability=0.5),
            hard_caps={'risk': 0.9}
        )
        
        # Create evaluation plan
        self.plan = EvaluationPlan([
            RegimeWindow(
                name="test_regime_1",
                train=("2020-01-01", "2020-12-31"),
                test=("2021-01-06", "2021-03-31"),  # Test starts after embargo (2020-12-31 + 5 days)
                embargo_days=5
            )
        ])
        
        # Set up telemetry
        self.logger = EventLogger(str(self.test_dir / "events.jsonl"))
        
        # Set up safety
        self.safety = SafetyGate(SafetyConfig(
            allowed_paths=[str(self.test_dir)],
            blocked_paths=["/etc", "/usr", "/bin"],  # Don't block "/" which blocks everything!
            dry_run=False
        ))

    def tearDown(self):
        """Clean up test environment."""
        self.logger.close()
        shutil.rmtree(self.test_dir, ignore_errors=True)

    def test_full_evolution_cycle(self):
        """Test a complete evolution cycle."""
        # Log run start
        self.logger.emit("run_start", {
            "seed": self.rng.seed,
            "regimes": [w.name for w in self.plan.windows]
        })

        # Generate mock population
        population = []
        for i in range(10):
            individual = {
                'id': f'ind_{i}',
                'genome': self.rng.uniform(-1, 1, size=5),
                'behavior': self.rng.uniform(0, 1, size=3)
            }
            population.append(individual)

        # Evaluate population
        for individual in population:
            # Simulate regime evaluation
            regime_metrics = []
            for regime in self.plan.iter():
                metrics = {
                    'perf': self.rng.uniform(0, 2),
                    'risk': self.rng.uniform(0, 1),
                    'maxdd': self.rng.uniform(0, 0.5)
                }
                regime_metrics.append(metrics)
                
                self.logger.emit("regime_eval", {
                    'individual': individual['id'],
                    'regime': regime.name,
                    'metrics': metrics
                })

            # Aggregate fitness
            agg_metrics = self.fitness.aggregate(regime_metrics)
            individual['fitness'] = self.fitness.score(agg_metrics)  # Calculate score from aggregated metrics
            
            # Calculate novelty
            individual['novelty'] = self.archive.novelty(individual['behavior'])
            self.archive.add(individual['behavior'])

            self.logger.emit("fitness_calc", {
                'individual': individual['id'],
                'fitness': individual['fitness'],
                'novelty': individual['novelty']
            })

        # Selection using Pareto front
        objectives = ['fitness', 'novelty']
        front_indices = pareto_front(population, objectives, maximize=True)
        
        self.logger.emit("pareto_front", {
            'size': len(front_indices),
            'individuals': [population[i]['id'] for i in front_indices]
        })

        # Verify results
        self.assertGreater(len(front_indices), 0)
        self.assertLessEqual(len(front_indices), len(population))

        # Check telemetry was logged
        self.logger.flush()
        log_path = self.test_dir / "events.jsonl"
        self.assertTrue(log_path.exists())
        
        # Validate events
        with open(log_path) as f:
            events = [json.loads(line) for line in f]
        
        self.assertGreater(len(events), 0)
        event_types = {e['event'] for e in events}
        self.assertIn('run_start', event_types)
        self.assertIn('fitness_calc', event_types)
        self.assertIn('pareto_front', event_types)

    def test_safety_enforcement(self):
        """Test safety gate enforcement."""
        # Try to write outside allowed path
        with self.assertRaises(PermissionError):
            self.safety.check_path("/etc/test.txt", "write")

        # Allowed path should work
        allowed_path = self.test_dir / "test.txt"
        result = self.safety.check_path(str(allowed_path), "write")
        self.assertTrue(result)

    def test_reproducibility(self):
        """Test reproducible results with same seed."""
        results1 = self._run_mini_evolution(seed=123)
        results2 = self._run_mini_evolution(seed=123)
        
        # Results should be identical with same seed
        self.assertEqual(results1['best_fitness'], results2['best_fitness'])
        self.assertEqual(results1['archive_size'], results2['archive_size'])

    def _run_mini_evolution(self, seed):
        """Helper to run mini evolution."""
        rng = RandomState(seed)
        archive = BehaviorArchive()
        
        # Generate and evaluate
        best_fitness = -float('inf')
        for _ in range(5):
            fitness = rng.uniform(-1, 1)
            behavior = rng.uniform(0, 1, size=3)
            archive.add(behavior)
            best_fitness = max(best_fitness, fitness)

        return {
            'best_fitness': best_fitness,
            'archive_size': len(archive.vectors)
        }


if __name__ == '__main__':
    unittest.main()
