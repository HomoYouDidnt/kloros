#!/usr/bin/env python3
"""
D-REAM Domain Integration
Integrates all domain evaluators and schedules regular optimization runs.
"""

import os
import sys
import json
import time
import logging
import threading
import schedule
from datetime import datetime, timedelta
from pathlib import Path
from typing import Dict, List, Any, Optional
import numpy as np

# Add parent directory for imports
sys.path.insert(0, str(Path(__file__).parent))
sys.path.insert(0, '/home/kloros/src/dream')

from .domain_evaluator_base import DomainEvaluator, CompositeDomainEvaluator
from cpu_domain_evaluator import CPUDomainEvaluator
from gpu_domain_evaluator import GPUDomainEvaluator
from audio_domain_evaluator import AudioDomainEvaluator

# Import D-REAM components
from complete_dream_system import DreamOrchestrator

logger = logging.getLogger(__name__)


class DreamDomainScheduler:
    """Scheduler for running domain optimizations at regular intervals."""

    def __init__(self):
        """Initialize the domain scheduler."""
        self.evaluators = self._initialize_evaluators()
        self.composite_evaluator = CompositeDomainEvaluator(list(self.evaluators.values()))
        self.schedule_config = self._load_schedule_config()
        self.running = False
        self.scheduler_thread = None
        self.results_dir = Path("/home/kloros/src/dream/artifacts/domain_results")
        self.results_dir.mkdir(parents=True, exist_ok=True)

    def _initialize_evaluators(self) -> Dict[str, DomainEvaluator]:
        """Initialize all domain evaluators."""
        evaluators = {}

        # CPU domain
        try:
            evaluators['cpu'] = CPUDomainEvaluator()
            logger.info("Initialized CPU domain evaluator")
        except Exception as e:
            logger.error(f"Failed to initialize CPU evaluator: {e}")

        # GPU domain
        try:
            evaluators['gpu'] = GPUDomainEvaluator()
            logger.info("Initialized GPU domain evaluator")
        except Exception as e:
            logger.error(f"Failed to initialize GPU evaluator: {e}")

        # Audio domain
        try:
            evaluators['audio'] = AudioDomainEvaluator()
            logger.info("Initialized Audio domain evaluator")
        except Exception as e:
            logger.error(f"Failed to initialize Audio evaluator: {e}")

        # Additional domains would be added here:
        # - Memory (DDR5) evaluator
        # - Storage (NVMe/SATA) evaluator
        # - ASR/TTS pipeline evaluator
        # - Power/Thermal evaluator
        # - OS/Scheduler evaluator

        return evaluators

    def _load_schedule_config(self) -> Dict[str, Any]:
        """Load scheduling configuration."""
        default_config = {
            'intervals': {
                'cpu': {'minutes': 30, 'enabled': True},
                'gpu': {'minutes': 60, 'enabled': True},
                'audio': {'minutes': 45, 'enabled': True},
                'memory': {'minutes': 120, 'enabled': False},
                'storage': {'minutes': 240, 'enabled': False},
                'power': {'minutes': 15, 'enabled': True},
            },
            'regimes': {
                'idle': {'weight': 0.2},
                'normal': {'weight': 0.5},
                'stress': {'weight': 0.2},
                'mixed': {'weight': 0.1}
            },
            'evolution': {
                'generations': 10,
                'population_size': 12,
                'timeout_minutes': 5
            }
        }

        config_path = Path("/home/kloros/src/dream/configs/domain_schedule.yaml")
        if config_path.exists():
            try:
                import yaml
                with open(config_path, 'r') as f:
                    loaded_config = yaml.safe_load(f)
                    default_config.update(loaded_config)
            except Exception as e:
                logger.error(f"Failed to load schedule config: {e}")

        return default_config

    def start(self):
        """Start the scheduler."""
        if self.running:
            logger.warning("Scheduler already running")
            return

        self.running = True

        # Schedule domain optimizations
        for domain_name, config in self.schedule_config['intervals'].items():
            if config.get('enabled', False) and domain_name in self.evaluators:
                minutes = config.get('minutes', 60)
                schedule.every(minutes).minutes.do(
                    self.run_domain_optimization, domain_name
                )
                logger.info(f"Scheduled {domain_name} optimization every {minutes} minutes")

        # Schedule composite optimizations
        schedule.every(6).hours.do(self.run_composite_optimization)
        logger.info("Scheduled composite optimization every 6 hours")

        # Start scheduler thread
        self.scheduler_thread = threading.Thread(target=self._scheduler_loop, daemon=True)
        self.scheduler_thread.start()
        logger.info("Domain scheduler started")

    def stop(self):
        """Stop the scheduler."""
        self.running = False
        if self.scheduler_thread:
            self.scheduler_thread.join(timeout=5)
        logger.info("Domain scheduler stopped")

    def _scheduler_loop(self):
        """Main scheduler loop."""
        while self.running:
            try:
                schedule.run_pending()
                time.sleep(10)  # Check every 10 seconds
            except Exception as e:
                logger.error(f"Scheduler error: {e}")

    def run_domain_optimization(self, domain_name: str):
        """Run optimization for a specific domain."""
        logger.info(f"Starting {domain_name} domain optimization")

        try:
            evaluator = self.evaluators[domain_name]

            # Create custom D-REAM config for this domain
            config = self._create_dream_config(domain_name)

            # Initialize D-REAM orchestrator
            orchestrator = DreamDomainOrchestrator(config, evaluator)

            # Run evolution
            results = orchestrator.run()

            # Save results
            self._save_results(domain_name, results)

            # Apply best configuration if improved
            if results.get('improved', False):
                self._apply_best_config(domain_name, results['best_config'])

            logger.info(f"Completed {domain_name} optimization: "
                       f"fitness={results.get('best_fitness', 0):.3f}")

        except Exception as e:
            logger.error(f"Failed to run {domain_name} optimization: {e}")

    def run_composite_optimization(self):
        """Run optimization across all domains."""
        logger.info("Starting composite domain optimization")

        try:
            # Create composite config
            config = self._create_composite_config()

            # Initialize composite orchestrator
            orchestrator = DreamCompositeOrchestrator(config, self.composite_evaluator)

            # Run evolution
            results = orchestrator.run()

            # Save results
            self._save_results('composite', results)

            logger.info(f"Completed composite optimization: "
                       f"fitness={results.get('best_fitness', 0):.3f}")

        except Exception as e:
            logger.error(f"Failed to run composite optimization: {e}")

    def _create_dream_config(self, domain_name: str) -> Dict[str, Any]:
        """Create D-REAM configuration for a domain."""
        evolution_config = self.schedule_config['evolution']

        config = {
            'domain': domain_name,
            'seed': int(datetime.now().timestamp()),
            'population': {
                'size': evolution_config['population_size'],
                'max_gens': evolution_config['generations'],
                'elite_k': 3
            },
            'fitness': {
                'objectives': ['perf', 'latency', 'power'],
                'weights': [0.5, -0.3, -0.2],
                'hard': {}  # Domain-specific constraints
            },
            'timeout': evolution_config['timeout_minutes'] * 60,
            'artifacts_dir': f'artifacts/domain_{domain_name}',
            'telemetry': {
                'events_path': f'artifacts/domain_{domain_name}/events.jsonl'
            }
        }

        return config

    def _create_composite_config(self) -> Dict[str, Any]:
        """Create D-REAM configuration for composite optimization."""
        config = self._create_dream_config('composite')
        config['domains'] = list(self.evaluators.keys())
        config['population']['size'] = 24  # Larger population for composite
        config['population']['max_gens'] = 20
        return config

    def _save_results(self, domain_name: str, results: Dict[str, Any]):
        """Save optimization results."""
        timestamp = datetime.now().isoformat()
        results_file = self.results_dir / f"{domain_name}_{timestamp}.json"

        try:
            with open(results_file, 'w') as f:
                json.dump({
                    'timestamp': timestamp,
                    'domain': domain_name,
                    'results': results
                }, f, indent=2, default=str)

            logger.info(f"Saved results to {results_file}")

        except Exception as e:
            logger.error(f"Failed to save results: {e}")

    def _apply_best_config(self, domain_name: str, config: Dict[str, Any]):
        """Apply the best configuration found."""
        logger.info(f"Applying best configuration for {domain_name}")

        try:
            evaluator = self.evaluators[domain_name]
            success = evaluator.apply_configuration(config)

            if success:
                # Save as active configuration
                active_config_file = self.results_dir / f"{domain_name}_active.json"
                with open(active_config_file, 'w') as f:
                    json.dump({
                        'timestamp': datetime.now().isoformat(),
                        'domain': domain_name,
                        'config': config
                    }, f, indent=2)

                logger.info(f"Applied and saved active configuration for {domain_name}")

        except Exception as e:
            logger.error(f"Failed to apply configuration: {e}")


