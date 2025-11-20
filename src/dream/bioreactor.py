# bioreactor.py — pressure→differentiation→insertion pipeline with fitness ledger integration
from __future__ import annotations
import json, os, time, random, sys, logging
from pathlib import Path
from typing import Dict, List, Optional, Tuple
from .genome import AgentGenome, BehavioralPhenotype, EcologicalRole, LifecycleState

# Import fitness ledger for real pressure computation
sys.path.insert(0, str(Path(__file__).parents[1]))
from kloros.observability.fitness_ledger import compute_niche_pressure

logger = logging.getLogger(__name__)

ROOT = Path.home() / ".kloros/bioreactor"
REG  = Path.home() / ".kloros/registry/niche_map.json"
PROD_LEDGER = Path.home() / ".kloros/observability/fitness_ledger.jsonl"
PHASE_LEDGER = Path.home() / ".kloros/lineage/phase_fitness.jsonl"

# Dual-source fitness configuration (environment overridable)
class FitnessConfig:
    W_PROD = float(os.getenv("KLR_W_PROD", "0.6"))
    W_PHASE = float(os.getenv("KLR_W_PHASE", "0.4"))
    PROD_WINDOW_SEC = int(os.getenv("KLR_PROD_WINDOW_SEC", "3600"))
    PHASE_WINDOW_SEC = int(os.getenv("KLR_PHASE_WINDOW_SEC", "86400"))
    MIN_PROD_CASES = int(os.getenv("KLR_MIN_PROD_CASES", "3"))
    MIN_PHASE_CASES = int(os.getenv("KLR_MIN_PHASE_CASES", "3"))
    PHASE_HALF_LIFE_SEC = int(os.getenv("KLR_PHASE_HALF_LIFE_SEC", "43200"))  # 12 hours

def _load_registry() -> Dict:
    return json.loads(Path(REG).read_text())

def compute_pressure(ecosystem: str, window_s: float = 3600) -> Dict[str, float]:
    """
    Compute ecological pressure for each niche in an ecosystem.

    Uses fitness ledger to calculate pressure based on:
    - Recent failure rates (70% weight)
    - Incident volume (30% weight)

    Args:
        ecosystem: Ecosystem name (e.g., "queue_management")
        window_s: Time window for pressure calculation (default 1 hour)

    Returns:
        Dict mapping niche → pressure (0.0-1.0, higher = more failures)
    """
    reg = _load_registry()["ecosystems"][ecosystem]
    niches = list(reg["niches"].keys())

    pressure_map = {}
    for niche in niches:
        pressure = compute_niche_pressure(ecosystem, niche, window_s=window_s)
        pressure_map[niche] = pressure
        logger.info(f"Computed pressure for {ecosystem}/{niche}: {pressure:.3f}")

    return pressure_map

def differentiate(niche: str, ecosystem: str, m: int = 3) -> List[AgentGenome]:
    out = []
    for i in range(m):
        pheno = BehavioralPhenotype(
            latency_budget_ms=500 - i*50,
            throughput_target_qps=50 + i*10,
            safety_guardrails=["no_mutation_runtime","readonly_fs"],
            cooperation_style=random.choice(["leader","support","peer"]),
            communication_protocols=["chem://Q_*","chem://synth.*"]
        )
        g = AgentGenome(
            name=f"{niche}_{int(time.time())}_{i}",
            ecosystem=ecosystem,
            niche=niche,
            ecological_role=EcologicalRole.STABILIZER,
            phenotype=pheno,
            module_code="# TODO: generated implementation",
        )
        out.append(g)
    return out

def _load_ledger(path: Path) -> List[Dict]:
    """Load JSONL ledger, return empty list if missing."""
    if not path.exists():
        return []
    rows = []
    with open(path, 'r') as f:
        for line in f:
            line = line.strip()
            if line:
                try:
                    rows.append(json.loads(line))
                except json.JSONDecodeError:
                    continue
    return rows

