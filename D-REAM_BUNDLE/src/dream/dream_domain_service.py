#!/usr/bin/env python3
"""
Enhanced D-REAM Background System with Domain Evaluators
Integrates real hardware/software optimization through domain evaluators.
"""

import os
import sys
import time
import json
import signal
import threading
import logging
import numpy as np
from datetime import datetime, timedelta
from pathlib import Path
from typing import Dict, List, Any, Optional, Tuple
import traceback
import random

# Add paths
sys.path.insert(0, '/home/kloros/src/dream')
sys.path.insert(0, '/home/kloros/src')

# Import Phase 1 modules
from baseline import Baselines, Baseline, hash_code
from stats import bootstrap_ci, compute_effect_size
from candidate_pack import CandidatePack, RegimeResult, PackWriter, aggregate_regimes

# Phase 2: Multi-regime evaluator (optional)
try:
    from evaluator import evaluate_candidate as evaluate_candidate_phase2
    PHASE2_AVAILABLE = True
except ImportError:
    PHASE2_AVAILABLE = False

from manifest import generate_run_id, write_manifest

# Import domain evaluators
from domains.domain_evaluator_base import DomainEvaluator, CompositeDomainEvaluator
from domains.cpu_domain_evaluator import CPUDomainEvaluator
from domains.gpu_domain_evaluator import GPUDomainEvaluator
from domains.audio_domain_evaluator import AudioDomainEvaluator
from domains.memory_domain_evaluator import MemoryDomainEvaluator
from domains.storage_domain_evaluator import StorageDomainEvaluator
from domains.asr_tts_domain_evaluator import ASRTTSDomainEvaluator
from domains.power_thermal_domain_evaluator import PowerThermalDomainEvaluator
from domains.os_scheduler_domain_evaluator import OSSchedulerDomainEvaluator
from domains.conversation_domain_evaluator import ConversationDomainEvaluator
from domains.rag_context_domain_evaluator import RAGContextDomainEvaluator

# Set up logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler('/home/kloros/.kloros/dream_domain_service.log'),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger('dream_domains')

