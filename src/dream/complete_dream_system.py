#!/usr/bin/env python3
"""
D-REAM Complete System Orchestrator
Production-safe evolutionary optimization with all safety features.
"""

import yaml
import json
import logging
import sys
from pathlib import Path
from datetime import datetime
from typing import Dict, Any, List, Optional
import numpy as np

# Add parent to path for imports
sys.path.insert(0, str(Path(__file__).parent))

from fitness import create_fitness_from_config
from novelty import BehaviorArchive, extract_behavior_vector, pareto_front
from evaluation_plan import create_plan_from_config, RegimeEvaluator
from deploy.patcher import PatchManager, ChangeRequest
from safety.gate import SafetyGate, SafetyConfig, SafeContext
from telemetry.logger import EventLogger, TelemetryCollector
from telemetry.manifest import RunManifest, ManifestManager
from utils.random_state import ensure_reproducibility, RandomState
from kloros_evaluator import KLoROSEvaluator

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s [%(levelname)s] %(name)s: %(message)s'
)
logger = logging.getLogger(__name__)


class DreamOrchestrator:
    """Main orchestrator for D-REAM evolution system."""

    def __init__(self, config_path: str):
        """
        Initialize orchestrator with configuration.

        Args:
            config_path: Path to YAML configuration file
        """
        # Load configuration
        self.config = self._load_config(config_path)
        
        # Set up reproducibility
        self.seeds = ensure_reproducibility(self.config.get('seed'))
        self.rng = RandomState(self.config.get('seed'))
        
        # Initialize components
        self._init_components()
        
        # Create run manifest
        self.manifest_manager = ManifestManager(
            self.config.get('artifacts_dir', 'artifacts') + '/manifests'
        )
        self.manifest = self.manifest_manager.create_manifest(self.config)
        self.manifest.set_seeds(self.seeds)

    def _load_config(self, path: str) -> Dict[str, Any]:
        """Load and validate configuration."""
        with open(path, 'r') as f:
            config = yaml.safe_load(f)
        
        # Load regime config if specified
        if 'regime_config' in config:
            regime_path = config['regime_config']
            with open(regime_path, 'r') as f:
                regime_config = yaml.safe_load(f)
            config['regimes'] = regime_config.get('regimes', [])
            
            # Apply fitness overrides if present
            if 'fitness_overrides' in regime_config:
                config['fitness'].update(regime_config['fitness_overrides'])
        
        logger.info(f"Loaded configuration from {path}")
        return config

    def _init_components(self):
        """Initialize all system components."""
        # Safety gate
        safety_config = SafetyConfig(**self.config.get('safety', {}))
        self.safety_gate = SafetyGate(safety_config)
        
        # Telemetry
        telemetry_cfg = self.config.get('telemetry', {})
        self.event_logger = EventLogger(
            telemetry_cfg.get('events_path', 'artifacts/telemetry/events.jsonl'),
            telemetry_cfg.get('buffer_size', 100)
        )
        self.telemetry = TelemetryCollector(self.event_logger)
        
        # Fitness function
        self.fitness_func = create_fitness_from_config(self.config.get('fitness', {}))
        
        # Novelty archive
        novelty_cfg = self.config.get('novelty', {})
        self.archive = BehaviorArchive(
            k=novelty_cfg.get('k', 10),
            max_size=novelty_cfg.get('archive_max', 256)
        )
        
        # Evaluation plan
        if 'regimes' in self.config:
            self.eval_plan = create_plan_from_config(self.config)
            self.regime_evaluator = RegimeEvaluator(self.eval_plan)
            self.manifest.set_regimes([w.name for w in self.eval_plan.windows])
        else:
            self.eval_plan = None
            self.regime_evaluator = None
        
        # Patch manager
        self.patch_manager = PatchManager(
            self.config.get('artifacts_dir', 'artifacts')
        )
        
        # KLoROS evaluator for real performance testing
        self.kloros_evaluator = KLoROSEvaluator()
        
        logger.info("All components initialized")

    def run(self) -> Dict[str, Any]:
        """
        Run complete D-REAM evolution cycle.

        Returns:
            Results dictionary with metrics and artifacts
        """
        # Enter safety context
        with SafeContext(self.safety_gate):
            # Log run start
            self.event_logger.emit('run_start', {
                'run_id': self.manifest.run_id,
                'config_hash': self.manifest.compute_config_hash(),
                'seed': self.config.get('seed')
            })
            
            try:
                # Run evolution
                results = self._run_evolution()
                
                # Process results
                self._process_results(results)
                
                # Save manifest
                manifest_path = self.manifest_manager.save_manifest(self.manifest)
                logger.info(f"Saved manifest to {manifest_path}")
                
                # Log run end
                self.event_logger.emit('run_end', {
                    'run_id': self.manifest.run_id,
                    'status': 'success',
                    'results': results.get('summary', {})
                })
                
                return results
                
            except Exception as e:
                logger.error(f"Evolution failed: {e}")
                self.event_logger.emit('run_end', {
                    'run_id': self.manifest.run_id,
                    'status': 'failed',
                    'error': str(e)
                })
                raise
            
            finally:
                self.event_logger.close()

    def _run_evolution(self) -> Dict[str, Any]:
        """Run the evolution loop."""
        pop_cfg = self.config.get('population', {})
        max_gens = pop_cfg.get('max_gens', 20)
        pop_size = pop_cfg.get('size', 24)
        
        results = {
            'generations': [],
            'best_individual': None,
            'best_fitness': -float('inf')
        }
        
        # Initialize population
        population = self._init_population(pop_size)
        
        for gen in range(max_gens):
            logger.info(f"Generation {gen+1}/{max_gens}")
            self.telemetry.start_timer(f'generation_{gen}')
            
            # Log generation start
            self.event_logger.emit('generation_start', {
                'generation': gen,
                'population_size': len(population)
            })
            
            # Evaluate population
            evaluated_pop = self._evaluate_population(population)
            
            # Selection
            selected = self._select(evaluated_pop)
            
            # Track best
            gen_best = max(evaluated_pop, key=lambda x: x.get('fitness', -float('inf')))
            if gen_best.get('fitness', -float('inf')) > results['best_fitness']:
                results['best_individual'] = gen_best
                results['best_fitness'] = gen_best['fitness']
            
            # Log generation end
            gen_time = self.telemetry.stop_timer(f'generation_{gen}')
            self.event_logger.emit('generation_end', {
                'generation': gen,
                'best_fitness': gen_best.get('fitness'),
                'archive_size': len(self.archive.vectors),
                'elapsed': gen_time
            })
            
            results['generations'].append({
                'generation': gen,
                'best_fitness': gen_best.get('fitness'),
                'mean_fitness': np.mean([ind.get('fitness', 0) for ind in evaluated_pop]),
                'archive_diversity': self.archive.get_diversity()
            })
            
            # Create next generation
            if gen < max_gens - 1:
                population = self._create_next_generation(selected)
        
        # Compute summary
        results['summary'] = self._compute_summary(results)
        
        return results

    def _init_population(self, size: int) -> List[Dict[str, Any]]:
        """Initialize random population."""
        population = []
        for i in range(size):
            individual = {
                'id': f'ind_{i}_gen0',
                'genome': self.rng.normal(0, 1, size=10),  # Mock genome
                'generation': 0
            }
            population.append(individual)
        return population

    def _evaluate_population(self, population: List[Dict]) -> List[Dict]:
        """Evaluate all individuals in population."""
        evaluated = []
        
        for individual in population:
            # Evaluate across regimes if available
            if self.regime_evaluator:
                eval_result = self.regime_evaluator.evaluate(
                    self._evaluate_on_regime,
                    individual
                )
                regime_metrics = [r['metrics'] for r in eval_result['regime_results'] 
                                if 'metrics' in r]
                
                if regime_metrics:
                    # Aggregate across regimes
                    agg_metrics = self.fitness_func.aggregate(regime_metrics)
                    individual['fitness'] = agg_metrics['score']
                    individual['metrics'] = agg_metrics
                else:
                    individual['fitness'] = -float('inf')
            else:
                # Single evaluation
                metrics = self._evaluate_individual(individual)
                individual['fitness'] = self.fitness_func.score(metrics)
                individual['metrics'] = metrics
            
            # Extract behavior vector
            behavior_features = self.config.get('behavior', {}).get('features', ['fitness'])
            individual['behavior'] = extract_behavior_vector(
                individual['metrics'],
                behavior_features
            )
            
            # Calculate novelty
            individual['novelty'] = self.archive.novelty(individual['behavior'])
            self.archive.add(individual['behavior'])
            
            # Log evaluation
            self.event_logger.emit('candidate_eval', {
                'individual': individual['id'],
                'fitness': individual['fitness'],
                'novelty': individual['novelty']
            })
            
            evaluated.append(individual)
        
        return evaluated

    def _evaluate_on_regime(self, individual: Dict, regime) -> Dict[str, float]:
        """Evaluate individual on specific regime."""
        # Use real KLoROS evaluator
        return self.kloros_evaluator.evaluate_individual(individual)

    def _evaluate_individual(self, individual: Dict) -> Dict[str, float]:
        """Evaluate single individual."""
        # Use real KLoROS evaluator
        return self.kloros_evaluator.evaluate_individual(individual)

    def _select(self, population: List[Dict]) -> List[Dict]:
        """Select individuals using Pareto front and diversity."""
        novelty_cfg = self.config.get('novelty', {})
        pareto_keys = novelty_cfg.get('pareto_keys', ['fitness', 'novelty'])
        
        # Get Pareto front
        front_indices = pareto_front(population, pareto_keys, maximize=True)
        
        # Log Pareto front
        self.event_logger.emit('pareto_front', {
            'size': len(front_indices),
            'objectives': pareto_keys
        })
        
        # Select elite plus some from front
        pop_cfg = self.config.get('population', {})
        elite_k = pop_cfg.get('elite_k', 6)
        
        # Sort by fitness for elite
        sorted_pop = sorted(population, key=lambda x: x.get('fitness', -float('inf')), 
                          reverse=True)
        elite = sorted_pop[:elite_k]
        
        # Add diverse individuals from Pareto front
        front_individuals = [population[i] for i in front_indices]
        for ind in front_individuals:
            if ind not in elite and len(elite) < len(population) // 2:
                elite.append(ind)
        
        return elite

    def _create_next_generation(self, parents: List[Dict]) -> List[Dict]:
        """Create next generation through mutation and crossover."""
        pop_cfg = self.config.get('population', {})
        pop_size = pop_cfg.get('size', 24)
        
        mut_cfg = self.config.get('mutation', {})
        mut_rate = mut_cfg.get('rate', 0.1)
        mut_strength = mut_cfg.get('strength', 0.3)
        
        next_gen = []
        gen_num = parents[0].get('generation', 0) + 1
        
        # Keep elite
        for i, parent in enumerate(parents):
            child = {
                'id': f'ind_{i}_gen{gen_num}',
                'genome': parent['genome'].copy(),
                'generation': gen_num,
                'parent': parent['id']
            }
            next_gen.append(child)
        
        # Fill rest with mutated offspring
        while len(next_gen) < pop_size:
            parent = self.rng.choice(parents)
            child_genome = parent['genome'].copy()
            
            # Apply mutation
            if self.rng.random() < mut_rate:
                mutation = self.rng.normal(0, mut_strength, size=len(child_genome))
                child_genome += mutation
            
            child = {
                'id': f'ind_{len(next_gen)}_gen{gen_num}',
                'genome': child_genome,
                'generation': gen_num,
                'parent': parent['id']
            }
            next_gen.append(child)
        
        return next_gen

    def _compute_summary(self, results: Dict) -> Dict[str, Any]:
        """Compute summary statistics."""
        generations = results.get('generations', [])
        if not generations:
            return {}
        
        fitness_trajectory = [g['best_fitness'] for g in generations]
        
        return {
            'total_generations': len(generations),
            'best_fitness': results.get('best_fitness'),
            'fitness_improvement': fitness_trajectory[-1] - fitness_trajectory[0],
            'final_diversity': generations[-1].get('archive_diversity', 0),
            'convergence_rate': self._calculate_convergence(fitness_trajectory)
        }

    def _calculate_convergence(self, trajectory: List[float]) -> float:
        """Calculate convergence rate."""
        if len(trajectory) < 2:
            return 0.0
        
        # Simple linear slope
        x = np.arange(len(trajectory))
        y = np.array(trajectory)
        
        # Avoid division by zero
        if np.std(x) == 0:
            return 0.0
            
        slope = np.cov(x, y)[0, 1] / np.var(x)
        return float(slope)

    def _process_results(self, results: Dict):
        """Process and potentially deploy results."""
        best = results.get('best_individual')
        if not best:
            logger.warning("No best individual found")
            return
        
        # Check if deployment criteria are met
        deploy_cfg = self.config.get('deployment', {})
        if not self._check_deployment_criteria(best):
            logger.info("Deployment criteria not met")
            return
        
        # Request approval if needed
        if deploy_cfg.get('require_approval', True):
            if not self.safety_gate.request_approval('deployment', {
                'individual': best['id'],
                'fitness': best.get('fitness')
            }):
                logger.info("Deployment not approved")
                return
        
        # Create patch if configured
        if deploy_cfg.get('create_patch', False):
            self._create_deployment_patch(best)

    def _check_deployment_criteria(self, individual: Dict) -> bool:
        """Check if individual meets deployment criteria."""
        # Check fitness threshold
        min_fitness = self.config.get('deployment', {}).get('min_fitness', 0)
        if individual.get('fitness', -float('inf')) < min_fitness:
            return False
        
        # Check regime minimums
        if 'metrics' in individual:
            metrics = individual['metrics']
            # Check if any hard constraints violated
            for metric, cap in self.fitness_func.hard.items():
                if metrics.get(metric, 0) > cap:
                    logger.warning(f"Hard constraint violated: {metric}")
                    return False
        
        # Check safety gate
        if not self.safety_gate.allow_mutation():
            logger.info("Mutations blocked by safety gate")
            return False
        
        return True

    def _create_deployment_patch(self, individual: Dict):
        """Create deployment patch for individual."""
        try:
            # Mock change request - replace with actual
            cr = ChangeRequest(
                file_path="src/target_module.py",
                target_class=None,
                target_func="evolve_function",
                new_impl_src="def evolve_function():\n    return 'evolved'",
                metadata={'individual': individual['id']}
            )
            
            # Apply with patch manager
            artifact = self.patch_manager.apply(cr, dry_run=self.safety_gate.cfg.dry_run)
            
            # Add to manifest
            self.manifest.add_artifact('patch', artifact.patch_id)
            
            logger.info(f"Created patch: {artifact.patch_id}")
            
        except Exception as e:
            logger.error(f"Failed to create patch: {e}")


