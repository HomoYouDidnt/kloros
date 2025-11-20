# Tournament Refactoring Plan

## Current Implementation (BROKEN)

**File:** `/home/kloros/src/dream/evaluators/spica_tournament_evaluator.py`

**What it does:**
```python
# Spawn ALL 8 candidates
for i, cand in enumerate(candidates):
    spawn_instance(cand)

# Run ALL 8 through PHASE sequentially (20 minutes!)
tournament = submit_tournament(instances=ALL_8)

# Pick winner = max(fitness)
champion_idx = fitnesses.index(max(fitnesses))
```

**Problems:**
1. ❌ Uses PHASE adapter (designed for 3-7 AM sequential validation)
2. ❌ Runs ALL candidates sequentially (~2.5s × 8 = 20 seconds minimum)
3. ❌ No actual "tournament" - just batch evaluation
4. ❌ No bracket elimination
5. ❌ Not parallelizable

---

## Proposed Implementation (BRACKET TOURNAMENT)

### Architecture

Create new file: `/home/kloros/src/dream/evaluators/bracket_tournament.py`

**Key Components:**

1. **BracketMatch** - Single head-to-head competition
2. **BracketRound** - Collection of matches run in parallel
3. **BracketTournament** - Complete tournament orchestrator

### Flow Diagram

```
Round 1: 8 candidates → 4 matches (parallel)
  Match 1: A vs B → Winner: B
  Match 2: C vs D → Winner: C
  Match 3: E vs F → Winner: F
  Match 4: G vs H → Winner: H

Round 2: 4 winners → 2 matches (parallel)
  Match 5: B vs C → Winner: C
  Match 6: F vs H → Winner: H

Finals: 2 winners → 1 match
  Match 7: C vs H → Champion: H

Total Time: 3 rounds × 2.5s = 7.5 seconds (vs 20 seconds sequential)
```

---

## Implementation Plan

### Step 1: Create Direct Test Runner

**File:** `/home/kloros/src/dream/test_runner.py`

```python
class DirectTestRunner:
    """
    Run SPICA tests directly without PHASE overhead.

    Executes pytest suite for a single instance and returns fitness.
    Much faster than PHASE's HTC approach.
    """

    def run_test(self, instance_path: Path, timeout: int = 30) -> Dict[str, Any]:
        """
        Run tests for a single SPICA instance.

        Returns:
            {
                "passed": 64,
                "failed": 0,
                "duration_ms": 2500,
                "fitness": 0.95
            }
        """
        test_dir = instance_path / "tests"

        # Run pytest directly
        result = subprocess.run(
            ["pytest", str(test_dir), "-v", "--tb=short"],
            capture_output=True,
            timeout=timeout,
            cwd=instance_path
        )

        # Parse output
        passed, failed = parse_pytest_output(result.stdout)
        pass_rate = passed / max(1, passed + failed)

        return {
            "passed": passed,
            "failed": failed,
            "pass_rate": pass_rate,
            "fitness": pass_rate,  # Simple fitness for now
            "exit_code": result.returncode
        }
```

**Advantages:**
- No PHASE overhead (epochs, slices, replicas)
- Direct pytest execution
- ~2.5 seconds per test
- Simple fitness calculation

---

### Step 2: Implement Bracket Match

**File:** `/home/kloros/src/dream/evaluators/bracket_tournament.py`

```python
class BracketMatch:
    """
    Head-to-head competition between two SPICA instances.
    """

    def __init__(self, candidate_a: str, candidate_b: str,
                 runner: DirectTestRunner):
        self.candidate_a = candidate_a
        self.candidate_b = candidate_b
        self.runner = runner

    def run(self) -> Dict[str, Any]:
        """
        Run match and declare winner.

        Returns:
            {
                "winner": "spica-abc123",
                "loser": "spica-def456",
                "score_a": 0.95,
                "score_b": 0.87,
                "margin": 0.08
            }
        """
        # Test both candidates
        result_a = self.runner.run_test(self.candidate_a)
        result_b = self.runner.run_test(self.candidate_b)

        # Determine winner
        if result_a["fitness"] > result_b["fitness"]:
            winner, loser = self.candidate_a, self.candidate_b
            score_a, score_b = result_a["fitness"], result_b["fitness"]
        else:
            winner, loser = self.candidate_b, self.candidate_a
            score_a, score_b = result_b["fitness"], result_a["fitness"]

        return {
            "winner": winner,
            "loser": loser,
            "score_winner": score_a,
            "score_loser": score_b,
            "margin": abs(score_a - score_b)
        }
```

