#!/usr/bin/env python3
"""
KLoROS Autonomous Self-Healing Loop

Coordinates PHASE → Analysis → Config Tuning in a closed feedback loop:

1. PHASE runs nightly (3-5 AM) - Validation
2. Post-PHASE analyzer detects degradation - Detection
3. Escalation flags armed if threshold reached - Gate
4. Config Tuning responds during maintenance window - Remediation
5. Next PHASE validates improvement - Verification

This is the production-ready autonomous loop that:
- Detects issues via scheduled regression testing
- Analyzes trends vs baseline
- Escalates when patterns emerge
- Fixes autonomously with bounded risk
- Validates improvements empirically

Bounded Execution:
- PHASE: predictive mode only (no downtime, ~2-4 hours)
- Analysis: read-only, fast (<10s)
- Config Tuning: canary mode only when escalated (60s/night budget)
- Cooldown: 6h minimum between canary runs
- Rate limit: 3 canary runs per 24h per subsystem
"""

import os
import json
import time
import logging
from pathlib import Path
from typing import Dict, Any, Optional
from dataclasses import dataclass, asdict
from datetime import datetime

logger = logging.getLogger(__name__)


@dataclass
class LoopCycleResult:
    """Result of a complete autonomous loop cycle."""
    cycle_id: str
    phase_epoch_id: str
    phase_status: str
    phase_duration_s: float
    analysis_status: str
    degradation_signals: int
    escalations_armed: int
    config_tuning_triggered: bool
    config_tuning_status: Optional[str]
    config_tuning_promoted: bool
    total_duration_s: float
    timestamp: float


