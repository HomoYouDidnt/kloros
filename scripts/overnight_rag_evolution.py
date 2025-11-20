#!/usr/bin/env python3
"""
Overnight D-REAM RAG Evolution Loop

Runs continuous evolution cycles to optimize RAG parameters.
Designed to run overnight or for extended periods.
"""
import sys
import json
import random
import time
from pathlib import Path
from dataclasses import dataclass, asdict
from typing import List, Dict, Any
from datetime import datetime

sys.path.insert(0, '/home/kloros')

from src.phase.domains.rag_context_domain import RAGDomain, RAGTestConfig, RAGTestResult

@dataclass
class RAGGenome:
    """RAG configuration genome for evolution."""
    genome_id: str
    generation: int
    epoch: int

    # Evolvable parameters
    top_k: int = 5
    chunk_size: int = 512
    chunk_overlap: int = 50
    similarity_threshold: float = 0.7

    # New evolvable params for deeper optimization
    num_predict: int = 150  # LLM token limit
    temperature: float = 0.7
    context_window: int = 3  # How many chunks to use for context

    # Fitness metrics
    fitness: float = 0.0
    precision: float = 0.0
    latency_ms: float = 0.0
    relevance: float = 0.0
    grounded_rate: float = 0.0

def mutate_genome(parent: RAGGenome, generation: int, epoch: int, genome_id: str) -> RAGGenome:
    """Create mutated offspring with adaptive mutation rates."""
    child = RAGGenome(
        genome_id=genome_id,
        generation=generation,
        epoch=epoch,
        top_k=parent.top_k,
        chunk_size=parent.chunk_size,
        chunk_overlap=parent.chunk_overlap,
        similarity_threshold=parent.similarity_threshold,
        num_predict=parent.num_predict,
        temperature=parent.temperature,
        context_window=parent.context_window
    )

    # Adaptive mutation rate (more aggressive early, refined later)
    mutation_rate = 0.4 if generation < 5 else 0.25
    mutation_strength = 1.0 if generation < 10 else 0.5

    # Mutate retrieval parameters
    if random.random() < mutation_rate:
        delta = int(random.randint(-2, 2) * mutation_strength)
        child.top_k = max(3, min(15, parent.top_k + delta))

    if random.random() < mutation_rate:
        delta = int(random.randint(-128, 128) * mutation_strength)
        child.chunk_size = max(256, min(2048, parent.chunk_size + delta))

    if random.random() < mutation_rate:
        delta = int(random.randint(-25, 25) * mutation_strength)
        child.chunk_overlap = max(0, min(200, parent.chunk_overlap + delta))

    if random.random() < mutation_rate:
        delta = random.uniform(-0.1, 0.1) * mutation_strength
        child.similarity_threshold = max(0.5, min(0.9, parent.similarity_threshold + delta))

    # Mutate generation parameters
    if random.random() < mutation_rate:
        delta = int(random.randint(-50, 50) * mutation_strength)
        child.num_predict = max(50, min(300, parent.num_predict + delta))

    if random.random() < mutation_rate:
        delta = random.uniform(-0.2, 0.2) * mutation_strength
        child.temperature = max(0.3, min(1.0, parent.temperature + delta))

    if random.random() < mutation_rate:
        delta = random.randint(-1, 1)
        child.context_window = max(1, min(10, parent.context_window + delta))

    return child

def crossover_genomes(parent_a: RAGGenome, parent_b: RAGGenome, generation: int, epoch: int, genome_id: str) -> RAGGenome:
    """Create offspring by uniform crossover."""
    return RAGGenome(
        genome_id=genome_id,
        generation=generation,
        epoch=epoch,
        top_k=random.choice([parent_a.top_k, parent_b.top_k]),
        chunk_size=random.choice([parent_a.chunk_size, parent_b.chunk_size]),
        chunk_overlap=random.choice([parent_a.chunk_overlap, parent_b.chunk_overlap]),
        similarity_threshold=random.choice([parent_a.similarity_threshold, parent_b.similarity_threshold]),
        num_predict=random.choice([parent_a.num_predict, parent_b.num_predict]),
        temperature=random.choice([parent_a.temperature, parent_b.temperature]),
        context_window=random.choice([parent_a.context_window, parent_b.context_window])
    )

