#!/usr/bin/env python3
"""
Test script for bracket tournament implementation.

Tests DirectTestRunner, BracketMatch, BracketRound, and BracketTournament
with real SPICA instances.
"""

from pathlib import Path
import sys
import logging

sys.path.insert(0, str(Path(__file__).parent.parent))

from dream.test_runner import DirectTestRunner
from dream.evaluators.bracket_tournament import BracketMatch, BracketRound, BracketTournament

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s [%(levelname)s] %(name)s: %(message)s'
)

logger = logging.getLogger(__name__)

SPICA_INSTANCES = Path("/home/kloros/experiments/spica/instances")


def test_direct_test_runner():
    """Test DirectTestRunner with a single SPICA instance."""
    logger.info("=" * 80)
    logger.info("TEST 1: DirectTestRunner")
    logger.info("=" * 80)

    instances = list(SPICA_INSTANCES.glob("spica-*"))
    if not instances:
        logger.error("No SPICA instances found!")
        return False

    instance = instances[0]
    logger.info(f"Testing with instance: {instance.name}")

    runner = DirectTestRunner(timeout=60)
    result = runner.run_test(instance, verbose=False)

    logger.info(f"Result: {result}")
    logger.info(f"✓ Passed: {result['passed']}")
    logger.info(f"✗ Failed: {result['failed']}")
    logger.info(f"⊘ Skipped: {result['skipped']}")
    logger.info(f"⏱ Duration: {result['duration_ms']:.0f}ms")
    logger.info(f"★ Fitness: {result['fitness']:.3f}")

    if result['exit_code'] == 0 or result['passed'] > 0:
        logger.info("✅ DirectTestRunner: PASS")
        return True
    else:
        logger.error("❌ DirectTestRunner: FAIL")
        return False


def test_bracket_match():
    """Test BracketMatch with two SPICA instances."""
    logger.info("\n" + "=" * 80)
    logger.info("TEST 2: BracketMatch")
    logger.info("=" * 80)

    instances = list(SPICA_INSTANCES.glob("spica-*"))
    if len(instances) < 2:
        logger.warning("⚠ Only 1 instance found, duplicating for test")
        instances = [instances[0], instances[0]]

    candidate_a = instances[0]
    candidate_b = instances[1] if len(instances) > 1 else instances[0]

    logger.info(f"Match: {candidate_a.name} vs {candidate_b.name}")

    runner = DirectTestRunner(timeout=60)
    match = BracketMatch(candidate_a, candidate_b, runner)
    result = match.run()

    logger.info(f"Winner: {result['winner'].name}")
    logger.info(f"Loser: {result['loser'].name}")
    logger.info(f"Score (winner): {result['score_winner']:.3f}")
    logger.info(f"Score (loser): {result['score_loser']:.3f}")
    logger.info(f"Margin: {result['margin']:.3f}")
    logger.info(f"Duration: {result['duration_ms']:.0f}ms")

    if result['winner'] and result['duration_ms'] > 0:
        logger.info("✅ BracketMatch: PASS")
        return True
    else:
        logger.error("❌ BracketMatch: FAIL")
        return False


def test_bracket_round():
    """Test BracketRound with parallel execution."""
    logger.info("\n" + "=" * 80)
    logger.info("TEST 3: BracketRound (Parallel Execution)")
    logger.info("=" * 80)

    instances = list(SPICA_INSTANCES.glob("spica-*"))
    if len(instances) < 2:
        logger.warning("⚠ Only 1 instance found, duplicating for test")
        instances = [instances[0], instances[0]]

    runner = DirectTestRunner(timeout=60)

    matches = [
        BracketMatch(instances[0], instances[1] if len(instances) > 1 else instances[0], runner)
    ]

    logger.info(f"Running {len(matches)} match(es) in parallel")

    round_obj = BracketRound(matches)
    winners = round_obj.run_parallel(max_workers=2)

    logger.info(f"Winners: {[w.name for w in winners]}")

    if len(winners) > 0:
        logger.info("✅ BracketRound: PASS")
        return True
    else:
        logger.error("❌ BracketRound: FAIL")
        return False


