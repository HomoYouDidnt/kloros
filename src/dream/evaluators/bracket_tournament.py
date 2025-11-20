"""
Bracket Tournament Implementation for D-REAM.

Implements true tournament-style bracket elimination:
- Round 1: 8 candidates → 4 matches (parallel)
- Round 2: 4 winners → 2 matches (parallel)
- Finals: 2 winners → 1 match
- Total time: 3 rounds × 2.5s = 7.5 seconds (vs 20 minutes sequential)

Replaces the sequential batch evaluation approach with proper
bracket-style competition.
"""

from __future__ import annotations
from pathlib import Path
from typing import Dict, Any, List
from concurrent.futures import ThreadPoolExecutor, as_completed
import time
import logging

from dream.test_runner import DirectTestRunner

logger = logging.getLogger(__name__)


class BracketMatch:
    """
    Head-to-head competition between two SPICA instances.

    Runs tests on both candidates and declares winner based on fitness.
    """

    def __init__(self, candidate_a: str | Path, candidate_b: str | Path,
                 runner: DirectTestRunner):
        """
        Args:
            candidate_a: Path to first SPICA instance
            candidate_b: Path to second SPICA instance
            runner: DirectTestRunner instance for test execution
        """
        self.candidate_a = Path(candidate_a)
        self.candidate_b = Path(candidate_b)
        self.runner = runner

    def run(self) -> Dict[str, Any]:
        """
        Run match and declare winner.

        Returns:
            {
                "winner": Path("spica-abc123"),
                "loser": Path("spica-def456"),
                "score_winner": 0.95,
                "score_loser": 0.87,
                "margin": 0.08,
                "duration_ms": 5000,
                "result_a": {...},
                "result_b": {...}
            }
        """
        logger.info(f"[MATCH] {self.candidate_a.name} vs {self.candidate_b.name}")

        start = time.time()

        result_a = self.runner.run_test(self.candidate_a)
        result_b = self.runner.run_test(self.candidate_b)

        duration_ms = (time.time() - start) * 1000

        if result_a["fitness"] > result_b["fitness"]:
            winner, loser = self.candidate_a, self.candidate_b
            score_winner, score_loser = result_a["fitness"], result_b["fitness"]
        elif result_b["fitness"] > result_a["fitness"]:
            winner, loser = self.candidate_b, self.candidate_a
            score_winner, score_loser = result_b["fitness"], result_a["fitness"]
        else:
            if result_a["duration_ms"] < result_b["duration_ms"]:
                winner, loser = self.candidate_a, self.candidate_b
                score_winner, score_loser = result_a["fitness"], result_b["fitness"]
                logger.info(f"[MATCH] Tie on fitness, {winner.name} wins on speed")
            else:
                winner, loser = self.candidate_b, self.candidate_a
                score_winner, score_loser = result_b["fitness"], result_a["fitness"]
                logger.info(f"[MATCH] Tie on fitness, {winner.name} wins on speed")

        margin = abs(score_winner - score_loser)

        logger.info(
            f"[MATCH] {winner.name} defeats {loser.name} "
            f"({score_winner:.3f} vs {score_loser:.3f}, margin={margin:.3f})"
        )

        return {
            "winner": winner,
            "loser": loser,
            "score_winner": score_winner,
            "score_loser": score_loser,
            "margin": margin,
            "duration_ms": duration_ms,
            "result_a": result_a,
            "result_b": result_b
        }


class BracketRound:
    """
    Collection of matches run in parallel.

    Executes all matches in a tournament round concurrently using ThreadPoolExecutor.
    """

    def __init__(self, matches: List[BracketMatch]):
        """
        Args:
            matches: List of BracketMatch instances to run
        """
        self.matches = matches

    def run_parallel(self, max_workers: int = 4) -> List[Path]:
        """
        Run all matches in parallel, return winners.

        Args:
            max_workers: Maximum number of concurrent matches

        Returns:
            List of winner instance paths
        """
        if not self.matches:
            logger.warning("[ROUND] No matches to run")
            return []

        logger.info(f"[ROUND] Running {len(self.matches)} matches in parallel (max_workers={max_workers})")

        winners = []
        start = time.time()

        with ThreadPoolExecutor(max_workers=max_workers) as executor:
            futures = {executor.submit(match.run): match for match in self.matches}

            for future in as_completed(futures):
                try:
                    result = future.result()
                    winners.append(result["winner"])

                    logger.info(
                        f"[ROUND] Match complete: {result['winner'].name} defeats {result['loser'].name} "
                        f"({result['score_winner']:.3f} vs {result['score_loser']:.3f})"
                    )
                except Exception as e:
                    match = futures[future]
                    logger.error(
                        f"[ROUND] Match failed: {match.candidate_a.name} vs {match.candidate_b.name}: {e}"
                    )

        duration_ms = (time.time() - start) * 1000
        logger.info(f"[ROUND] Round complete: {len(winners)} winners in {duration_ms:.0f}ms")

        return winners


class BracketTournament:
    """
    Complete bracket tournament orchestrator.

    Manages multi-round elimination tournament:
    - Creates matches by pairing candidates
    - Runs rounds in parallel
    - Advances winners to next round
    - Handles odd-numbered candidates with byes
    - Returns champion and complete bracket history
    """

    def __init__(self, candidates: List[str | Path], runner: DirectTestRunner):
        """
        Args:
            candidates: List of SPICA instance paths to compete
            runner: DirectTestRunner instance for test execution
        """
        self.candidates = [Path(c) for c in candidates]
        self.runner = runner
        self.bracket_history = []

    def run(self, max_workers: int = 4) -> Dict[str, Any]:
        """
        Run full bracket tournament.

        Args:
            max_workers: Maximum concurrent matches per round

        Returns:
            {
                "champion": Path("spica-xyz789"),
                "rounds": [round1_results, round2_results, finals_results],
                "total_duration_ms": 7500,
                "total_matches": 7,
                "total_candidates": 8
            }
        """
        logger.info(f"[TOURNAMENT] Starting with {len(self.candidates)} candidates")

        start = time.time()

        current_round = self.candidates.copy()
        round_num = 1
        total_matches = 0

        while len(current_round) > 1:
            logger.info(
                f"[TOURNAMENT] Round {round_num}: {len(current_round)} candidates → "
                f"{len(current_round)//2} matches"
            )

            matches = []
            bye_candidate = None

            for i in range(0, len(current_round), 2):
                if i + 1 < len(current_round):
                    match = BracketMatch(
                        current_round[i],
                        current_round[i+1],
                        self.runner
                    )
                    matches.append(match)
                else:
                    bye_candidate = current_round[i]
                    logger.info(f"[TOURNAMENT] Bye: {bye_candidate.name} advances automatically")

            round_obj = BracketRound(matches)
            winners = round_obj.run_parallel(max_workers=max_workers)

            if bye_candidate:
                winners.append(bye_candidate)

            self.bracket_history.append({
                "round": round_num,
                "candidates": len(current_round),
                "matches": len(matches),
                "winners": [str(w.name) for w in winners],
                "bye": str(bye_candidate.name) if bye_candidate else None
            })

            total_matches += len(matches)
            current_round = winners
            round_num += 1

        duration_ms = (time.time() - start) * 1000
        champion = current_round[0]

        logger.info(
            f"[TOURNAMENT] Complete! Champion: {champion.name} "
            f"(duration: {duration_ms:.0f}ms, matches: {total_matches})"
        )

        return {
            "champion": champion,
            "rounds": self.bracket_history,
            "total_duration_ms": duration_ms,
            "total_matches": total_matches,
            "total_candidates": len(self.candidates)
        }
