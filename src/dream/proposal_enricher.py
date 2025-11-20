#!/usr/bin/env python3
"""
Proposal Enricher - The missing link that generates solutions for improvement proposals.

This module takes problem-only proposals from ImprovementProposer and enriches them
with concrete solutions using KLoROS's existing multi-layer reasoning (ToT/Debate).

Architectural Note:
    This should have been part of the original system. Proposals without solutions
    cannot be auto-deployed, creating a bottleneck. This enricher closes that gap.
"""

import json
import logging
from typing import Dict, Any, Optional, List
from datetime import datetime
from pathlib import Path
from dataclasses import asdict

logger = logging.getLogger(__name__)


class ProposalEnricher:
    """
    Enriches improvement proposals with concrete solutions using deep reasoning.

    Purpose:
        Bridge the gap between problem identification (ImprovementProposer)
        and solution implementation (auto-deployment)

    Flow:
        1. Load proposals with null proposed_change
        2. Use invoke_deep_reasoning (ToT/Debate) to analyze problem
        3. Generate concrete solution with target files
        4. Enrich proposal with proposed_change and target_files
        5. Mark as ready for D-REAM validation
    """

    def __init__(self, kloros_instance=None):
        """
        Initialize proposal enricher.

        Args:
            kloros_instance: KLoROS instance for LLM access (optional)
        """
        self.kloros = kloros_instance
        self.proposals_dir = Path("/home/kloros/var/dream/proposals")
        self.proposals_file = self.proposals_dir / "improvement_proposals.jsonl"

    def enrich_pending_proposals(self, max_proposals: int = 3) -> int:
        """
        Enrich pending proposals that lack solutions.

        Args:
            max_proposals: Maximum number to enrich per cycle (rate limiting)

        Returns:
            Number of proposals enriched
        """
        if not self.proposals_file.exists():
            logger.info("[proposal_enricher] No proposals file found")
            return 0

        try:
            from src.dream.improvement_proposer import ImprovementProposal, get_improvement_proposer

            # Load proposals needing enrichment
            proposals_to_enrich = []

            with open(self.proposals_file, 'r') as f:
                for line in f:
                    if not line.strip():
                        continue
                    data = json.loads(line)  # Load as dict

                    # Only enrich proposals that:
                    # 1. Are in "proposed" or "submitted" status
                    # 2. Have no proposed_change yet
                    # 3. Have high priority
                    if (data.get('status') in ['proposed', 'submitted'] and
                        not data.get('proposed_change') and
                        data.get('priority') in ['high', 'critical']):
                        proposals_to_enrich.append(data)

            if not proposals_to_enrich:
                logger.info("[proposal_enricher] No proposals need enrichment")
                return 0

            # Limit to max_proposals per cycle
            proposals_to_enrich = proposals_to_enrich[:max_proposals]

            logger.info(f"[proposal_enricher] Enriching {len(proposals_to_enrich)} proposals...")

            enriched_count = 0
            proposer = get_improvement_proposer()

            for proposal_data in proposals_to_enrich:
                try:
                    # Generate solution using deep reasoning
                    solution = self._generate_solution(proposal_data)

                    if solution:
                        # Update proposal with solution
                        proposal_data['proposed_change'] = solution['change_description']
                        proposal_data['target_files'] = solution['target_files']
                        proposal_data['status'] = 'solution_generated'
                        proposal_data['enriched_at'] = datetime.now().isoformat()

                        # Save updated proposal
                        self._update_proposal_in_file(proposal_data)

                        enriched_count += 1
                        logger.info(f"[proposal_enricher] ✓ Enriched {proposal_data['id']}")
                    else:
                        logger.warning(f"[proposal_enricher] Failed to generate solution for {proposal_data['id']}")

                except Exception as e:
                    logger.error(f"[proposal_enricher] Error enriching {proposal_data.get('id')}: {e}")
                    continue

            logger.info(f"[proposal_enricher] Enriched {enriched_count}/{len(proposals_to_enrich)} proposals")
            return enriched_count

        except Exception as e:
            logger.error(f"[proposal_enricher] Failed to enrich proposals: {e}")
            return 0

    def _generate_solution(self, proposal: Dict[str, Any]) -> Optional[Dict[str, str]]:
        """
        Generate concrete solution for a proposal using deep reasoning.

        Args:
            proposal: Proposal dict with component, issue_type, description, evidence

        Returns:
            Dict with change_description and target_files, or None if failed
        """
        try:
            # Build problem statement for deep reasoning
            problem = self._build_problem_statement(proposal)

            # Use invoke_deep_reasoning if available
            if self.kloros and hasattr(self.kloros, 'invoke_deep_reasoning'):
                logger.info(f"[proposal_enricher] Using KLoROS deep reasoning for {proposal['id']}")
                result = self.kloros.invoke_deep_reasoning(
                    problem=problem,
                    method='tot',  # Tree of Thought for solution exploration
                    context=str(proposal.get('evidence', {}))
                )

                # Parse result to extract solution
                return self._parse_reasoning_result(result, proposal)

            # Fallback: Use introspection tool directly
            else:
                logger.info(f"[proposal_enricher] Using introspection tool for {proposal['id']}")
                from src.introspection_tools import IntrospectionToolRegistry

                registry = IntrospectionToolRegistry()
                if 'invoke_deep_reasoning' in registry.tools:
                    result = registry.tools['invoke_deep_reasoning'].func(
                        self.kloros,
                        problem=problem,
                        method='tot',
                        context=str(proposal.get('evidence', {}))
                    )

                    return self._parse_reasoning_result(result, proposal)

            # Last resort: Generate heuristic solution
            logger.warning(f"[proposal_enricher] Deep reasoning unavailable, using heuristics")
            return self._generate_heuristic_solution(proposal)

        except Exception as e:
            logger.error(f"[proposal_enricher] Solution generation failed: {e}")
            return None

    def _build_problem_statement(self, proposal: Dict[str, Any]) -> str:
        """Build comprehensive problem statement for reasoning."""
        component = proposal.get('component', 'unknown')
        issue_type = proposal.get('issue_type', 'unknown')
        description = proposal.get('description', '')
        evidence = proposal.get('evidence', {})

        problem = f"""Problem: {description}

Component: {component}
Issue Type: {issue_type}
Priority: {proposal.get('priority', 'medium')}

Evidence:
"""

        # Format evidence
        if isinstance(evidence, dict):
            for key, value in evidence.items():
                problem += f"  - {key}: {value}\n"
        else:
            problem += f"  {evidence}\n"

        problem += "\nTask: Generate a concrete solution with specific code changes and target files."

        return problem

    def _parse_reasoning_result(self, result: str, proposal: Dict[str, Any]) -> Optional[Dict[str, str]]:
        """
        Parse deep reasoning result to extract solution.

        Args:
            result: Raw result from invoke_deep_reasoning
            proposal: Original proposal

        Returns:
            Dict with change_description and target_files
        """
        try:
            # Extract solution from reasoning result
            # This is a simplified parser - in production, use structured output

            lines = result.split('\n')
            solution_lines = []
            capture = False

            for line in lines:
                # Look for solution indicators
                if any(keyword in line.lower() for keyword in ['solution', 'fix', 'implement', 'change']):
                    capture = True

                if capture and line.strip():
                    solution_lines.append(line.strip())

            change_description = ' '.join(solution_lines[:10])  # First 10 lines

            # Infer target files from proposal or reasoning output
            target_files = proposal.get('target_files', [])

            if not target_files:
                # Infer from component
                component = proposal.get('component', '')
                if component == 'tool_synthesis':
                    target_files = [
                        "/home/kloros/src/tool_synthesis/synthesizer.py",
                        "/home/kloros/src/tool_synthesis/validator.py"
                    ]
                elif component == 'dream':
                    target_files = [
                        "/home/kloros/src/dream/runner.py"
                    ]
                elif 'self_healing' in component:
                    target = proposal.get('evidence', {}).get('target', '')
                    if 'rag' in target:
                        target_files = ["/home/kloros/src/reasoning/local_rag_backend.py"]
                    elif 'tts' in target:
                        target_files = ["/home/kloros/src/tts/base.py"]

            if change_description:
                return {
                    'change_description': change_description,
                    'target_files': target_files
                }

            return None

        except Exception as e:
            logger.error(f"[proposal_enricher] Failed to parse reasoning result: {e}")
            return None

    def _generate_heuristic_solution(self, proposal: Dict[str, Any]) -> Optional[Dict[str, str]]:
        """
        Generate heuristic solution when deep reasoning unavailable.

        Args:
            proposal: Proposal dict

        Returns:
            Dict with change_description and target_files
        """
        component = proposal.get('component', '')
        issue_type = proposal.get('issue_type', '')
        description = proposal.get('description', '')

        # Pattern-based heuristics
        if 'failure' in description.lower() and 'timeout' in description.lower():
            change = "Increase timeout thresholds and add retry logic with exponential backoff"
        elif 'reliability' in issue_type and 'validation' in description.lower():
            change = "Relax validation constraints and add better error messages"
        elif 'performance' in issue_type:
            change = "Add caching layer and optimize hot paths identified in evidence"
        else:
            change = f"Investigate and fix root cause of {issue_type} issue in {component}"

        # Infer target files
        target_files = proposal.get('target_files', [])
        if not target_files and component:
            target_files = [f"/home/kloros/src/{component}/main.py"]

        return {
            'change_description': change,
            'target_files': target_files
        }

    def _update_proposal_in_file(self, updated_proposal: Dict[str, Any]):
        """
        Update a proposal in the proposals file.

        Args:
            updated_proposal: Updated proposal dict with proposal_hash for matching
        """
        try:
            import json

            # Read all proposals
            proposals = []
            with open(self.proposals_file, 'r') as f:
                for line in f:
                    if line.strip():
                        proposals.append(json.loads(line))

            # Find and update matching proposal
            updated = False
            for i, p in enumerate(proposals):
                if p.get('proposal_hash') == updated_proposal.get('proposal_hash'):
                    proposals[i] = updated_proposal
                    updated = True
                    break

            if not updated:
                # Append if not found
                proposals.append(updated_proposal)

            # Rewrite file
            with open(self.proposals_file, 'w') as f:
                for p in proposals:
                    f.write(json.dumps(p) + '\n')

        except Exception as e:
            logger.error(f"[proposal_enricher] Failed to update proposal in file: {e}")
            raise


# Singleton instance
_enricher_instance = None

def get_proposal_enricher(kloros_instance=None):
    """Get singleton enricher instance."""
    global _enricher_instance
    if _enricher_instance is None:
        _enricher_instance = ProposalEnricher(kloros_instance)
    return _enricher_instance