class DreamDomainOrchestrator(DreamOrchestrator):
    """Extended D-REAM orchestrator for domain evaluations."""

    def __init__(self, config: Dict[str, Any], evaluator: DomainEvaluator):
        """
        Initialize domain orchestrator.

        Args:
            config: D-REAM configuration
            evaluator: Domain evaluator to use
        """
        # Create temporary config file
        import tempfile
        import yaml

        self.evaluator = evaluator
        self.domain_name = config.get('domain', 'unknown')

        with tempfile.NamedTemporaryFile(mode='w', suffix='.yaml', delete=False) as f:
            yaml.dump(config, f)
            config_path = f.name

        super().__init__(config_path)

    def _evaluate_individual(self, individual: Dict) -> Dict[str, float]:
        """Evaluate individual using domain evaluator."""
        genome = individual.get('genome', [])

        # Use domain evaluator
        result = self.evaluator.evaluate(genome)

        # Map to D-REAM metrics
        metrics = {
            'perf': result.get('fitness', 0),
            'risk': 0 if result.get('safe', True) else 1,
            'maxdd': 0,  # Domain-specific
            'turnover': 0  # Domain-specific
        }

        # Add raw metrics for telemetry
        metrics['raw_metrics'] = result.get('metrics', {})
        metrics['config'] = result.get('config', {})
        metrics['violations'] = result.get('violations', [])

        return metrics