def evaluate_fitness(genome: RAGGenome, test_results: List[RAGTestResult]) -> float:
    """Compute fitness with weighted objectives."""
    if not test_results:
        return 0.0

    avg_precision = sum(r.retrieval_precision for r in test_results) / len(test_results)
    avg_latency = sum(r.total_latency_ms for r in test_results) / len(test_results)
    avg_relevance = sum(r.context_relevance for r in test_results) / len(test_results)
    grounded_rate = sum(1 for r in test_results if r.answer_grounded) / len(test_results)

    # Normalize latency (target: <2000ms, acceptable: <3000ms)
    latency_score = max(0, 1.0 - (avg_latency / 3000.0))

    # Weighted fitness with emphasis on precision and speed
    fitness = (
        0.40 * avg_precision +      # Precision is king
        0.30 * latency_score +       # Speed matters
        0.15 * avg_relevance +       # Context quality
        0.10 * grounded_rate +       # No hallucinations
        0.05 * 1.0                   # Bonus for passing tests
    )

    genome.fitness = fitness
    genome.precision = avg_precision
    genome.latency_ms = avg_latency
    genome.relevance = avg_relevance
    genome.grounded_rate = grounded_rate

    return fitness

def run_rag_tests(genome: RAGGenome, epoch_id: str) -> List[RAGTestResult]:
    """Run PHASE RAG tests with genome parameters."""
    config = RAGTestConfig(top_k=genome.top_k)
    domain = RAGDomain(config)

    # Inject genome parameters into domain tests
    # (Would need to modify rag_context_domain.py to accept these)

    results = domain.run_all_tests(epoch_id=epoch_id)
    return results

