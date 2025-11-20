#!/usr/bin/env python3
"""
Active Proposal Helper - Allows KLoROS to create improvement proposals during active thinking.

This module provides a simple interface for KLoROS to submit improvement proposals
during her reasoning/introspection, not just during passive idle cycles.
"""

import logging
import uuid
from typing import Dict, Any, Optional, List
from datetime import datetime
from dataclasses import asdict

logger = logging.getLogger(__name__)


class ActiveProposalHelper:
    """Helper for KLoROS to actively submit improvement proposals."""

    def __init__(self):
        """Initialize active proposal helper."""
        try:
            import sys
            sys.path.insert(0, '/home/kloros')
            from src.dream.improvement_proposer import get_improvement_proposer, ImprovementProposal
            from src.dream.proposal_to_candidate_bridge import get_proposal_bridge

            self.proposer = get_improvement_proposer()
            self.bridge = get_proposal_bridge()
            self.ImprovementProposal = ImprovementProposal
            self.enabled = True

        except Exception as e:
            logger.error(f"Failed to initialize active proposal helper: {e}")
            self.enabled = False

    def submit_improvement_idea(
        self,
        component: str,
        issue_type: str,
        description: str,
        priority: str = "medium",
        evidence: Optional[Dict[str, Any]] = None,
        proposed_change: Optional[str] = None,
        target_files: Optional[List[str]] = None
    ) -> bool:
        """
        Submit an improvement proposal during active reasoning.

        Args:
            component: Component name (e.g., "tool_synthesis", "reasoning", "memory")
            issue_type: Issue type (e.g., "performance", "reliability", "quality")
            description: Description of the issue and proposed improvement
            priority: Priority level ("low", "medium", "high", "critical")
            evidence: Supporting evidence (metrics, examples, patterns)
            proposed_change: Specific change to implement
            target_files: Files that should be modified

        Returns:
            True if submitted successfully

        Example:
            helper.submit_improvement_idea(
                component="tool_synthesis",
                issue_type="reliability",
                description="Tool validation is too strict, rejecting valid tools",
                priority="high",
                evidence={"recent_rejections": 5, "pattern": "syntax_false_positives"},
                proposed_change="Relax syntax validation for edge cases",
                target_files=["/home/kloros/src/tool_synthesis/validator.py"]
            )
        """
        if not self.enabled:
            logger.warning("Active proposal helper not enabled")
            return False

        try:
            # Create proposal
            proposal = self.ImprovementProposal(
                id=f"active_{component}_{int(datetime.now().timestamp())}",
                timestamp=datetime.now().isoformat(),
                component=component,
                issue_type=issue_type,
                description=description,
                evidence=evidence or {},
                priority=priority,
                proposed_change=proposed_change,
                target_files=target_files,
                status="proposed"
            )

            # Submit to proposer queue
            submitted = self.proposer.submit_proposal(proposal)

            if submitted:
                # Also convert to candidate immediately for fast-track
                candidate_submitted = self.bridge.submit_proposals_as_candidates([asdict(proposal)])

                logger.info(
                    f"Active proposal submitted: {component}/{issue_type} (priority: {priority}, "
                    f"candidate: {candidate_submitted > 0})"
                )

                return True
            else:
                logger.error("Failed to submit active proposal")
                return False

        except Exception as e:
            logger.error(f"Failed to submit improvement idea: {e}")
            return False

    def submit_quick_fix_idea(self, description: str, target_file: Optional[str] = None) -> bool:
        """
        Quick method to submit a simple fix idea.

        Args:
            description: What should be improved
            target_file: File that should be changed (optional)

        Returns:
            True if submitted successfully

        Example:
            helper.submit_quick_fix_idea(
                "The RAG context window is too small, causing truncation",
                "/home/kloros/src/rag/config.py"
            )
        """
        return self.submit_improvement_idea(
            component="code_repair",
            issue_type="enhancement",
            description=description,
            priority="medium",
            evidence={"source": "active_reasoning"},
            target_files=[target_file] if target_file else None
        )

    def submit_performance_concern(
        self,
        component: str,
        metric_name: str,
        current_value: float,
        target_value: float,
        description: str
    ) -> bool:
        """
        Submit a performance-related improvement proposal.

        Args:
            component: Component with performance issue
            metric_name: Name of the performance metric
            current_value: Current metric value
            target_value: Desired metric value
            description: Description of the performance issue

        Returns:
            True if submitted successfully

        Example:
            helper.submit_performance_concern(
                component="rag",
                metric_name="retrieval_latency_ms",
                current_value=500.0,
                target_value=100.0,
                description="RAG retrieval is too slow, blocking conversations"
            )
        """
        return self.submit_improvement_idea(
            component=component,
            issue_type="performance",
            description=description,
            priority="high",
            evidence={
                "metric_name": metric_name,
                "current_value": current_value,
                "target_value": target_value,
                "gap": abs(current_value - target_value)
            }
        )


# Singleton instance
_helper_instance = None

def get_active_proposal_helper() -> ActiveProposalHelper:
    """Get singleton helper instance."""
    global _helper_instance
    if _helper_instance is None:
        _helper_instance = ActiveProposalHelper()
    return _helper_instance
