#!/usr/bin/env python3
"""
SPICA Evolutionary Loop - Champion tracking and generational improvement.

Maintains champion registry, provides evolutionary candidate generation.
"""

import json
import random
import hashlib
from pathlib import Path
from typing import Dict, List, Any, Optional
from datetime import datetime, timezone
import logging

logger = logging.getLogger(__name__)

CHAMPIONS_REGISTRY = Path("/home/kloros/artifacts/spica/champions.json")
EVOLUTION_LOG = Path("/home/kloros/artifacts/spica/evolution.jsonl")


def _init_registry() -> Dict[str, Any]:
    """Initialize empty champion registry."""
    return {
        "schema": "spica.champions/v1",
        "champions": {},
        "last_updated": datetime.now(timezone.utc).isoformat()
    }


def load_champions() -> Dict[str, Any]:
    """Load champion registry from disk."""
    if not CHAMPIONS_REGISTRY.exists():
        return _init_registry()

    try:
        return json.loads(CHAMPIONS_REGISTRY.read_text())
    except (json.JSONDecodeError, OSError) as e:
        logger.error(f"Failed to load champions registry: {e}")
        return _init_registry()


def save_champions(registry: Dict[str, Any]) -> None:
    """Persist champion registry to disk."""
    CHAMPIONS_REGISTRY.parent.mkdir(parents=True, exist_ok=True)
    registry["last_updated"] = datetime.now(timezone.utc).isoformat()
    CHAMPIONS_REGISTRY.write_text(json.dumps(registry, indent=2))


def record_champion(
    question_id: str,
    champion_params: Dict[str, Any],
    fitness: float,
    tournament_data: Optional[Dict[str, Any]] = None
) -> None:
    """
    Record tournament champion in registry.

    Args:
        question_id: Curiosity question identifier
        champion_params: Winning parameter configuration
        fitness: Champion fitness score (0.0-1.0)
        tournament_data: Optional tournament metadata
    """
    registry = load_champions()

    record = {
        "params": champion_params,
        "fitness": fitness,
        "recorded_at": datetime.now(timezone.utc).isoformat(),
        "generation": registry["champions"].get(question_id, {}).get("generation", 0) + 1
    }

    if tournament_data:
        record["tournament_metadata"] = {
            "total_candidates": tournament_data.get("total_candidates", 0),
            "suite_id": tournament_data.get("artifacts", {}).get("tournament", {}).get("suite_id")
        }

    prev_champion = registry["champions"].get(question_id)
    if prev_champion:
        prev_fitness = prev_champion.get("fitness", 0.0)
        if fitness > prev_fitness:
            logger.info(f"New champion for {question_id}: fitness {prev_fitness:.3f} → {fitness:.3f}")
            record["improvement"] = fitness - prev_fitness
        elif fitness == prev_fitness:
            logger.info(f"Champion tied for {question_id}: fitness={fitness:.3f}")
        else:
            logger.warning(f"Champion regressed for {question_id}: fitness {prev_fitness:.3f} → {fitness:.3f}")
    else:
        logger.info(f"First champion for {question_id}: fitness={fitness:.3f}")

    registry["champions"][question_id] = record
    save_champions(registry)

    # Bridge to deployment pipeline
    try:
        from src.dream.spica_deployment_bridge import record_champion_for_deployment
        record_champion_for_deployment(question_id, champion_params, fitness, tournament_data)
    except Exception as e:
        logger.error(f"Failed to record champion for deployment: {e}")

    EVOLUTION_LOG.parent.mkdir(parents=True, exist_ok=True)
    log_entry = {
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "question_id": question_id,
        "champion_params": champion_params,
        "fitness": fitness,
        "generation": record["generation"]
    }
    with EVOLUTION_LOG.open("a") as f:
        f.write(json.dumps(log_entry) + "\n")


def get_champion(question_id: str) -> Optional[Dict[str, Any]]:
    """Get current champion params for a question."""
    registry = load_champions()
    champion_record = registry["champions"].get(question_id)
    if champion_record:
        return champion_record.get("params")
    return None


def mutate_params(base_params: Dict[str, Any], mutation_rate: float = 0.2) -> Dict[str, Any]:
    """
    Generate mutation of parameter set.

    Args:
        base_params: Base parameter configuration
        mutation_rate: Probability of mutating each parameter (0.0-1.0)

    Returns:
        Mutated parameter configuration
    """
    mutated = base_params.copy()

    for key, value in base_params.items():
        if random.random() < mutation_rate:
            if isinstance(value, bool):
                mutated[key] = not value
            elif isinstance(value, (int, float)):
                if isinstance(value, int):
                    delta = random.randint(-2, 2)
                    mutated[key] = max(1, value + delta)
                else:
                    delta = random.uniform(-0.2, 0.2)
                    mutated[key] = max(0.0, min(1.0, value + delta))
            elif isinstance(value, str):
                pass

    if "name" in mutated:
        mutated["name"] = f"{mutated['name']}_mut_{random.randint(1000, 9999)}"

    return mutated


def generate_evolutionary_candidates(
    question_id: str,
    min_count: int = 8,
    exploration_ratio: float = 0.5
) -> List[Dict[str, Any]]:
    """
    Generate candidate strategies using evolutionary approach.

    Strategy:
    - Include current champion (exploitation)
    - Generate mutations of champion (local search)
    - Include diverse baseline strategies (exploration)

    Args:
        question_id: Curiosity question identifier
        min_count: Minimum number of candidates
        exploration_ratio: Fraction of candidates for exploration vs exploitation

    Returns:
        List of candidate parameter configurations
    """
    candidates = []

    champion_params = get_champion(question_id)

    if champion_params:
        candidates.append(champion_params.copy())

        num_mutations = max(1, int((1 - exploration_ratio) * min_count) - 1)
        for i in range(num_mutations):
            mutation_rate = 0.1 + (i * 0.1)
            mutated = mutate_params(champion_params, mutation_rate=mutation_rate)
            candidates.append(mutated)

    baseline_strategies = [
        {"name": "conservative", "temperature": 0.3, "explore": False},
        {"name": "aggressive", "temperature": 0.9, "explore": True},
        {"name": "balanced", "temperature": 0.6, "explore": True},
        {"name": "adaptive", "temperature": 0.7, "adaptive_temp": True},
    ]

    remaining = min_count - len(candidates)
    if remaining > 0:
        candidates.extend(baseline_strategies[:remaining])

    while len(candidates) < min_count:
        candidates.append({
            "name": f"variant_{len(candidates)}",
            "temperature": random.uniform(0.3, 0.9),
            "explore": random.choice([True, False])
        })

    return candidates[:min_count]


if __name__ == "__main__":
    import sys

    if len(sys.argv) < 2:
        print("Usage: python spica_evolution.py <command>")
        print("Commands:")
        print("  champions              - List all champions")
        print("  record <qid> <params>  - Record champion")
        print("  generate <qid>         - Generate evolutionary candidates")
        sys.exit(1)

    command = sys.argv[1]

    if command == "champions":
        registry = load_champions()
        print(json.dumps(registry, indent=2))

    elif command == "record" and len(sys.argv) >= 4:
        qid = sys.argv[2]
        params = json.loads(sys.argv[3])
        record_champion(qid, params, 1.0)
        print(f"Recorded champion for {qid}")

    elif command == "generate" and len(sys.argv) >= 3:
        qid = sys.argv[2]
        candidates = generate_evolutionary_candidates(qid)
        print(json.dumps(candidates, indent=2))

    else:
        print(f"Unknown command: {command}")
        sys.exit(1)