def main():
    """Main entry point."""
    import argparse
    
    parser = argparse.ArgumentParser(description='D-REAM Evolution System')
    parser.add_argument('--config', default='configs/default.yaml',
                       help='Configuration file path')
    parser.add_argument('--regime', help='Regime configuration file')
    parser.add_argument('--dry-run', action='store_true',
                       help='Run in dry-run mode (no mutations)')
    
    args = parser.parse_args()
    
    # Load config
    config_path = args.config
    if not Path(config_path).exists():
        config_path = Path(__file__).parent / config_path
    
    if args.regime:
        # Override regime config
        with open(config_path, 'r') as f:
            config = yaml.safe_load(f)
        config['regime_config'] = args.regime
        
        # Save temporary config
        temp_config = Path('/tmp/dream_config.yaml')
        with open(temp_config, 'w') as f:
            yaml.dump(config, f)
        config_path = str(temp_config)
    
    if args.dry_run:
        # Force dry-run mode
        with open(config_path, 'r') as f:
            config = yaml.safe_load(f)
        config.setdefault('safety', {})['dry_run'] = True
        
        temp_config = Path('/tmp/dream_config_dry.yaml')
        with open(temp_config, 'w') as f:
            yaml.dump(config, f)
        config_path = str(temp_config)
    
    # Run orchestrator
    logger.info(f"Starting D-REAM with config: {config_path}")
    orchestrator = DreamOrchestrator(config_path)
    results = orchestrator.run()
    
    # Print summary
    summary = results.get('summary', {})
    print("\n" + "="*50)
    print("D-REAM Evolution Complete")
    print("="*50)
    print(f"Best Fitness: {summary.get('best_fitness', 'N/A')}")
    print(f"Improvement: {summary.get('fitness_improvement', 'N/A')}")
    print(f"Convergence Rate: {summary.get('convergence_rate', 'N/A'):.4f}")
    print(f"Final Diversity: {summary.get('final_diversity', 'N/A'):.4f}")
    print("="*50)


if __name__ == '__main__':
    main()
