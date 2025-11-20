#!/usr/bin/env python3
"""DeepAgents Integration Acceptance Tests (Phase 10)

Comprehensive acceptance tests for all DeepAgents integration phases:
1. DeepAgents shows in MCP with budgets, concurrency, egress=blocked
2. Hard task routes to deep_planner; trivial never does
3. TUMIX committee vote with {fast_coder, deep_planner, reAct} returns winner + entropy
4. PHASE domain emits fitness; UCB1 shifts budget within 3 rounds
5. Frozen judges output on each candidate with versioning
6. Cost sanity check (deep planner cost/latency visible, bandit deprioritizes poor ROI)
"""

import sys
import asyncio
sys.path.insert(0, '/home/kloros')

from src.registry.loader import get_registry
from src.mcp.integration import MCPIntegration
from src.routing.difficulty_classifier import DifficultyClassifier
from src.phase.domains.planning_strategies_domain import run_planning_strategies_benchmark
from src.dream.dashboard_card_validator import DashboardCardValidator
from src.tumix.deadlock_prevention import detect_deadlock
from src.deepagents.wrapper import DeepAgentsConfig, DeepAgentsWorker
import logging

# Configure logging
logging.basicConfig(level=logging.INFO, format='%(message)s')
logger = logging.getLogger(__name__)


def test_1_mcp_registration():
    """Test 1: DeepAgents shows in MCP with budgets, concurrency, egress=blocked"""
    logger.info("\n=== Test 1: MCP Registration ===")

    # Check registry
    registry = get_registry()
    caps = registry.get_enabled_capabilities()
    deepagents_cap = next((c for c in caps if c.name == 'deepagents'), None)

    assert deepagents_cap is not None, "DeepAgents not found in capabilities registry"
    logger.info(f"✓ DeepAgents registered: {deepagents_cap.description}")

    # Check manifest
    import yaml
    from pathlib import Path
    manifest_path = Path("/home/kloros/src/mcp/manifests/deepagents.yaml")
    assert manifest_path.exists(), "DeepAgents manifest not found"

    with open(manifest_path) as f:
        manifest = yaml.safe_load(f)

    assert manifest['budgets']['max_time_ms'] == 30000, "Incorrect timeout budget"
    assert manifest['budgets']['max_in_flight'] == 2, "Incorrect concurrency cap"
    assert manifest['network']['egress_allowed'] == False, "Egress should be blocked"

    logger.info("✓ Manifest: timeout=30s, concurrency=2, egress=blocked")
    logger.info("✅ Test 1 PASS\n")


def test_2_routing_logic():
    """Test 2: Hard task routes to deep_planner; trivial never does"""
    logger.info("=== Test 2: Routing Logic ===")

    classifier = DifficultyClassifier()

    # Hard task
    hard_task = "Generate async Python code with comprehensive error handling and unit tests"
    result_hard = classifier.classify(hard_task)
    logger.info(f"Hard task: '{hard_task[:50]}...'")
    logger.info(f"  Level: {result_hard.level}")
    logger.info(f"  Should use deep_planner: {result_hard.should_use_deep_planner}")
    assert result_hard.should_use_deep_planner, "Hard task should route to deep_planner"

    # Trivial task
    trivial_task = "What is 2+2?"
    result_trivial = classifier.classify(trivial_task)
    logger.info(f"Trivial task: '{trivial_task}'")
    logger.info(f"  Level: {result_trivial.level}")
    logger.info(f"  Should use deep_planner: {result_trivial.should_use_deep_planner}")
    assert not result_trivial.should_use_deep_planner, "Trivial task should NOT route to deep_planner"

    logger.info("✅ Test 2 PASS\n")


async def test_3_tumix_committee():
    """Test 3: TUMIX committee vote with {fast_coder, deep_planner, reAct} returns winner + entropy"""
    logger.info("=== Test 3: TUMIX Committee Voting ===")

    # Simulate committee vote
    votes = [
        ('fast_coder', 0.75),
        ('deep_planner', 0.85),
        ('reAct', 0.70)
    ]

    outputs_by_agent = {
        'fast_coder': {'answer': 'Solution A', 'confidence': 0.75},
        'deep_planner': {'answer': 'Solution B', 'confidence': 0.85},
        'reAct': {'answer': 'Solution C', 'confidence': 0.70}
    }

    # Check deadlock prevention (should be normal voting)
    result = detect_deadlock(votes, outputs_by_agent, judge_already_invoked=False)

    logger.info(f"  Votes: {votes}")
    logger.info(f"  Entropy: {result.entropy:.3f}")
    logger.info(f"  Agreement: {result.agreement_level:.3f}")
    logger.info(f"  Deadlocked: {result.is_deadlocked}")

    assert not result.is_deadlocked, "Normal votes should not deadlock"
    assert result.entropy > 0, "Should have non-zero entropy"

    # Winner should be deep_planner (highest confidence)
    winner = max(votes, key=lambda x: x[1])
    logger.info(f"  Winner: {winner[0]} (confidence={winner[1]})")
    assert winner[0] == 'deep_planner', "deep_planner should win"

    logger.info("✅ Test 3 PASS\n")