def _in_window(ts: float, now: float, window: float) -> bool:
    """Check if timestamp is within window."""
    return (now - ts) <= window

def _production_fitness(candidate: str, now: float, window: float, rows: List[Dict]) -> Tuple[Optional[float], int]:
    """
    Calculate production fitness from fitness_ledger.jsonl.

    Returns:
        (fitness_score, num_observations) where fitness is None if insufficient data
    """
    observations = [r for r in rows
                   if r.get("zooid") == candidate and _in_window(r.get("ts", 0), now, window)]

    if not observations:
        return None, 0

    # Success rate (ok/total)
    ok_count = sum(1 for r in observations if r.get("ok") is True)
    success_rate = ok_count / len(observations)

    # TTR penalty (lower TTR = better)
    ttr_values = [r.get("ttr_ms", 0) for r in observations if "ttr_ms" in r and r.get("ok") is True]
    if ttr_values:
        avg_ttr = sum(ttr_values) / len(ttr_values)
        ttr_penalty = 1.0 / (1.0 + (avg_ttr / 500.0))  # Normalize around 500ms
    else:
        ttr_penalty = 0.5  # Neutral if no TTR data

    # Weighted combination: 60% success rate, 40% speed
    fitness = 0.6 * success_rate + 0.4 * ttr_penalty

    return fitness, len(observations)

def _phase_fitness(candidate: str, now: float, window: float, rows: List[Dict]) -> Tuple[Optional[float], int]:
    """
    Calculate PHASE synthetic fitness from phase_fitness.jsonl.

    Returns:
        (fitness_score, num_observations) where fitness is None if insufficient data
    """
    observations = [r for r in rows
                   if r.get("candidate") == candidate and _in_window(r.get("ts", 0), now, window)]

    if not observations:
        return None, 0

    # Average composite PHASE fitness with exponential time decay
    half_life = FitnessConfig.PHASE_HALF_LIFE_SEC
    decay_lambda = 0.693147 / half_life  # ln(2) / half_life

    weighted_sum = 0.0
    weight_sum = 0.0

    for r in observations:
        age = now - r.get("ts", now)
        weight = 2.0 ** (-age / half_life)  # Exponential decay
        fitness = r.get("composite_phase_fitness", 0.0)
        weighted_sum += fitness * weight
        weight_sum += weight

    if weight_sum > 0:
        return weighted_sum / weight_sum, len(observations)
    else:
        return None, 0

def fused_fitness(candidate: str, now: float, prod_rows: List[Dict], phase_rows: List[Dict]) -> Dict:
    """
    Calculate fused fitness from production and PHASE sources with confidence gating.

    Returns:
        Dict with: score, prod_fitness, phase_fitness, w_prod, w_phase, n_prod, n_phase
    """
    cfg = FitnessConfig

    # Calculate individual fitness scores
    prod_fitness, n_prod = _production_fitness(candidate, now, cfg.PROD_WINDOW_SEC, prod_rows)
    phase_fitness, n_phase = _phase_fitness(candidate, now, cfg.PHASE_WINDOW_SEC, phase_rows)

    # Confidence gating: require minimum observations
    prod_ok = prod_fitness is not None and n_prod >= cfg.MIN_PROD_CASES
    phase_ok = phase_fitness is not None and n_phase >= cfg.MIN_PHASE_CASES

    # No data at all
    if not prod_ok and not phase_ok:
        return {
            "score": 0.0,
            "prod_fitness": None,
            "phase_fitness": None,
            "w_prod": 0.0,
            "w_phase": 0.0,
            "n_prod": n_prod,
            "n_phase": n_phase,
            "reason": "insufficient_data"
        }

    # Determine weights based on available data
    w_prod = cfg.W_PROD if prod_ok else 0.0
    w_phase = cfg.W_PHASE if phase_ok else 0.0

    # If only one source available, use it exclusively
    if prod_ok and not phase_ok:
        w_prod = 1.0
    elif phase_ok and not prod_ok:
        w_phase = 1.0

    # Calculate fused score
    total_weight = w_prod + w_phase
    if total_weight > 0:
        score = (w_prod * (prod_fitness or 0.0) + w_phase * (phase_fitness or 0.0)) / total_weight
    else:
        score = 0.0

    return {
        "score": score,
        "prod_fitness": prod_fitness,
        "phase_fitness": phase_fitness,
        "w_prod": w_prod,
        "w_phase": w_phase,
        "n_prod": n_prod,
        "n_phase": n_phase,
        "reason": "ok"
    }

