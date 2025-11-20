#!/usr/bin/env python3
"""
Proposal-to-Candidate Bridge - Converts ImprovementProposals to D-REAM Candidates

This module bridges the gap between the ImprovementProposer system (which detects
runtime issues) and the D-REAM candidate admission pipeline.
"""

import json
import logging
import uuid
from typing import List, Dict, Any
from datetime import datetime
from pathlib import Path

logger = logging.getLogger(__name__)


class ProposalToCandidateBridge:
    """Convert improvement proposals to D-REAM candidates."""

    def __init__(self):
        """Initialize bridge."""
        self.candidates_dir = Path("/home/kloros/src/dream/phase_raw")
        self.candidates_dir.mkdir(parents=True, exist_ok=True)

        self.bridge_log = Path("/home/kloros/var/dream/proposal_bridge.log")
        self.bridge_log.parent.mkdir(parents=True, exist_ok=True)

    def convert_proposal_to_candidate(self, proposal: Dict[str, Any]) -> Dict[str, Any]:
        """
        Convert an ImprovementProposal to a D-REAM Candidate.

        Args:
            proposal: ImprovementProposal dict with keys:
                - id, timestamp, component, issue_type, description,
                  evidence, priority, proposed_change, target_files, status

        Returns:
            Candidate dict for D-REAM admission
        """
        # Map proposal to candidate format
        candidate = {
            "id": proposal.get("id", str(uuid.uuid4())[:8]),
            "domain": self._map_component_to_domain(proposal.get("component", "system")),
            "params": self._extract_params_from_proposal(proposal),
            "metrics": self._compute_metrics_from_evidence(proposal),
            "notes": proposal.get("description", "")
        }

        return candidate

    def _map_component_to_domain(self, component: str) -> str:
        """Map component name to D-REAM domain."""
        mapping = {
            "tool_synthesis": "tool_synthesis",
            "dream": "code_repair",
            "reasoning": "llm_consistency",
            "audio": "conversation_quality",
            "memory": "memory_integration",
            "rag": "rag_quality",
            "asr": "asr_accuracy",
            "system": "code_repair"
        }
        return mapping.get(component, "code_repair")

    def _extract_params_from_proposal(self, proposal: Dict[str, Any]) -> Dict[str, Any]:
        """Extract parameters from proposal evidence."""
        params = {
            "issue_type": proposal.get("issue_type", "unknown"),
            "priority": proposal.get("priority", "medium"),
            "proposed_change": proposal.get("proposed_change", ""),
            "target_files": proposal.get("target_files", [])
        }

        # Add evidence metadata
        evidence = proposal.get("evidence", {})
        if isinstance(evidence, dict):
            params["failure_count"] = evidence.get("failure_count", 0)
            params["family"] = evidence.get("family", "unknown")
            params["common_errors"] = evidence.get("common_errors", {})

        return params

    def _compute_metrics_from_evidence(self, proposal: Dict[str, Any]) -> Dict[str, Any]:
        """Compute metrics from proposal evidence for D-REAM scoring."""
        evidence = proposal.get("evidence", {})

        # Priority score mapping
        priority_scores = {
            "critical": 1.0,
            "high": 0.8,
            "medium": 0.6,
            "low": 0.4
        }

        priority = proposal.get("priority", "medium")
        base_score = priority_scores.get(priority, 0.5)

        # Compute novelty based on failure patterns
        failure_count = 0
        if isinstance(evidence, dict):
            failure_count = evidence.get("failure_count", 0)

        # Higher failure count = more urgent, but not necessarily novel
        novelty = min(0.3 + (failure_count * 0.1), 1.0)

        metrics = {
            "score": base_score,
            "novelty": novelty,
            "latency_ms": 0.0,  # Not applicable for proposals
            "holdout_ok": True,  # Proposals don't have holdout tests yet
            "wer": 0.0,  # Not applicable for non-audio proposals
            "failure_count": failure_count
        }

        return metrics

    def submit_proposals_as_candidates(self, proposals: List[Dict[str, Any]]) -> int:
        """
        Convert proposals to candidates and submit to D-REAM queue.

        Args:
            proposals: List of ImprovementProposal dicts

        Returns:
            Number of candidates successfully submitted
        """
        if not proposals:
            return 0

        submitted = 0
        episode_id = f"improvement_proposals_{int(datetime.now().timestamp())}"
        candidate_file = self.candidates_dir / f"{episode_id}.jsonl"

        try:
            with open(candidate_file, 'w') as f:
                for proposal in proposals:
                    # Convert to candidate
                    candidate = self.convert_proposal_to_candidate(proposal)

                    # Write to candidates file
                    f.write(json.dumps(candidate) + '\n')
                    submitted += 1

            # Log bridge activity
            self._log_bridge_activity(episode_id, len(proposals), submitted)

            logger.info(f"Submitted {submitted} proposals as D-REAM candidates in episode {episode_id}")
            return submitted

        except Exception as e:
            logger.error(f"Failed to submit proposals as candidates: {e}")
            return 0

    def _log_bridge_activity(self, episode_id: str, total: int, submitted: int):
        """Log bridge activity."""
        try:
            log_entry = {
                "timestamp": datetime.now().isoformat(),
                "episode_id": episode_id,
                "total_proposals": total,
                "submitted_candidates": submitted,
                "status": "success" if submitted == total else "partial"
            }

            with open(self.bridge_log, 'a') as f:
                f.write(json.dumps(log_entry) + '\n')

        except Exception as e:
            logger.error(f"Failed to log bridge activity: {e}")


# Singleton instance
_bridge_instance = None

def get_proposal_bridge():
    """Get singleton bridge instance."""
    global _bridge_instance
    if _bridge_instance is None:
        _bridge_instance = ProposalToCandidateBridge()
    return _bridge_instance
