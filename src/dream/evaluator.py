#!/usr/bin/env python3
"""
D-REAM Phase 2: Multi-Regime Evaluation Orchestrator
Coordinates trials, baselines, CIs, and candidate pack generation.
"""

import sys
import yaml
import time
import logging
from pathlib import Path
from typing import Dict, List, Optional, Any
from dataclasses import asdict

# Add dream to path
sys.path.insert(0, '/home/kloros/src/dream')

from baseline import Baselines, create_baseline_from_trials
from stats import compute_cis_for_metrics
from candidate_pack import CandidatePack, RegimeResult, create_regime_result, PackWriter, aggregate_regimes_v2
from scoring import compute_aggregate_score

logger = logging.getLogger('evaluator')


def load_regimes(domain: str) -> Dict[str, Dict]:
    """
    Load regime configurations for a domain.
    
    Args:
        domain: Domain name
    
    Returns:
        Dict mapping regime_name -> regime_config
    """
    regimes_path = Path('/home/kloros/src/dream/regimes.yaml')
    if not regimes_path.exists():
        logger.warning(f"regimes.yaml not found, using single 'normal' regime")
        return {'normal': {'workload': 'default', 'args': ''}}
    
    regimes = yaml.safe_load(regimes_path.read_text())
    domain_regimes = regimes.get('domains', {}).get(domain, {})
    
    if not domain_regimes:
        logger.warning(f"No regimes defined for {domain}, using single 'normal' regime")
        return {'normal': {'workload': 'default', 'args': ''}}
    
    return domain_regimes


def load_caps(domain: str) -> Dict[str, Any]:
    """
    Load safety caps for a domain.
    
    Args:
        domain: Domain name
    
    Returns:
        Dict with safety limits
    """
    caps_path = Path('/home/kloros/src/dream/caps.yaml')
    if not caps_path.exists():
        logger.warning(f"caps.yaml not found, using permissive defaults")
        return {'temp_peak_c': 100, 'errors': 0, 'oom': 0}
    
    caps = yaml.safe_load(caps_path.read_text())
    domain_caps = caps.get('domains', {}).get(domain, {})
    
    return domain_caps


def run_trials(evaluator: Any, genome: Any, regime_name: str, regime_cfg: Dict[str, Any], runs: int = 10, seed: int = 1337) -> Dict[str, List[float]]:
    """
    Execute multiple trials for a candidate in one regime.
    
    Args:
        evaluator: Domain evaluator instance
        genome: Genome array (normalized)
        regime_name: Regime name
        runs: Number of trials to run
        seed: Random seed for reproducibility
    
    Returns:
        Dict mapping metric_name -> [values]
    """
    logger.info(f"      Running {runs} trials for regime '{regime_name}'")
    
    kpis = {}
    
    for trial in range(runs):
        try:
            # Execute evaluation (existing domain evaluator)
            result = evaluator.evaluate(genome, regime_config=regime_cfg)
            
            # Extract metrics
            metrics = result.get('metrics', {})
            
            # Map domain-specific metrics to generic scoring names
            metrics = evaluator.map_metrics_to_scoring(metrics)
            
            # Initialize KPI arrays on first trial
            if trial == 0:
                for metric in metrics.keys():
                    kpis[metric] = []
            
            # Collect KPIs
            for metric, value in metrics.items():
                kpis[metric].append(float(value))
            
            logger.debug(f"         Trial {trial + 1}/{runs}: {len(metrics)} metrics collected")
            
        except Exception as e:
            logger.warning(f"         Trial {trial + 1}/{runs} failed: {e}")
            # Fill with zeros for failed trial
            for metric in kpis.keys():
                kpis[metric].append(0.0)
    
    # Log summary
    logger.info(f"      Completed {runs} trials, collected {len(kpis)} metrics")
    
    return kpis


def check_safety(kpis: Dict[str, List[float]], caps: Dict[str, Any]) -> bool:
    """
    Check if KPIs violate safety caps.
    
    Args:
        kpis: KPI arrays
        caps: Safety caps dict
    
    Returns:
        True if safe, False if any cap violated
    """
    for metric, values in kpis.items():
        if metric in caps:
            cap_value = caps[metric]
            
            # Check if any value exceeds cap
            for value in values:
                if value > cap_value:
                    logger.warning(f"Safety cap violated: {metric}={value} > {cap_value}")
                    return False
    
    return True