def run_overnight_evolution(
    population_size: int = 10,
    generations_per_epoch: int = 20,
    max_epochs: int = 10,
    elite_count: int = 3,
    output_dir: str = "/home/kloros/dream_artifacts/rag_evolution"
):
    """Run continuous evolution epochs overnight."""

    output_path = Path(output_dir)
    output_path.mkdir(parents=True, exist_ok=True)

    # Evolution log
    log_file = output_path / f"evolution_log_{datetime.now().strftime('%Y%m%d_%H%M%S')}.jsonl"
    best_genomes_file = output_path / "best_genomes.jsonl"

    print("=" * 80)
    print("D-REAM Overnight RAG Evolution")
    print("=" * 80)
    print(f"\nConfiguration:")
    print(f"  Population size: {population_size}")
    print(f"  Generations per epoch: {generations_per_epoch}")
    print(f"  Max epochs: {max_epochs}")
    print(f"  Elite count: {elite_count}")
    print(f"  Output dir: {output_path}")
    print(f"\nEstimated runtime:")
    print(f"  ~{population_size * generations_per_epoch * max_epochs * 3 * 2 / 3600:.1f} hours")
    print(f"  (assuming ~2s per test, 3 tests per genome)")
    print()

    # Initialize baseline population
    baseline = RAGGenome(
        genome_id="baseline",
        generation=0,
        epoch=0,
        top_k=5,
        chunk_size=512,
        chunk_overlap=50,
        similarity_threshold=0.7,
        num_predict=150,
        temperature=0.7,
        context_window=3
    )

    # Global best tracker
    global_best: RAGGenome = None

    # Epoch loop
    for epoch in range(max_epochs):
        epoch_start = time.time()
        print(f"\n{'=' * 80}")
        print(f"EPOCH {epoch + 1}/{max_epochs}")
        print(f"{'=' * 80}")

        # Create initial population for this epoch
        if epoch == 0:
            population = [baseline]
            for i in range(population_size - 1):
                variant = mutate_genome(baseline, generation=0, epoch=epoch, genome_id=f"e{epoch}_g0_v{i}")
                population.append(variant)
        else:
            # Seed from global best + mutations
            population = [global_best]
            for i in range(population_size - 1):
                variant = mutate_genome(global_best, generation=0, epoch=epoch, genome_id=f"e{epoch}_g0_v{i}")
                population.append(variant)

        # Evaluate initial population
        print(f"\n[Epoch {epoch}] Evaluating initial population...")
        for genome in population:
            epoch_id = f"rag_evo_e{epoch}_g0_{genome.genome_id}"
            try:
                test_results = run_rag_tests(genome, epoch_id)
                evaluate_fitness(genome, test_results)
            except Exception as e:
                print(f"  ✗ {genome.genome_id} failed: {e}")
                genome.fitness = 0.0

        population.sort(key=lambda g: g.fitness, reverse=True)

        # Evolution within epoch
        for gen in range(1, generations_per_epoch + 1):
            print(f"\n[Epoch {epoch}, Gen {gen}/{generations_per_epoch}] Evolving...")

            # Elitism
            new_population = population[:elite_count]

            # Generate offspring
            offspring_count = population_size - elite_count
            for i in range(offspring_count):
                # Tournament selection
                parent_a = max(random.sample(population, min(3, len(population))), key=lambda g: g.fitness)
                parent_b = max(random.sample(population, min(3, len(population))), key=lambda g: g.fitness)

                # 60% crossover, 40% mutation
                if random.random() < 0.6:
                    offspring = crossover_genomes(parent_a, parent_b, gen, epoch, f"e{epoch}_g{gen}_cross{i}")
                else:
                    offspring = mutate_genome(parent_a, gen, epoch, f"e{epoch}_g{gen}_mut{i}")

                new_population.append(offspring)

            # Evaluate offspring
            for genome in new_population[elite_count:]:
                epoch_id = f"rag_evo_e{epoch}_g{gen}_{genome.genome_id}"
                try:
                    test_results = run_rag_tests(genome, epoch_id)
                    evaluate_fitness(genome, test_results)
                except Exception as e:
                    print(f"  ✗ {genome.genome_id} failed: {e}")
                    genome.fitness = 0.0

            new_population.sort(key=lambda g: g.fitness, reverse=True)
            population = new_population

            # Log best of generation
            best = population[0]
            print(f"  Best: {best.genome_id} (fitness={best.fitness:.3f}, "
                  f"precision={best.precision:.2f}, latency={best.latency_ms:.0f}ms)")

        # End of epoch
        epoch_best = population[0]

        # Update global best
        if global_best is None or epoch_best.fitness > global_best.fitness:
            global_best = epoch_best
            improvement = "NEW GLOBAL BEST!"
        else:
            improvement = f"(global best: {global_best.fitness:.3f})"

        epoch_duration = time.time() - epoch_start

        print(f"\n{'=' * 80}")
        print(f"EPOCH {epoch + 1} COMPLETE - Duration: {epoch_duration/60:.1f} min")
        print(f"{'=' * 80}")
        print(f"Epoch Best: {epoch_best.genome_id}")
        print(f"  Fitness: {epoch_best.fitness:.3f} {improvement}")
        print(f"  Precision: {epoch_best.precision*100:.1f}%")
        print(f"  Latency: {epoch_best.latency_ms:.0f}ms")
        print(f"  Parameters: top_k={epoch_best.top_k}, chunk={epoch_best.chunk_size}, "
              f"overlap={epoch_best.chunk_overlap}, threshold={epoch_best.similarity_threshold:.2f}")

        # Log epoch results
        with open(log_file, 'a') as f:
            f.write(json.dumps({
                "epoch": epoch,
                "duration_s": epoch_duration,
                "best_genome": asdict(epoch_best),
                "population_diversity": len(set(g.fitness for g in population)),
                "timestamp": datetime.now().isoformat()
            }) + '\n')

        # Save best genome
        with open(best_genomes_file, 'a') as f:
            f.write(json.dumps(asdict(epoch_best)) + '\n')

    # Final report
    print(f"\n{'=' * 80}")
    print("OVERNIGHT EVOLUTION COMPLETE")
    print(f"{'=' * 80}")
    print(f"\n🏆 Global Best: {global_best.genome_id}")
    print(f"   Fitness: {global_best.fitness:.3f}")
    print(f"   Precision: {global_best.precision*100:.1f}%")
    print(f"   Latency: {global_best.latency_ms:.0f}ms")
    print(f"   Grounded rate: {global_best.grounded_rate*100:.1f}%")
    print(f"\n   Optimal Parameters:")
    print(f"     top_k: {global_best.top_k}")
    print(f"     chunk_size: {global_best.chunk_size}")
    print(f"     chunk_overlap: {global_best.chunk_overlap}")
    print(f"     similarity_threshold: {global_best.similarity_threshold:.2f}")
    print(f"     num_predict: {global_best.num_predict}")
    print(f"     temperature: {global_best.temperature:.2f}")
    print(f"     context_window: {global_best.context_window}")

    # Save final best
    final_best_file = output_path / "global_best_genome.json"
    with open(final_best_file, 'w') as f:
        json.dump(asdict(global_best), f, indent=2)

    print(f"\n✓ Results saved to: {output_path}")
    print(f"✓ Evolution log: {log_file}")
    print(f"✓ Best genome: {final_best_file}")

if __name__ == "__main__":
    # Overnight configuration: 10 epochs × 20 generations × 10 population
    # = 2000 total evaluations = ~1.7 hours at 3s per test
    run_overnight_evolution(
        population_size=10,
        generations_per_epoch=20,
        max_epochs=10,
        elite_count=3
    )