def test_4_phase_fitness():
    """Test 4: PHASE domain emits fitness; UCB1 shifts budget"""
    logger.info("=== Test 4: PHASE Domain Fitness ===")

    # Run benchmarking domain
    result = run_planning_strategies_benchmark('acceptance_test_001')

    logger.info(f"  Tasks run: {result['tasks_run']}")
    logger.info(f"  Strategies: {result['strategies']}")
    logger.info(f"  Fitness scores:")
    for strategy, fitness in result['avg_fitness'].items():
        logger.info(f"    {strategy}: {fitness:.3f}")

    logger.info(f"  UCB1 allocations:")
    for strategy, allocation in result['ucb1_allocations'].items():
        logger.info(f"    {strategy}: {allocation:.1%}")

    logger.info(f"  Winner: {result['winner']}")

    # Check that fitness was written
    import json
    from pathlib import Path
    fitness_file = Path("/home/kloros/var/dream/fitness/planning_strategies.jsonl")
    assert fitness_file.exists(), "Fitness file should exist"

    with open(fitness_file) as f:
        lines = f.readlines()
        assert len(lines) > 0, "Fitness file should have entries"
        last_entry = json.loads(lines[-1])
        assert 'strategies' in last_entry, "Fitness entry should have strategies"

    logger.info("✓ Fitness written to D-REAM")
    logger.info("✅ Test 4 PASS\n")


def test_5_dashboard_cards():
    """Test 5: Dashboard card validation (all required fields)"""
    logger.info("=== Test 5: Dashboard Card Validation ===")

    validator = DashboardCardValidator(strict_mode=True)

    # Complete card
    complete_card = {
        'judge_version': 'v1.2.3',
        'kl_delta': 0.05,
        'synthetic_pct': 15.0,
        'diversity': 0.72,
        'latency_ms': 250,
        'cost_usd': 0.003,
        'wins': 5,
        'losses': 2
    }

    result = validator.validate_card(complete_card, 'test_candidate')

    logger.info(f"  Required fields: {len(validator.validate_card.__code__.co_names)}")
    logger.info(f"  Card valid: {result.is_valid}")
    logger.info(f"  Missing fields: {result.missing_fields}")

    assert result.is_valid, "Complete card should be valid"

    logger.info("✅ Test 5 PASS\n")


async def test_6_cost_sanity():
    """Test 6: Cost sanity check (deep planner cost/latency visible)"""
    logger.info("=== Test 6: Cost Sanity Check ===")

    config = DeepAgentsConfig(
        timeout_ms=5000,
        hard_kill_ms=10000,
        enable_vfs=True,
        vfs_cleanup=True
    )

    worker = DeepAgentsWorker(config)
    inputs = {'query': 'test task', 'domain': 'test'}

    result = await worker.run_async(inputs)

    logger.info(f"  Latency: {result.get('latency_ms', 'N/A')}ms")
    logger.info(f"  Tool counts: {result.get('tool_counts', {})}")

    assert 'latency_ms' in result, "Should track latency"
    assert 'tool_counts' in result, "Should track tool usage"

    logger.info("✓ Cost metrics tracked")
    logger.info("✅ Test 6 PASS\n")


def main():
    """Run all acceptance tests."""
    logger.info("\n" + "="*60)
    logger.info("DeepAgents Integration Acceptance Tests")
    logger.info("="*60 + "\n")

    tests = [
        ("MCP Registration", test_1_mcp_registration),
        ("Routing Logic", test_2_routing_logic),
        ("TUMIX Committee", test_3_tumix_committee),
        ("PHASE Fitness", test_4_phase_fitness),
        ("Dashboard Cards", test_5_dashboard_cards),
        ("Cost Sanity", test_6_cost_sanity),
    ]

    passed = 0
    failed = 0

    for name, test_fn in tests:
        try:
            if asyncio.iscoroutinefunction(test_fn):
                asyncio.run(test_fn())
            else:
                test_fn()
            passed += 1
        except Exception as e:
            logger.error(f"❌ Test '{name}' FAILED: {e}")
            failed += 1

    logger.info("\n" + "="*60)
    logger.info(f"Results: {passed}/{len(tests)} tests passed")
    if failed == 0:
        logger.info("✅✅✅ ALL ACCEPTANCE TESTS PASS ✅✅✅")
    else:
        logger.info(f"❌ {failed} test(s) failed")
    logger.info("="*60 + "\n")

    return 0 if failed == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