def evaluate_candidate(evaluator: Any, genome: Any, domain: str, generation: int, 
                      cand_id: str, run_id: str, code_hash: str, runs: int = 10) -> Dict:
    """
    Evaluate a candidate across multiple regimes with statistical rigor.
    
    Args:
        evaluator: Domain evaluator instance
        genome: Genome array (normalized)
        domain: Domain name
        generation: Generation number
        cand_id: Candidate ID
        run_id: Run ID from manifest
        code_hash: Code hash for baseline tracking
        runs: Number of trials per regime
    
    Returns:
        CandidatePack dict
    """
    logger.info(f"   Evaluating candidate {cand_id} (multi-regime, {runs} trials each)")
    
    # Load regimes and caps
    domain_regimes = load_regimes(domain)
    domain_caps = load_caps(domain)
    
    # Initialize baseline manager
    baselines = Baselines()
    
    # Decode genome
    decoded_genome = evaluator.genome_to_config(genome)
    
    # Evaluate each regime
    regime_results = []
    all_safe = True
    risk_profile = {}
    
    for regime_name, regime_cfg in domain_regimes.items():
        logger.info(f"   📊 Regime: {regime_name}")
        
        # Run trials
        kpis = run_trials(evaluator, genome, regime_name, regime_cfg, runs=runs)
        
        # Check safety
        safe = check_safety(kpis, domain_caps)
        if not safe:
            all_safe = False
            logger.warning(f"      ⚠️  Regime {regime_name} violated safety caps")
        
        # Update risk profile with max values
        for metric, values in kpis.items():
            if 'temp' in metric.lower() or 'error' in metric.lower() or 'oom' in metric.lower():
                risk_profile[metric] = max(values)
        
        # Load baseline
        baseline_dict = baselines.get(domain, regime_name)
        
        if baseline_dict:
            logger.info(f"      Using baseline: {baseline_dict.get('baseline_id', 'unknown')}")
        else:
            logger.info(f"      No baseline yet - will set after this run")
        
        # Compute CIs
        ci95 = compute_cis_for_metrics(kpis, seed=1337)
        
        # Create RegimeResult
        regime_result = create_regime_result(
            regime=regime_name,
            trials=runs,
            kpis=kpis,
            baseline=baseline_dict,
            ci95=ci95
        )
        
        regime_results.append(regime_result)
        
        # Set baseline if first successful run
        if not baseline_dict and safe:
            timestamp = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
            baseline = create_baseline_from_trials(
                domain=domain,
                regime=regime_name,
                kpis=kpis,
                genome=decoded_genome,
                code_hash=code_hash,
                timestamp=timestamp
            )
            
            if baselines.set(baseline):
                logger.info(f"      ✅ Set baseline: {baseline.baseline_id}")
    
    # Compute aggregate score
    aggregate = aggregate_regimes_v2(regime_results)
    
    # Override score if unsafe
    if not all_safe:
        aggregate['score_v2'] = float('-inf')
        logger.warning(f"   ⚠️  Candidate marked unsafe, score set to -inf")
    
    # Get fitness from first regime for backward compatibility
    first_regime_kpis = regime_results[0].kpis if regime_results else {}
    fitness = aggregate.get('score_v2', 0.0)
    
    # Create candidate pack
    pack = CandidatePack(
        schema="candidate_pack.v2",
        run_id=run_id,
        domain=domain,
        cand_id=cand_id,
        generation=generation,
        genome=decoded_genome,
        risk_profile=risk_profile,
        regimes=regime_results,
        aggregate=aggregate,
        safe=all_safe,
        fitness=fitness,
        artifacts={'regimes_evaluated': list(domain_regimes.keys())}
    )
    
    # Write pack
    pack_writer = PackWriter()
    pack_path = pack_writer.write(pack)
    
    logger.info(f"   📦 Candidate pack written: {pack_path}")
    logger.info(f"   🎯 Score v2: {aggregate.get('score_v2', 0.0):.4f}")
    logger.info(f"   {'✅' if all_safe else '⚠️ '} Safe: {all_safe}")
    
    return asdict(pack)


if __name__ == '__main__':
    # Test evaluator
    print("Testing evaluator.py...")

    # Load a domain
    from src.dream_legacy_domains.cpu_domain_evaluator import CPUDomainEvaluator
    import numpy as np
    
    evaluator = CPUDomainEvaluator()
    
    # Create test genome
    genome = np.random.uniform(-1, 1, len(evaluator.get_genome_spec()))
    
    # Evaluate
    pack = evaluate_candidate(
        evaluator=evaluator,
        genome=genome,
        domain='cpu',
        generation=999,
        cand_id='test_candidate',
        run_id='test_run_id',
        code_hash='sha256:test',
        runs=3  # Small number for testing
    )
    
    print(f"\n✓ Evaluation complete")
    print(f"  Regimes evaluated: {len(pack['regimes'])}")
    print(f"  Score v2: {pack['aggregate']['score_v2']:.4f}")
    print(f"  Safe: {pack['safe']}")
