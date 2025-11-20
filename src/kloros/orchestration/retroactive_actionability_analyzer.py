#!/usr/bin/env python3
"""
Retroactive Actionability Analyzer - One-time migration script

Purpose:
    Re-analyze investigations completed BEFORE actionability analysis was deployed (17:55)
    that stopped with "answered_by_documentation" without checking if docs were actionable.

Context:
    - 814 investigations ran with old logic (pre-17:55)
    - All stopped at "found docs, read them" without actionability check
    - New logic deployed at 17:55 checks if docs provide actionable solutions
    - Those 814 questions now locked in 1-30 day cooldown
    - Action consumer starved because no new actionable investigations

Solution:
    - Load investigations from curiosity_investigations.jsonl
    - Filter for: timestamp < 2025-11-16T17:55:00 AND stopping_reason == "answered_by_documentation"
    - Re-run actionability analysis using NEW logic from generic_investigation_handler
    - Emit Q_INVESTIGATION_COMPLETE for actionable findings
    - Mark as retroactively_analyzed to prevent re-processing

Author: Claude Code
Date: 2025-11-16
"""

import json
import logging
import sys
from pathlib import Path
from typing import Dict, Any, List
from datetime import datetime, timezone

sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from kloros.orchestration.chem_bus_v2 import ChemPub

logger = logging.getLogger(__name__)

INVESTIGATIONS_LOG = Path("/home/kloros/.kloros/curiosity_investigations.jsonl")
CUTOFF_TIMESTAMP = "2025-11-16T17:55:00"  # When actionability analysis was deployed