class DreamCompositeOrchestrator(DreamOrchestrator):
    """D-REAM orchestrator for composite domain evaluations."""

    def __init__(self, config: Dict[str, Any], composite_evaluator: CompositeDomainEvaluator):
        """
        Initialize composite orchestrator.

        Args:
            config: D-REAM configuration
            composite_evaluator: Composite evaluator to use
        """
        import tempfile
        import yaml

        self.composite_evaluator = composite_evaluator
        self.domains = config.get('domains', [])

        with tempfile.NamedTemporaryFile(mode='w', suffix='.yaml', delete=False) as f:
            yaml.dump(config, f)
            config_path = f.name

        super().__init__(config_path)

    def _evaluate_individual(self, individual: Dict) -> Dict[str, float]:
        """Evaluate individual across multiple domains."""
        genome = individual.get('genome', [])

        # Use composite evaluator
        result = self.composite_evaluator.evaluate(genome, self.domains)

        # Aggregate metrics
        metrics = {
            'perf': result.get('fitness', 0),
            'risk': 0 if result.get('safe', True) else 1,
            'maxdd': 0,
            'turnover': 0
        }

        # Add domain-specific results
        metrics['domain_results'] = result.get('domain_results', {})
        metrics['violations'] = result.get('violations', [])

        return metrics


# Integration with background service
class DreamDomainBackground:
    """Background service integration for domain optimization."""

    def __init__(self):
        """Initialize background integration."""
        self.scheduler = DreamDomainScheduler()
        self.status_file = Path("/home/kloros/.kloros/dream_domain_status.json")

    def start(self):
        """Start background domain optimization."""
        logger.info("Starting D-REAM domain background service")

        # Start scheduler
        self.scheduler.start()

        # Update status
        self._update_status('running')

    def stop(self):
        """Stop background service."""
        logger.info("Stopping D-REAM domain background service")

        # Stop scheduler
        self.scheduler.stop()

        # Update status
        self._update_status('stopped')

    def _update_status(self, status: str):
        """Update service status file."""
        try:
            status_data = {
                'status': status,
                'timestamp': datetime.now().isoformat(),
                'domains': list(self.scheduler.evaluators.keys()),
                'next_runs': self._get_next_runs()
            }

            with open(self.status_file, 'w') as f:
                json.dump(status_data, f, indent=2)

        except Exception as e:
            logger.error(f"Failed to update status: {e}")

    def _get_next_runs(self) -> Dict[str, str]:
        """Get next scheduled run times."""
        next_runs = {}

        for job in schedule.jobs:
            if hasattr(job, 'job_func') and hasattr(job.job_func, '__name__'):
                name = job.job_func.__name__
                next_run = job.next_run
                if next_run:
                    next_runs[name] = next_run.isoformat()

        return next_runs


def main():
    """Main entry point for domain optimization service."""
    import argparse

    parser = argparse.ArgumentParser(description='D-REAM Domain Optimization Service')
    parser.add_argument('--daemon', action='store_true',
                       help='Run as background daemon')
    parser.add_argument('--domain', help='Run optimization for specific domain')
    parser.add_argument('--composite', action='store_true',
                       help='Run composite optimization')

    args = parser.parse_args()

    # Configure logging
    logging.basicConfig(
        level=logging.INFO,
        format='%(asctime)s [%(levelname)s] %(name)s: %(message)s',
        handlers=[
            logging.FileHandler('/home/kloros/.kloros/dream_domain.log'),
            logging.StreamHandler()
        ]
    )

    if args.daemon:
        # Run as background service
        service = DreamDomainBackground()
        service.start()

        try:
            while True:
                time.sleep(60)
        except KeyboardInterrupt:
            service.stop()

    else:
        # Run single optimization
        scheduler = DreamDomainScheduler()

        if args.domain:
            scheduler.run_domain_optimization(args.domain)
        elif args.composite:
            scheduler.run_composite_optimization()
        else:
            print("Available domains:")
            for domain in scheduler.evaluators.keys():
                print(f"  - {domain}")


if __name__ == '__main__':
    main()