def tournament_score(g: AgentGenome, prod_rows: List[Dict], phase_rows: List[Dict], now: float) -> float:
    """
    Calculate tournament score using fused fitness from production and PHASE.

    Logs detailed fitness breakdown for observability.
    """
    fitness_breakdown = fused_fitness(g.name, now, prod_rows, phase_rows)

    # Log breakdown for observability
    prod_str = f"{fitness_breakdown['prod_fitness']:.3f}" if fitness_breakdown['prod_fitness'] is not None else "N/A"
    phase_str = f"{fitness_breakdown['phase_fitness']:.3f}" if fitness_breakdown['phase_fitness'] is not None else "N/A"

    logger.info(
        f"Fitness for {g.name}: "
        f"fused={fitness_breakdown['score']:.3f} "
        f"[prod={prod_str} (n={fitness_breakdown['n_prod']}, w={fitness_breakdown['w_prod']:.2f}), "
        f"phase={phase_str} (n={fitness_breakdown['n_phase']}, w={fitness_breakdown['w_phase']:.2f})] "
        f"reason={fitness_breakdown['reason']}"
    )

    return fitness_breakdown["score"]

def select_winners(gs: List[AgentGenome], prod_rows: List[Dict], phase_rows: List[Dict], now: float, k: int = 2) -> List[AgentGenome]:
    """
    Select top k winners via tournament scoring with fused fitness.

    Args:
        gs: Candidate genomes
        prod_rows: Production fitness ledger
        phase_rows: PHASE fitness ledger
        now: Current timestamp
        k: Number of winners to select

    Returns:
        Top k genomes ranked by fused fitness
    """
    ranked = sorted(gs, key=lambda g: tournament_score(g, prod_rows, phase_rows, now), reverse=True)
    return ranked[:k]

def insert_into_registry(ecosystem: str, niche: str, winners: List[AgentGenome]):
    reg = _load_registry()
    bucket = reg["ecosystems"][ecosystem]["niches"].setdefault(niche, [])
    for w in winners:
        bucket.append(w.name)
    reg["version"] = reg.get("version", 0) + 1

    # Save versioned snapshot before overwriting
    version = reg["version"]
    snapshot_path = REG.parent / f"niche_map.v{version}.json"
    snapshot_path.write_text(json.dumps(reg, indent=2))
    logger.info(f"Saved registry snapshot: {snapshot_path}")

    # Update current registry
    Path(REG).write_text(json.dumps(reg, indent=2))