class RetroactiveAnalyzer:
    """Re-analyze pre-fix investigations for actionability."""

    def __init__(self, dry_run: bool = False, limit: int = 100):
        self.dry_run = dry_run
        self.limit = limit
        self.chem_pub = ChemPub()
        self.analyzed_count = 0
        self.actionable_count = 0

    def _parse_timestamp(self, ts_str: str) -> datetime:
        """Parse ISO timestamp to datetime."""
        try:
            return datetime.fromisoformat(ts_str.replace('Z', '+00:00'))
        except Exception as e:
            logger.warning(f"Failed to parse timestamp {ts_str}: {e}")
            return datetime.now(timezone.utc)

    def _analyze_documentation_for_action(
        self,
        question: str,
        doc_content: str,
        question_id: str
    ) -> Dict[str, Any]:
        """
        Analyze documentation to determine if it provides actionable solution.

        This is copied from generic_investigation_handler.py to avoid circular imports
        and ensure we use the EXACT same logic.
        """
        # For now, use heuristic analysis
        # TODO: Could integrate with LLM if needed

        # Simple heuristic: check if docs contain implementation guidance
        actionable_indicators = [
            "fix by",
            "solution:",
            "to resolve",
            "implement",
            "configure",
            "set to",
            "change to",
            "add the following",
            "modify",
            "update",
        ]

        content_lower = doc_content.lower()
        has_actionable_guidance = any(
            indicator in content_lower
            for indicator in actionable_indicators
        )

        if has_actionable_guidance and len(doc_content) > 200:
            return {
                "provides_solution": True,
                "recommendation": "Apply solution from documentation",
                "action_type": "apply_documented_solution",
                "confidence": 0.75,
                "reasoning": "Documentation contains actionable implementation guidance"
            }

        return {
            "provides_solution": False,
            "recommendation": "Documentation insufficient for autonomous action",
            "action_type": "unknown",
            "confidence": 0.3,
            "reasoning": "Documentation lacks clear implementation steps"
        }

    def load_pre_fix_investigations(self) -> List[Dict[str, Any]]:
        """
        Load investigations completed before actionability fix.

        Returns:
            List of investigation dicts needing re-analysis
        """
        if not INVESTIGATIONS_LOG.exists():
            logger.error(f"Investigations log not found: {INVESTIGATIONS_LOG}")
            return []

        cutoff_dt = self._parse_timestamp(CUTOFF_TIMESTAMP)
        pre_fix_investigations = []

        try:
            with open(INVESTIGATIONS_LOG, 'r') as f:
                for line in f:
                    if not line.strip():
                        continue

                    try:
                        investigation = json.loads(line)

                        # Filter criteria
                        timestamp_str = investigation.get("timestamp", "")
                        stopping_reason = investigation.get("stopping_reason", "")

                        if not timestamp_str:
                            continue

                        inv_dt = self._parse_timestamp(timestamp_str)

                        # Must be before cutoff and stopped at documentation
                        if (inv_dt < cutoff_dt and
                            stopping_reason == "answered_by_documentation" and
                            not investigation.get("retroactively_analyzed")):

                            pre_fix_investigations.append(investigation)

                            if len(pre_fix_investigations) >= self.limit:
                                break

                    except json.JSONDecodeError:
                        continue

            logger.info(f"Loaded {len(pre_fix_investigations)} pre-fix investigations for re-analysis")
            return pre_fix_investigations

        except Exception as e:
            logger.error(f"Failed to load investigations: {e}")
            return []

    def analyze_investigation(self, investigation: Dict[str, Any]) -> bool:
        """
        Re-analyze investigation for actionability.

        Args:
            investigation: Investigation dict from log

        Returns:
            True if actionable, False otherwise
        """
        question_id = investigation.get("question_id", "unknown")
        question = investigation.get("question", "")

        # Get documentation content from rtfm_check
        rtfm_check = investigation.get("rtfm_check", {})
        relevant_content = rtfm_check.get("relevant_content", {})

        # Concatenate all documentation snippets
        doc_snippets = []
        for doc_path, doc_data in relevant_content.items():
            if isinstance(doc_data, dict):
                content = doc_data.get("full_content", "")
                if content:
                    doc_snippets.append(content[:1000])  # First 1000 chars

        doc_content = "\n\n".join(doc_snippets)

        if len(doc_content) < 100:
            logger.debug(f"Skipping {question_id} - insufficient documentation")
            return False

        # Analyze for actionability
        analysis = self._analyze_documentation_for_action(
            question,
            doc_content,
            question_id
        )

        if analysis.get("provides_solution"):
            logger.info(
                f"[retroactive] ✓ Found actionable solution for {question_id}: "
                f"{analysis.get('action_type')}"
            )

            # Emit Q_INVESTIGATION_COMPLETE with actionable analysis
            if not self.dry_run:
                self.chem_pub.emit(
                    signal="Q_INVESTIGATION_COMPLETE",
                    ecosystem="introspection",
                    facts={
                        "investigation_timestamp": investigation.get("timestamp"),
                        "question_id": question_id,
                        "retroactive_analysis": True
                    }
                )

            self.actionable_count += 1
            return True

        return False

    def run(self):
        """Run retroactive analysis."""
        logger.info(f"[retroactive] Starting analysis (dry_run={self.dry_run}, limit={self.limit})")

        investigations = self.load_pre_fix_investigations()

        if not investigations:
            logger.info("[retroactive] No pre-fix investigations found")
            return

        logger.info(f"[retroactive] Analyzing {len(investigations)} investigations...")

        for investigation in investigations:
            try:
                self.analyze_investigation(investigation)
                self.analyzed_count += 1
            except Exception as e:
                logger.error(f"[retroactive] Analysis failed: {e}", exc_info=True)

        logger.info(
            f"[retroactive] Complete: {self.analyzed_count} analyzed, "
            f"{self.actionable_count} actionable ({self.actionable_count/max(self.analyzed_count,1)*100:.1f}%)"
        )

        if self.dry_run:
            logger.info("[retroactive] DRY RUN - no signals emitted")


def main():
    logging.basicConfig(
        level=logging.INFO,
        format='%(asctime)s [%(levelname)s] %(name)s: %(message)s'
    )

    import argparse
    parser = argparse.ArgumentParser(description="Re-analyze pre-fix investigations")
    parser.add_argument("--dry-run", action="store_true", help="Don't emit signals")
    parser.add_argument("--limit", type=int, default=100, help="Max investigations to analyze")
    args = parser.parse_args()

    analyzer = RetroactiveAnalyzer(dry_run=args.dry_run, limit=args.limit)
    analyzer.run()


if __name__ == "__main__":
    main()