class DomainOptimizationScheduler:
    """Schedule and run domain evaluations at configurable intervals."""

    def __init__(self):
        self.evaluators = self._load_evaluators()
        self.schedules = self._load_schedules()
        self.last_runs = {}
        self.current_genomes = {}
        self.best_genomes = {}
        self.best_fitness = {}
        self.evolution_history = []

        # Evolutionary parameters
        self.population_size = 20
        self.mutation_rate = 0.1
        self.crossover_rate = 0.7
        self.elite_size = 2

        # Phase 1: Initialize baseline tracking and candidate pack export
        self.run_id = generate_run_id()
        self.baselines = Baselines()
        self.pack_writer = PackWriter()

        # Write run manifest on startup
        code_paths = [
            '/home/kloros/src/dream/dream_domain_service.py',
            '/home/kloros/src/dream/domains/domain_evaluator_base.py'
        ]
        config_paths = [
            '/home/kloros/.kloros/dream_domain_schedules.json'
        ]
        seed_map = {"python": int(os.getenv("PYTHONHASHSEED", "0")), "numpy": 1337}

        try:
            manifest_path = write_manifest(
                self.run_id,
                list(self.evaluators.keys()) if hasattr(self, 'evaluators') else [],
                config_paths,
                code_paths,
                seed_map
            )
            logger.info(f"📋 Run manifest written: {manifest_path}")
        except Exception as e:
            logger.warning(f"Failed to write manifest: {e}")

        # Phase 2 configuration
        self.enable_phase2 = os.getenv('KLR_DREAM_PHASE2', '0') == '1' and PHASE2_AVAILABLE
        self.phase2_trials = int(os.getenv('KLR_DREAM_TRIALS', '10'))
        
        if self.enable_phase2:
            logger.info("✨ Phase 2 multi-regime evaluation ENABLED")
            logger.info(f"   Trials per regime: {self.phase2_trials}")
        else:
            logger.info("📊 Phase 1 single-regime evaluation active")

    def _load_evaluators(self) -> Dict[str, DomainEvaluator]:
        """Load all domain evaluators."""
        evaluators = {}

        try:
            evaluators['cpu'] = CPUDomainEvaluator()
            logger.info("✓ CPU evaluator loaded")
        except Exception as e:
            logger.warning(f"Failed to load CPU evaluator: {e}")

        try:
            evaluators['gpu'] = GPUDomainEvaluator()
            logger.info("✓ GPU evaluator loaded")
        except Exception as e:
            logger.warning(f"Failed to load GPU evaluator: {e}")

        try:
            evaluators['audio'] = AudioDomainEvaluator()
            logger.info("✓ Audio evaluator loaded")
        except Exception as e:
            logger.warning(f"Failed to load Audio evaluator: {e}")

        try:
            evaluators['memory'] = MemoryDomainEvaluator()
            logger.info("✓ Memory evaluator loaded")
        except Exception as e:
            logger.warning(f"Failed to load Memory evaluator: {e}")

        try:
            evaluators['storage'] = StorageDomainEvaluator()
            logger.info("✓ Storage evaluator loaded")
        except Exception as e:
            logger.warning(f"Failed to load Storage evaluator: {e}")

        try:
            evaluators['asr_tts'] = ASRTTSDomainEvaluator()
            logger.info("✓ ASR/TTS evaluator loaded")
        except Exception as e:
            logger.warning(f"Failed to load ASR/TTS evaluator: {e}")

        try:
            evaluators['power_thermal'] = PowerThermalDomainEvaluator()
            logger.info("✓ Power/Thermal evaluator loaded")
        except Exception as e:
            logger.warning(f"Failed to load Power/Thermal evaluator: {e}")

        try:
            evaluators['os_scheduler'] = OSSchedulerDomainEvaluator()
            logger.info("✓ OS/Scheduler evaluator loaded")
        except Exception as e:
            logger.warning(f"Failed to load OS/Scheduler evaluator: {e}")

        try:
            evaluators['conversation'] = ConversationDomainEvaluator()
            logger.info("✓ Conversation evaluator loaded")
        except Exception as e:
            logger.warning(f"Failed to load Conversation evaluator: {e}")

        try:
            evaluators['rag_context'] = RAGContextDomainEvaluator()
            logger.info("✓ RAG Context evaluator loaded")
        except Exception as e:
            logger.warning(f"Failed to load RAG Context evaluator: {e}")

        logger.info(f"Loaded {len(evaluators)} domain evaluators")
        return evaluators

    def _load_schedules(self) -> Dict[str, Dict[str, Any]]:
        """Load evaluation schedules for each domain."""
        # Default schedules (in minutes)
        schedules = {
            'cpu': {
                'interval': 30,
                'priority': 'medium',
                'enabled': True,
                'apply_best': False  # Don't auto-apply, just evaluate
            },
            'gpu': {
                'interval': 45,
                'priority': 'medium',
                'enabled': True,
                'apply_best': False
            },
            'audio': {
                'interval': 60,
                'priority': 'high',
                'enabled': True,
                'apply_best': False
            },
            'memory': {
                'interval': 120,
                'priority': 'low',
                'enabled': True,
                'apply_best': False
            },
            'storage': {
                'interval': 240,
                'priority': 'low',
                'enabled': True,
                'apply_best': False
            },
            'asr_tts': {
                'interval': 90,
                'priority': 'high',
                'enabled': True,
                'apply_best': False
            },
            'power_thermal': {
                'interval': 15,
                'priority': 'critical',
                'enabled': True,
                'apply_best': False
            },
            'os_scheduler': {
                'interval': 180,
                'priority': 'medium',
                'enabled': True,
                'apply_best': False
            }
        }

        # Try to load custom schedules
        schedule_file = Path('/home/kloros/.kloros/dream_domain_schedules.json')
        if schedule_file.exists():
            try:
                with open(schedule_file, 'r') as f:
                    custom_schedules = json.load(f)
                    schedules.update(custom_schedules)
                    logger.info(f"Loaded custom schedules from {schedule_file}")
            except Exception as e:
                logger.warning(f"Failed to load custom schedules: {e}")

        return schedules

    def should_run_domain(self, domain: str) -> bool:
        """Check if a domain evaluation should run."""
        if domain not in self.evaluators:
            return False

        schedule = self.schedules.get(domain, {})
        if not schedule.get('enabled', False):
            return False

        now = datetime.now()
        last_run = self.last_runs.get(domain)

        if not last_run:
            return True

        interval_minutes = schedule.get('interval', 60)
        if now - last_run >= timedelta(minutes=interval_minutes):
            return True

        return False

    def evolve_population(self, domain: str, population: List[np.ndarray],
                         fitness_scores: List[float]) -> List[np.ndarray]:
        """Evolve a population using genetic operators."""
        genome_size = len(population[0])
        new_population = []

        # Convert -inf to a large negative number for sorting
        sortable_scores = []
        for score in fitness_scores:
            if score == -float('inf'):
                sortable_scores.append(-1e10)
            else:
                sortable_scores.append(score)

        # Create pairs for sorting
        pairs = list(zip(sortable_scores, population))

        # Sort by fitness
        sorted_pairs = sorted(pairs, key=lambda x: x[0], reverse=True)
        sorted_fitness = [f for f, _ in sorted_pairs]
        sorted_pop = [g for _, g in sorted_pairs]

        # Elite selection
        for i in range(self.elite_size):
            if i < len(sorted_pop):
                new_population.append(sorted_pop[i].copy())

        # Generate offspring
        while len(new_population) < self.population_size:
            # Tournament selection
            parent1 = self._tournament_select(sorted_pop, sorted_fitness)
            parent2 = self._tournament_select(sorted_pop, sorted_fitness)

            # Crossover
            if random.random() < self.crossover_rate:
                offspring = self._crossover(parent1, parent2)
            else:
                offspring = parent1.copy()

            # Mutation
            if random.random() < self.mutation_rate:
                offspring = self._mutate(offspring)

            new_population.append(offspring)

        return new_population[:self.population_size]

    def _tournament_select(self, population: List[np.ndarray],
                          fitness_scores: List[float], tournament_size: int = 3) -> np.ndarray:
        """Tournament selection."""
        indices = random.sample(range(len(population)), min(tournament_size, len(population)))
        best_idx = max(indices, key=lambda i: fitness_scores[i])
        return population[best_idx].copy()

    def _crossover(self, parent1: np.ndarray, parent2: np.ndarray) -> np.ndarray:
        """Uniform crossover."""
        offspring = np.empty_like(parent1)
        for i in range(len(parent1)):
            if random.random() < 0.5:
                offspring[i] = parent1[i]
            else:
                offspring[i] = parent2[i]
        return offspring

    def _mutate(self, genome: np.ndarray) -> np.ndarray:
        """Gaussian mutation."""
        mutated = genome.copy()
        for i in range(len(mutated)):
            if random.random() < 0.2:  # 20% chance per gene
                mutated[i] += np.random.normal(0, 0.1)
                mutated[i] = np.clip(mutated[i], -1, 1)
        return mutated

    def run_domain_evaluation(self, domain: str) -> Optional[Dict[str, Any]]:
        """Run evolutionary optimization for a domain."""
        if domain not in self.evaluators:
            logger.warning(f"Domain {domain} not available")
            return None

        evaluator = self.evaluators[domain]
        genome_spec = evaluator.get_genome_spec()
        genome_size = len(genome_spec)

        logger.info(f"🧬 Starting evolutionary optimization for {domain} domain")
        logger.info(f"   Genome size: {genome_size} parameters")
        logger.info(f"   Population size: {self.population_size}")

        try:
            # Initialize or get current population
            if domain not in self.current_genomes:
                # Initialize random population
                population = [np.random.uniform(-1, 1, genome_size)
                             for _ in range(self.population_size)]
                generation = 0
            else:
                # Use existing population
                population = self.current_genomes[domain]
                generation = len([h for h in self.evolution_history
                                 if h.get('domain') == domain])

            # Evaluate population
            fitness_scores = []
            valid_fitness = []  # Track non-inf fitness values

            for i, genome in enumerate(population):
                try:
                    result = evaluator.evaluate(genome)
                    fitness = result.get('fitness', -float('inf'))
                    fitness_scores.append(fitness)

                    if fitness > -float('inf'):
                        logger.debug(f"   Individual {i}: fitness = {fitness:.4f}")
                        valid_fitness.append(fitness)
                    else:
                        logger.debug(f"   Individual {i}: fitness = -inf (unsafe)")

                except Exception as e:
                    logger.warning(f"   Individual {i} evaluation failed: {e}")
                    fitness_scores.append(-float('inf'))

            # Track best
            candidate_pack_path = None
            if valid_fitness:  # Only if we have valid fitness scores
                best_idx = np.argmax(fitness_scores)
                best_fitness = fitness_scores[best_idx]
                best_genome = population[best_idx]

                # Update best if improved
                if domain not in self.best_fitness or best_fitness > self.best_fitness[domain]:
                    self.best_fitness[domain] = best_fitness
                    self.best_genomes[domain] = best_genome.copy()
                    logger.info(f"   🎯 New best fitness for {domain}: {best_fitness:.4f}")

                    # Phase 1/2: Export candidate pack
                    try:
                        if hasattr(self, 'enable_phase2') and self.enable_phase2:
                            # Phase 2: Multi-regime evaluation
                            logger.info(f"   🔬 Phase 2: Multi-regime with {self.phase2_trials} trials/regime")
                            pack_dict = evaluate_candidate_phase2(
                                evaluator=evaluator,
                                genome=best_genome,
                                domain=domain,
                                generation=generation,
                                cand_id=f"gen{generation}_best",
                                run_id=self.run_id,
                                code_hash=hash_code([__file__]),
                                runs=self.phase2_trials
                            )
                            # Extract path from pack dict
                            candidate_pack_path = f"artifacts/candidates/{domain}/gen{generation}_best.json"
                            regimes_evaluated = len(pack_dict.get('regimes', []))
                            score_v2 = pack_dict.get('aggregate', {}).get('score_v2', 0.0)
                            logger.info(f"   📦 Phase 2 pack: {regimes_evaluated} regimes, score_v2={score_v2:.4f}")
                        else:
                            # Phase 1: Single evaluation
                            best_result = evaluator.evaluate(best_genome)
                            decoded_genome = evaluator.genome_to_config(best_genome)

                            regime_result = RegimeResult(
                                regime="normal",
                                trials=1,
                                kpis={metric: [value] for metric, value in best_result.get('metrics', {}).items()},
                                delta=None,
                                ci95={},
                                baseline=None
                            )

                            cand_pack = CandidatePack(
                                schema_version=4,
                                run_id=self.run_id,
                                domain=domain,
                                cand_id=f"gen{generation}_best",
                                generation=generation,
                                genome=decoded_genome,
                                risk_profile=best_result.get('metrics', {}),
                                regimes=[regime_result],
                                aggregate={"score_v1": best_fitness},
                                fitness=best_fitness,
                                safe=best_result.get('safe', True),
                                created_at_utc=datetime.utcnow().strftime('%Y-%m-%dT%H:%M:%SZ')
                            )

                            pack_path = self.pack_writer.write(cand_pack)
                            candidate_pack_path = str(pack_path)
                            logger.info(f"   📦 Phase 1 pack: {pack_path}")

                            # Write candidate to dashboard intake
                            try:
                                os.makedirs("/var/log/dream", exist_ok=True)
                                candidate_for_dashboard = {
                                    "title": f"{domain.upper()} optimization (gen{generation})",
                                    "description": f"Evolutionary improvement: fitness={best_fitness:.4f}",
                                    "domain": domain,
                                    "score": float(best_fitness) if best_fitness != -float('inf') else 0.0,
                                    "meta": {
                                        "generation": generation,
                                        "run_id": self.run_id,
                                        "genome": decoded_genome,
                                        "candidate_pack": candidate_pack_path
                                    }
                                }
                                with open("/var/log/dream/candidates.jsonl", "a") as f:
                                    f.write(json.dumps(candidate_for_dashboard) + "\n")
                                logger.info(f"   📋 Candidate written to dashboard intake")
                            except Exception as e:
                                logger.warning(f"Failed to write candidate to dashboard: {e}")
                    except Exception as e:
                        logger.warning(f"   Failed to export candidate pack: {e}")
                        logger.debug(traceback.format_exc())
                # All configurations were unsafe
                best_fitness = -float('inf')
                logger.warning(f"   ⚠️  All configurations unsafe for {domain}")

            # Evolve population
            new_population = self.evolve_population(domain, population, fitness_scores)
            self.current_genomes[domain] = new_population

            # Calculate statistics
            if valid_fitness:
                avg_fitness = np.mean(valid_fitness)
                min_fitness = np.min(valid_fitness)
            else:
                avg_fitness = -float('inf')
                min_fitness = -float('inf')

            # Log results
            result = {
                'domain': domain,
                'timestamp': datetime.now().isoformat(),
                'generation': generation,
                'best_fitness': float(best_fitness) if best_fitness != -float('inf') else None,
                'avg_fitness': float(avg_fitness) if avg_fitness != -float('inf') else None,
                'min_fitness': float(min_fitness) if min_fitness != -float('inf') else None,
                'valid_individuals': len(valid_fitness),
                'population_size': len(population),
                'genome_size': genome_size,
                'candidate_pack': candidate_pack_path,  # Phase 1: Link to candidate pack
                'run_id': self.run_id  # Phase 1: Include run_id for traceability
            }

            self.evolution_history.append(result)
            self.last_runs[domain] = datetime.now()

            logger.info(f"   ✅ Generation {generation} complete")
            if valid_fitness:
                logger.info(f"      Best: {best_fitness:.4f}, Avg: {avg_fitness:.4f}, Valid: {len(valid_fitness)}/{self.population_size}")
            else:
                logger.info(f"      No valid configurations found")

            # Save telemetry
            self._save_telemetry(result)

            return result

        except Exception as e:
            logger.error(f"Domain evaluation failed for {domain}: {e}")
            logger.error(traceback.format_exc())
            return None

    def _save_telemetry(self, result: Dict[str, Any]):
        """Save evaluation telemetry."""
        telemetry_dir = Path('/home/kloros/src/dream/artifacts/domain_evolution')
        telemetry_dir.mkdir(parents=True, exist_ok=True)

        telemetry_file = telemetry_dir / f"{result['domain']}_evolution.jsonl"

        try:
            with open(telemetry_file, 'a') as f:
                f.write(json.dumps(result) + '\n')
        except Exception as e:
            logger.warning(f"Failed to save telemetry: {e}")

    def get_best_configuration(self, domain: str) -> Optional[Dict[str, Any]]:
        """Get the best configuration found for a domain."""
        if domain not in self.best_genomes:
            return None

        evaluator = self.evaluators[domain]
        best_genome = self.best_genomes[domain]

        # Convert genome to configuration
        config = evaluator.genome_to_config(best_genome)

        return {
            'domain': domain,
            'configuration': config,
            'fitness': self.best_fitness.get(domain, 0),
            'genome': best_genome.tolist()
        }

    def apply_best_configuration(self, domain: str) -> bool:
        """Apply the best configuration found for a domain."""
        if domain not in self.best_genomes:
            logger.warning(f"No best configuration found for {domain}")
            return False

        evaluator = self.evaluators[domain]
        best_genome = self.best_genomes[domain]

        try:
            # Get the evaluation result with config and metrics
            result = evaluator.evaluate(best_genome)

            # Check if it's safe
            if not result.get('safe', False):
                logger.warning(f"Best configuration for {domain} is not safe")
                return False

            # Log what would be applied (but don't actually apply in evaluation mode)
            config = result.get('config', {})
            fitness = result.get('fitness', -float('inf'))

            logger.info(f"🚀 Best configuration for {domain} (not applied in eval mode)")
            logger.info(f"   Configuration: {config}")
            logger.info(f"   Fitness: {fitness:.4f}")

            # In production, you would actually apply the configuration here
            # For now, we're just evaluating and logging

            return True

        except Exception as e:
            logger.error(f"Failed to apply configuration for {domain}: {e}")
            return False