---

### Step 3: Implement Bracket Round (Parallel Execution)

```python
class BracketRound:
    """
    Collection of matches run in parallel.
    """

    def __init__(self, matches: List[BracketMatch]):
        self.matches = matches

    def run_parallel(self, max_workers: int = 4) -> List[str]:
        """
        Run all matches in parallel, return winners.

        Returns:
            List of winner instance IDs
        """
        from concurrent.futures import ThreadPoolExecutor

        winners = []

        with ThreadPoolExecutor(max_workers=max_workers) as executor:
            # Submit all matches
            futures = [executor.submit(match.run) for match in self.matches]

            # Collect winners
            for future in futures:
                result = future.result()
                winners.append(result["winner"])

                logger.info(
                    f"Match complete: {result['winner']} defeats {result['loser']} "
                    f"({result['score_winner']:.3f} vs {result['score_loser']:.3f})"
                )

        return winners
```

**Advantages:**
- Uses ThreadPoolExecutor for parallel execution
- 4 matches × 2.5s each = 2.5 seconds total (not 10 seconds)
- Configurable parallelism

---

### Step 4: Implement Full Bracket Tournament

```python
class BracketTournament:
    """
    Complete bracket tournament orchestrator.
    """

    def __init__(self, candidates: List[str], runner: DirectTestRunner):
        self.candidates = candidates
        self.runner = runner
        self.bracket_history = []

    def run(self) -> Dict[str, Any]:
        """
        Run full bracket tournament.

        Returns:
            {
                "champion": "spica-xyz789",
                "rounds": [round1_results, round2_results, finals_results],
                "total_duration_ms": 7500
            }
        """
        import time
        start = time.time()

        current_round = self.candidates.copy()
        round_num = 1

        while len(current_round) > 1:
            logger.info(
                f"Round {round_num}: {len(current_round)} candidates → "
                f"{len(current_round)//2} matches"
            )

            # Create matches (pair up candidates)
            matches = []
            for i in range(0, len(current_round), 2):
                if i + 1 < len(current_round):
                    match = BracketMatch(
                        current_round[i],
                        current_round[i+1],
                        self.runner
                    )
                    matches.append(match)
                else:
                    # Odd number - bye to finals
                    logger.info(f"Bye: {current_round[i]} advances automatically")
                    matches.append(None)

            # Run round in parallel
            round_obj = BracketRound([m for m in matches if m is not None])
            winners = round_obj.run_parallel(max_workers=4)

            # Add bye winners
            if len(current_round) % 2 == 1:
                winners.append(current_round[-1])

            self.bracket_history.append({
                "round": round_num,
                "matches": len(matches),
                "winners": winners
            })

            current_round = winners
            round_num += 1

        duration_ms = (time.time() - start) * 1000
        champion = current_round[0]

        logger.info(
            f"Tournament complete! Champion: {champion} "
            f"(duration: {duration_ms:.0f}ms)"
        )

        return {
            "champion": champion,
            "rounds": self.bracket_history,
            "total_duration_ms": duration_ms,
            "total_matches": sum(r["matches"] for r in self.bracket_history)
        }
```

---

### Step 5: Integrate into SPICATournamentEvaluator

**Modified:** `/home/kloros/src/dream/evaluators/spica_tournament_evaluator.py`