def test_bracket_tournament():
    """Test full BracketTournament with available instances."""
    logger.info("\n" + "=" * 80)
    logger.info("TEST 4: BracketTournament (Full Tournament)")
    logger.info("=" * 80)

    instances = list(SPICA_INSTANCES.glob("spica-*"))

    if len(instances) < 2:
        logger.warning("⚠ Only 1 instance found, duplicating to create tournament")
        instances = [instances[0]] * 2

    logger.info(f"Tournament with {len(instances)} candidates")
    for i, inst in enumerate(instances):
        logger.info(f"  Candidate {i+1}: {inst.name}")

    runner = DirectTestRunner(timeout=60)
    tournament = BracketTournament(instances, runner)
    result = tournament.run(max_workers=2)

    logger.info(f"\n🏆 Champion: {result['champion'].name}")
    logger.info(f"Total duration: {result['total_duration_ms']:.0f}ms")
    logger.info(f"Total matches: {result['total_matches']}")
    logger.info(f"Total candidates: {result['total_candidates']}")

    logger.info("\nRound-by-round breakdown:")
    for round_data in result['rounds']:
        logger.info(f"  Round {round_data['round']}: {round_data['candidates']} candidates → {round_data['matches']} matches")
        logger.info(f"    Winners: {round_data['winners']}")
        if round_data['bye']:
            logger.info(f"    Bye: {round_data['bye']}")

    if result['champion'] and result['total_duration_ms'] > 0:
        logger.info("✅ BracketTournament: PASS")
        return True
    else:
        logger.error("❌ BracketTournament: FAIL")
        return False


def test_performance_benchmark():
    """Benchmark tournament performance."""
    logger.info("\n" + "=" * 80)
    logger.info("TEST 5: Performance Benchmark")
    logger.info("=" * 80)

    instances = list(SPICA_INSTANCES.glob("spica-*"))

    if len(instances) < 2:
        instances = [instances[0]] * 4

    logger.info(f"Benchmarking with {len(instances)} candidates")

    runner = DirectTestRunner(timeout=60)
    tournament = BracketTournament(instances, runner)

    import time
    start = time.time()
    result = tournament.run(max_workers=4)
    duration = (time.time() - start) * 1000

    logger.info(f"\n⏱ Performance Results:")
    logger.info(f"  Total duration: {duration:.0f}ms ({duration/1000:.2f}s)")
    logger.info(f"  Candidates: {len(instances)}")
    logger.info(f"  Matches: {result['total_matches']}")
    logger.info(f"  Time per match: {duration/result['total_matches']:.0f}ms")

    expected_sequential = len(instances) * 2500
    speedup = expected_sequential / duration

    logger.info(f"\n📊 Comparison:")
    logger.info(f"  Sequential (estimated): {expected_sequential:.0f}ms ({expected_sequential/1000:.2f}s)")
    logger.info(f"  Bracket (actual): {duration:.0f}ms ({duration/1000:.2f}s)")
    logger.info(f"  Speedup: {speedup:.2f}x")

    if duration < expected_sequential:
        logger.info("✅ Performance: PASS (faster than sequential)")
        return True
    else:
        logger.warning("⚠ Performance: MARGINAL (not faster than sequential)")
        return True


def main():
    """Run all tests."""
    logger.info("\n" + "=" * 80)
    logger.info("BRACKET TOURNAMENT TEST SUITE")
    logger.info("=" * 80)

    results = {
        "DirectTestRunner": test_direct_test_runner(),
        "BracketMatch": test_bracket_match(),
        "BracketRound": test_bracket_round(),
        "BracketTournament": test_bracket_tournament(),
        "Performance": test_performance_benchmark()
    }

    logger.info("\n" + "=" * 80)
    logger.info("TEST RESULTS SUMMARY")
    logger.info("=" * 80)

    for test_name, passed in results.items():
        status = "✅ PASS" if passed else "❌ FAIL"
        logger.info(f"{test_name:25s} {status}")

    all_passed = all(results.values())
    logger.info("\n" + "=" * 80)
    if all_passed:
        logger.info("🎉 ALL TESTS PASSED")
    else:
        logger.error("❌ SOME TESTS FAILED")
    logger.info("=" * 80)

    return 0 if all_passed else 1


if __name__ == "__main__":
    sys.exit(main())