def bioreactor_tick(ecosystem: str, pressure_threshold: float = 0.5, niches_filter: List[str] = None):
    """
    Run bioreactor evolution cycle for an ecosystem with PHASE integration.

    Args:
        ecosystem: Ecosystem to evolve (e.g., "queue_management")
        pressure_threshold: Minimum pressure to trigger evolution (0.0-1.0)
        niches_filter: Optional list of specific niches to evolve (None = check all)

    Returns:
        Dict with evolution results including fitness breakdowns
    """
    now = time.time()

    logger.info(f"Bioreactor tick starting for ecosystem: {ecosystem}")
    logger.info(f"Pressure threshold: {pressure_threshold}")
    logger.info(f"Fitness config: W_PROD={FitnessConfig.W_PROD}, W_PHASE={FitnessConfig.W_PHASE}")

    # Load fitness ledgers
    logger.info(f"Loading production ledger: {PROD_LEDGER}")
    prod_rows = _load_ledger(PROD_LEDGER)
    logger.info(f"Loaded {len(prod_rows)} production observations")

    logger.info(f"Loading PHASE ledger: {PHASE_LEDGER}")
    phase_rows = _load_ledger(PHASE_LEDGER)
    logger.info(f"Loaded {len(phase_rows)} PHASE observations")

    # Compute pressure for all niches
    pressure = compute_pressure(ecosystem, window_s=3600)

    # Filter to specific niches if requested
    if niches_filter:
        pressure = {n: p for n, p in pressure.items() if n in niches_filter}
        logger.info(f"Filtered to niches: {niches_filter}")

    evolved_niches = []
    skipped_niches = []

    for niche, p in pressure.items():
        if p < pressure_threshold:
            skipped_niches.append((niche, p))
            logger.info(f"Skipping {niche}: pressure {p:.3f} < threshold {pressure_threshold}")
            continue

        logger.warning(f"Evolving {niche}: pressure {p:.3f} exceeds threshold {pressure_threshold}")

        # Generate new candidate challengers
        new_cands = differentiate(niche, ecosystem, m=3)
        logger.info(f"Generated {len(new_cands)} new challenger candidates for {niche}")

        # Include existing zooids from registry as defenders
        reg = _load_registry()
        existing_zooid_names = reg["ecosystems"][ecosystem]["niches"].get(niche, [])
        existing_genomes = []
        for zooid_name in existing_zooid_names:
            # Create genome stubs for existing zooids so they can compete
            genome = AgentGenome(
                name=zooid_name,
                ecosystem=ecosystem,
                niche=niche,
                ecological_role=EcologicalRole.STABILIZER,
                phenotype=BehavioralPhenotype(
                    latency_budget_ms=500,
                    throughput_target_qps=50,
                    safety_guardrails=["no_mutation_runtime","readonly_fs"],
                    cooperation_style="defender",
                    communication_protocols=["chem://Q_*"]
                ),
                module_code="# Existing defender"
            )
            existing_genomes.append(genome)

        logger.info(f"Loaded {len(existing_genomes)} existing defenders for {niche}: {existing_zooid_names}")

        # DEATH MATCH: New challengers vs existing defenders!
        all_candidates = existing_genomes + new_cands
        logger.info(f"💀 DEATH MATCH: {len(all_candidates)} total combatants ({len(existing_genomes)} defenders + {len(new_cands)} challengers)")

        # Select winners via tournament with fused fitness
        winners = select_winners(all_candidates, prod_rows, phase_rows, now, k=2)
        logger.info(f"🏆 Selected {len(winners)} winners for {niche}: {[w.name for w in winners]}")

        # Insert into registry
        insert_into_registry(ecosystem, niche, winners)
        evolved_niches.append((niche, p, winners))

    logger.info(f"Bioreactor tick complete:")
    logger.info(f"  - Evolved: {len(evolved_niches)} niches")
    logger.info(f"  - Skipped: {len(skipped_niches)} niches (below threshold)")

    return {
        "ecosystem": ecosystem,
        "evolved": evolved_niches,
        "skipped": skipped_niches,
        "timestamp": now,
        "fitness_config": {
            "w_prod": FitnessConfig.W_PROD,
            "w_phase": FitnessConfig.W_PHASE,
            "prod_observations": len(prod_rows),
            "phase_observations": len(phase_rows)
        }
    }

if __name__ == "__main__":
    import sys

    # Set up logging
    logging.basicConfig(
        level=logging.INFO,
        format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
    )

    ROOT.mkdir(parents=True, exist_ok=True)

    # Parse command line args
    ecosystem = sys.argv[1] if len(sys.argv) > 1 else "queue_management"
    threshold = float(sys.argv[2]) if len(sys.argv) > 2 else 0.3

    logger.info(f"Starting bioreactor: ecosystem={ecosystem}, threshold={threshold}")

    result = bioreactor_tick(ecosystem, pressure_threshold=threshold)

    logger.info(f"Bioreactor result: {result}")