class DreamDomainService:
    """Main service for running domain evaluations."""

    def __init__(self):
        self.running = False
        self.scheduler = DomainOptimizationScheduler()
        self.main_loop_interval = 30  # Check every 30 seconds
        self.stats = {
            'start_time': None,
            'evaluations_run': 0,
            'configurations_applied': 0,
            'errors': 0
        }

        self._setup_signal_handlers()

    def _setup_signal_handlers(self):
        """Setup signal handlers for graceful shutdown."""
        signal.signal(signal.SIGTERM, self._signal_handler)
        signal.signal(signal.SIGINT, self._signal_handler)

    def _signal_handler(self, signum, frame):
        """Handle shutdown signals."""
        logger.info(f"Received signal {signum}, shutting down gracefully...")
        self.stop()

    def start(self):
        """Start the domain evaluation service."""
        if self.running:
            logger.warning("Service already running")
            return

        self.running = True
        self.stats['start_time'] = datetime.now()

        logger.info("🚀 Starting D-REAM Domain Evaluation Service")
        logger.info(f"   Check interval: {self.main_loop_interval}s")
        logger.info(f"   Available domains: {', '.join(self.scheduler.evaluators.keys())}")

        # Start main loop thread
        main_thread = threading.Thread(target=self._main_loop, daemon=True)
        main_thread.start()

        logger.info("✅ D-REAM Domain Service started")

        return main_thread

    def stop(self):
        """Stop the domain evaluation service."""
        if not self.running:
            return

        self.running = False
        logger.info("🛑 Stopping D-REAM Domain Service")

        # Log statistics
        self._log_statistics()

        # Save best configurations
        self._save_best_configurations()

        logger.info("✅ D-REAM Domain Service stopped")

    def _main_loop(self):
        """Main service loop."""
        logger.info("📊 Starting domain evaluation loop")

        while self.running:
            try:
                # Check each domain
                for domain in self.scheduler.evaluators.keys():
                    if not self.running:
                        break

                    if self.scheduler.should_run_domain(domain):
                        logger.info(f"⏱️ Time to evaluate {domain} domain")

                        result = self.scheduler.run_domain_evaluation(domain)

                        if result:
                            self.stats['evaluations_run'] += 1

                            # Check if we should apply best configuration
                            schedule = self.scheduler.schedules.get(domain, {})
                            if schedule.get('apply_best', False):
                                if self.scheduler.apply_best_configuration(domain):
                                    self.stats['configurations_applied'] += 1
                        else:
                            self.stats['errors'] += 1

                        # Small delay between domains
                        time.sleep(5)

                # Write evaluator status file for dashboard
                self._write_evaluator_status()

                # Wait for next check
                time.sleep(self.main_loop_interval)

            except Exception as e:
                logger.error(f"Error in main loop: {e}")
                logger.error(traceback.format_exc())
                self.stats['errors'] += 1
                time.sleep(10)

    def _log_statistics(self):
        """Log service statistics."""
        if not self.stats['start_time']:
            return

        uptime = datetime.now() - self.stats['start_time']

        logger.info("📈 D-REAM Domain Service Statistics:")
        logger.info(f"   Uptime: {uptime}")
        logger.info(f"   Evaluations run: {self.stats['evaluations_run']}")
        logger.info(f"   Configurations applied: {self.stats['configurations_applied']}")
        logger.info(f"   Errors: {self.stats['errors']}")

        # Domain-specific stats
        for domain in self.scheduler.evaluators.keys():
            if domain in self.scheduler.best_fitness:
                logger.info(f"   {domain}: best fitness = {self.scheduler.best_fitness[domain]:.4f}")

    def _save_best_configurations(self):
        """Save best configurations to file."""
        config_file = Path('/home/kloros/.kloros/dream_best_configs.json')

        try:
            best_configs = {}
            for domain in self.scheduler.evaluators.keys():
                config = self.scheduler.get_best_configuration(domain)
                if config:
                    best_configs[domain] = config

            with open(config_file, 'w') as f:
                json.dump(best_configs, f, indent=2)

            logger.info(f"Saved best configurations to {config_file}")

        except Exception as e:
            logger.error(f"Failed to save configurations: {e}")

    def _write_evaluator_status(self):
        """Write evaluator status file for dashboard visibility."""
        status_file = Path('/home/kloros/out/dreameval_status.json')

        try:
            # Count candidates emitted
            candidates_file = Path('/var/log/dream/candidates.jsonl')
            candidates_emitted = 0
            if candidates_file.exists():
                with open(candidates_file, 'r') as f:
                    candidates_emitted = sum(1 for line in f if line.strip())

            # Collect domain failures
            domain_failures = {}
            for domain in self.scheduler.evaluators.keys():
                # Check if domain has any failures in recent evaluations
                if self.scheduler.best_fitness.get(domain) == -float('inf'):
                    domain_failures[domain] = 1
                else:
                    domain_failures[domain] = 0

            status = {
                "ts_utc": datetime.utcnow().strftime('%Y-%m-%dT%H:%M:%SZ'),
                "domains_scanned": len(self.scheduler.evaluators),
                "candidates_emitted": candidates_emitted,
                "failures": domain_failures,
                "uptime_seconds": (datetime.now() - self.stats['start_time']).total_seconds() if self.stats['start_time'] else 0,
                "evaluations_run": self.stats['evaluations_run'],
                "errors": self.stats['errors']
            }

            status_file.parent.mkdir(parents=True, exist_ok=True)
            with open(status_file, 'w') as f:
                json.dump(status, f, indent=2)

        except Exception as e:
            logger.warning(f"Failed to write evaluator status: {e}")

    def get_status(self) -> Dict[str, Any]:
        """Get service status."""
        uptime = datetime.now() - self.stats['start_time'] if self.stats['start_time'] else timedelta(0)

        domain_status = {}
        for domain in self.scheduler.evaluators.keys():
            last_run = self.scheduler.last_runs.get(domain)
            domain_status[domain] = {
                'enabled': self.scheduler.schedules.get(domain, {}).get('enabled', False),
                'last_run': last_run.isoformat() if last_run else None,
                'best_fitness': self.scheduler.best_fitness.get(domain),
                'generations': len([h for h in self.scheduler.evolution_history
                                  if h.get('domain') == domain])
            }

        return {
            'running': self.running,
            'uptime_seconds': uptime.total_seconds(),
            'statistics': self.stats.copy(),
            'domains': domain_status
        }

def main():
    """Main entry point."""
    logger.info("🧬 D-REAM Domain Evaluation Service Starting Up")

    # Create and start service
    service = DreamDomainService()

    try:
        main_thread = service.start()

        # Keep main thread alive
        while service.running:
            time.sleep(1)

        # Wait for main thread to finish
        if main_thread.is_alive():
            main_thread.join(timeout=5)

    except KeyboardInterrupt:
        logger.info("Received keyboard interrupt")
    except Exception as e:
        logger.error(f"Unexpected error: {e}")
        logger.error(traceback.format_exc())
    finally:
        service.stop()

if __name__ == "__main__":
    main()