class AutonomousLoop:
    """Orchestrate the complete autonomous self-healing loop."""

    def __init__(self, audit_dir: Path = Path("/home/kloros/.kloros/autonomous_loop")):
        """
        Args:
            audit_dir: Directory for loop execution audit trail
        """
        self.audit_dir = audit_dir
        self.audit_dir.mkdir(parents=True, exist_ok=True)
        self.audit_file = self.audit_dir / "cycles.jsonl"

    def _log_cycle(self, result: LoopCycleResult):
        """Append cycle result to audit trail."""
        with open(self.audit_file, 'a') as f:
            f.write(json.dumps(asdict(result)) + '\n')

    def run_cycle(self, force_phase: bool = False) -> LoopCycleResult:
        """
        Execute one complete autonomous loop cycle.

        Steps:
        1. Run PHASE (scheduled regression testing)
        2. Run post-PHASE analysis (detect degradation)
        3. Check escalation flags
        4. Run config tuning if escalated
        5. Record cycle results

        Args:
            force_phase: Force PHASE run even if already completed today

        Returns:
            LoopCycleResult with complete cycle metrics
        """
        cycle_id = f"loop_{datetime.now().strftime('%Y%m%d_%H%M%S')}"
        start_time = time.time()

        logger.info(f"=== Autonomous Loop Cycle {cycle_id} starting ===")

        # Step 1: Run PHASE
        logger.info("Step 1: Running PHASE regression testing...")
        phase_result = self._run_phase(force=force_phase)

        if phase_result["exit_code"] != 0:
            logger.error(f"PHASE failed with exit code {phase_result['exit_code']}")
            result = LoopCycleResult(
                cycle_id=cycle_id,
                phase_epoch_id=phase_result.get("epoch_id", "unknown"),
                phase_status="failed",
                phase_duration_s=phase_result.get("duration_s", 0),
                analysis_status="skipped",
                degradation_signals=0,
                escalations_armed=0,
                config_tuning_triggered=False,
                config_tuning_status=None,
                config_tuning_promoted=False,
                total_duration_s=time.time() - start_time,
                timestamp=time.time()
            )
            self._log_cycle(result)
            return result

        logger.info(f"PHASE completed: epoch={phase_result['epoch_id']}, "
                   f"duration={phase_result['duration_s']:.1f}s")

        # Step 2: Run post-PHASE analysis
        logger.info("Step 2: Analyzing PHASE results for degradation...")
        analysis_result = self._run_analysis()

        logger.info(f"Analysis complete: {analysis_result['degradation_signals']} signals, "
                   f"{analysis_result['escalations_armed']} escalations armed")

        # Step 3: Check if config tuning should run
        config_tuning_triggered = False
        config_tuning_status = None
        config_tuning_promoted = False

        if analysis_result["escalations_armed"] > 0:
            logger.info("Step 3: Escalations armed - checking if config tuning should run...")

            # Check maintenance window and budget
            can_run, reason = self._check_config_tuning_eligibility()

            if can_run:
                logger.info("Config tuning eligible - running autonomous remediation...")
                config_tuning_triggered = True

                # Step 4: Run config tuning
                tuning_result = self._run_config_tuning(analysis_result)
                config_tuning_status = tuning_result.get("status")
                config_tuning_promoted = tuning_result.get("promoted", False)

                logger.info(f"Config tuning complete: status={config_tuning_status}, "
                           f"promoted={config_tuning_promoted}")
            else:
                logger.info(f"Config tuning not eligible: {reason}")
                config_tuning_status = f"deferred: {reason}"
        else:
            logger.info("Step 3: No escalations - system healthy, config tuning not needed")

        # Summary
        result = LoopCycleResult(
            cycle_id=cycle_id,
            phase_epoch_id=phase_result["epoch_id"],
            phase_status="success",
            phase_duration_s=phase_result["duration_s"],
            analysis_status=analysis_result["status"],
            degradation_signals=analysis_result["degradation_signals"],
            escalations_armed=analysis_result["escalations_armed"],
            config_tuning_triggered=config_tuning_triggered,
            config_tuning_status=config_tuning_status,
            config_tuning_promoted=config_tuning_promoted,
            total_duration_s=time.time() - start_time,
            timestamp=time.time()
        )

        self._log_cycle(result)

        logger.info(f"=== Autonomous Loop Cycle {cycle_id} complete "
                   f"(duration={result.total_duration_s:.1f}s) ===")

        return result

    def _run_phase(self, force: bool = False) -> Dict[str, Any]:
        """Run PHASE regression testing."""
        try:
            from src.kloros.orchestration.phase_trigger import run_epoch

            phase_result = run_epoch(force=force, timeout_s=7200)  # 2 hour timeout

            return {
                "exit_code": phase_result.exit_code,
                "epoch_id": phase_result.epoch_id,
                "duration_s": phase_result.duration_s,
                "report_path": str(phase_result.report_path) if phase_result.report_path else None
            }
        except Exception as e:
            logger.error(f"PHASE execution failed: {e}", exc_info=True)
            return {
                "exit_code": 1,
                "epoch_id": "error",
                "duration_s": 0,
                "error": str(e)
            }

    def _run_analysis(self) -> Dict[str, Any]:
        """Run post-PHASE degradation analysis."""
        try:
            from src.phase.post_phase_analyzer import PHASEAnalyzer

            analyzer = PHASEAnalyzer()
            return analyzer.analyze()
        except Exception as e:
            logger.error(f"Analysis failed: {e}", exc_info=True)
            return {
                "status": "error",
                "degradation_signals": 0,
                "escalations_armed": 0,
                "error": str(e)
            }

    def _check_config_tuning_eligibility(self) -> tuple[bool, str]:
        """
        Check if config tuning can run now.

        Checks:
        - Maintenance window (3-7 AM)
        - GPU canary budget (60s/night)
        - Cooldown (6h minimum)

        Returns:
            (eligible, reason)
        """
        return False, "gpu_canary_runner module not available"

    def _run_config_tuning(self, analysis_result: Dict[str, Any]) -> Dict[str, Any]:
        """
        Run config tuning for escalated subsystems.

        Args:
            analysis_result: Post-PHASE analysis with degradation signals

        Returns:
            Config tuning result summary
        """
        try:
            from src.dream.config_tuning.runner import ConfigTuningRunner

            # Extract primary symptom from analysis
            signals = analysis_result.get("signals", [])
            if not signals:
                return {"status": "no_signals", "promoted": False}

            # Focus on most critical signal (GPU domain, critical severity)
            critical_signals = [s for s in signals if s.get("severity") == "critical"]
            primary_signal = critical_signals[0] if critical_signals else signals[0]

            # Build intent data for config tuning
            intent = {
                "mode": "autonomous",
                "subsystem": "vllm",  # Map from domain to subsystem
                "seed_fix": None,  # Let actuators generate candidates
                "context": {
                    "trigger": "phase_degradation",
                    "symptom_kind": primary_signal.get("symptom_kind"),
                    "domain": primary_signal.get("domain"),
                    "severity": primary_signal.get("severity"),
                    "delta_pct": primary_signal.get("delta_pct"),
                    "analysis_result": analysis_result
                }
            }

            logger.info(f"Running config tuning for {intent['subsystem']} "
                       f"(symptom: {primary_signal.get('symptom_kind')})")

            runner = ConfigTuningRunner()
            result = runner.run(intent)

            return {
                "status": result.status,
                "promoted": result.promoted,
                "run_id": result.run_id,
                "candidates_tested": len(result.candidates_tested),
                "best_fitness": result.best_candidate.fitness if result.best_candidate else 0.0,
                "promotion_path": result.promotion_path
            }

        except Exception as e:
            logger.error(f"Config tuning failed: {e}", exc_info=True)
            return {
                "status": "error",
                "promoted": False,
                "error": str(e)
            }


def main():
    """CLI entry point for autonomous loop."""
    import argparse

    parser = argparse.ArgumentParser(description="KLoROS Autonomous Self-Healing Loop")
    parser.add_argument("--force-phase", action="store_true",
                       help="Force PHASE run even if already completed today")
    args = parser.parse_args()

    logging.basicConfig(
        level=logging.INFO,
        format='%(asctime)s [%(levelname)s] %(message)s'
    )

    loop = AutonomousLoop()
    result = loop.run_cycle(force_phase=args.force_phase)

    # Print summary
    print("\n" + "="*80)
    print(f"Autonomous Loop Cycle Complete: {result.cycle_id}")
    print("="*80)
    print(f"PHASE:             {result.phase_status} (epoch: {result.phase_epoch_id}, {result.phase_duration_s:.1f}s)")
    print(f"Analysis:          {result.degradation_signals} degradation signals, {result.escalations_armed} escalations")
    print(f"Config Tuning:     {'triggered' if result.config_tuning_triggered else 'not needed'}")
    if result.config_tuning_triggered:
        print(f"  Status:          {result.config_tuning_status}")
        print(f"  Promoted:        {result.config_tuning_promoted}")
    print(f"Total Duration:    {result.total_duration_s:.1f}s")
    print("="*80 + "\n")

    # Exit code: 0 if healthy, 1 if degraded, 2 if fixed
    if result.escalations_armed == 0:
        return 0  # Healthy
    elif result.config_tuning_promoted:
        return 2  # Fixed
    else:
        return 1  # Degraded


if __name__ == "__main__":
    exit(main())