```python
def evaluate_batch(self, candidates: List[Dict[str, Any]],
                   context: Dict[str, Any] = None) -> Tuple[List[float], Dict[str, Any]]:
    """
    Batch evaluation using bracket tournament.
    """
    if context is None:
        context = {}

    # 1) Spawn instances
    instance_paths = []
    for i, cand in enumerate(candidates):
        inst = spawn_instance(
            mutations=cand,
            parent_id=None,
            notes=f"D-REAM gen={context.get('generation', 0)} candidate={i}",
            auto_prune=False
        )
        instance_paths.append(inst)

    # 2) Run BRACKET tournament (NEW!)
    from dream.test_runner import DirectTestRunner
    from dream.evaluators.bracket_tournament import BracketTournament

    runner = DirectTestRunner()
    tournament = BracketTournament(instance_paths, runner)
    bracket_result = tournament.run()

    champion = bracket_result["champion"]

    # 3) Extract fitness scores from bracket history
    # For now, simple approach: champion gets 1.0, others get decreasing scores
    fitnesses = []
    for inst in instance_paths:
        if inst == champion:
            fitnesses.append(1.0)
        else:
            # Could extract actual scores from bracket_history
            fitnesses.append(0.5)  # Placeholder

    artifacts = {
        "bracket_tournament": bracket_result,
        "instances": instance_paths,
        "champion": champion
    }

    return fitnesses, artifacts
```

---

## Performance Comparison

### Current (Sequential PHASE)
```
8 candidates × 2.5s = 20 seconds minimum
Plus PHASE overhead = ~20 minutes total
```

### Proposed (Bracket Tournament)
```
Round 1: 4 matches in parallel = 2.5s
Round 2: 2 matches in parallel = 2.5s
Finals:  1 match            = 2.5s
Total: 7.5 seconds
```

**Speed Improvement: ~160x faster** (20 minutes → 7.5 seconds)

---

## Implementation Steps

1. ✅ Create DirectTestRunner (`/home/kloros/src/dream/test_runner.py`)
2. ✅ Create BracketMatch class
3. ✅ Create BracketRound class with parallel execution
4. ✅ Create BracketTournament orchestrator
5. ✅ Modify SPICATournamentEvaluator to use bracket tournament
6. ✅ Add configuration flag: `USE_BRACKET_TOURNAMENT=1`
7. ✅ Test with 8 SPICA instances
8. ✅ Verify winner selection is correct
9. ✅ Measure performance improvement

---

## Backward Compatibility

Keep PHASE adapter as fallback:

```python
USE_BRACKET_TOURNAMENT = os.getenv("KLR_USE_BRACKET_TOURNAMENT", "0") == "1"

if USE_BRACKET_TOURNAMENT:
    # New fast bracket tournament
    tournament = BracketTournament(instance_paths, runner)
    result = tournament.run()
else:
    # Legacy PHASE sequential (slow but battle-tested)
    tournament = submit_tournament(instances=instance_paths, ...)
```

---

## Testing Plan

1. **Unit Test:** Single BracketMatch
   - Verify winner selection
   - Check fitness calculation

2. **Integration Test:** Full BracketRound
   - Verify parallel execution
   - Check all winners advance

3. **End-to-End Test:** Complete Tournament
   - 8 candidates → 1 champion
   - Verify bracket integrity
   - Measure duration (<10 seconds)

4. **Comparison Test:** Bracket vs PHASE
   - Same 8 candidates
   - Compare champion selection
   - Compare duration (should be ~160x faster)

---

## Risks & Mitigation

### Risk 1: Parallel execution causes system overload
**Mitigation:** Configurable `max_workers`, default to 2-4

### Risk 2: Different winner than PHASE
**Mitigation:** Keep PHASE as fallback, log differences

### Risk 3: Test flakiness (timing issues)
**Mitigation:** Run each match twice if scores are close, use best-of-3

### Risk 4: Fitness calculation too simple
**Mitigation:** Extract actual test metrics from DirectTestRunner, calculate composite score

---

## Open Questions

1. **Should we run all 8 through tests first, then bracket?**
   - Pro: Get baseline fitness for all
   - Con: Takes longer (8 tests vs 7 matches)

2. **How to handle ties?**
   - Re-run match?
   - Use secondary metrics (latency)?
   - Random selection?

3. **Should losers be pruned immediately?**
   - Pro: Save disk space
   - Con: Can't analyze runner-up strategies

4. **Integrate with chemical signals?**
   - Emit match results as signals?
   - Allow async bracket execution?

---

**END OF PLAN**
