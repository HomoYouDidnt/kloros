#!/usr/bin/env python3
"""
Improvement Proposer - Identifies and proposes improvements to KLoROS.

This module analyzes system telemetry, error logs, and performance metrics
to identify opportunities for improvement and submits them to D-REAM for
evolutionary optimization.
"""

import json
import logging
import hashlib
import psutil
from typing import Dict, List, Optional, Tuple
from datetime import datetime, timedelta
from pathlib import Path
from dataclasses import dataclass, asdict

logger = logging.getLogger(__name__)


@dataclass
class ImprovementProposal:
    """Represents a proposed improvement to KLoROS."""
    id: str
    timestamp: str
    component: str  # e.g., "tool_synthesis", "reasoning", "audio"
    issue_type: str  # e.g., "performance", "reliability", "quality"
    description: str
    evidence: Dict  # Metrics, logs, or other supporting data
    priority: str  # "low", "medium", "high", "critical"
    proposed_change: Optional[str] = None
    target_files: Optional[List[str]] = None
    status: str = "proposed"  # "proposed", "submitted", "in_progress", "validated", "deployed", "rejected"
    # Deduplication fields
    proposal_hash: Optional[str] = None  # Unique hash for deduplication
    first_seen: Optional[str] = None  # When first observed
    last_seen: Optional[str] = None  # When last observed
    occurrence_count: int = 1  # How many times we've seen this issue
    enriched_at: Optional[str] = None  # When proposal was enriched with solutions


class ImprovementProposer:
    """Analyzes KLoROS telemetry and proposes improvements."""

    def __init__(self):
        """Initialize improvement proposer."""
        self.proposals_dir = Path("/home/kloros/var/dream/proposals")
        self.proposals_dir.mkdir(parents=True, exist_ok=True)

        self.proposals_file = self.proposals_dir / "improvement_proposals.jsonl"
        self.telemetry_dir = Path("/home/kloros/.kloros")
        self.dream_ledger = Path("/home/kloros/var/dream/ledger.jsonl")

        # In-memory cache of active proposals for deduplication
        self._active_proposals_cache: Optional[Dict[str, ImprovementProposal]] = None

    def analyze_system_health(self) -> List[ImprovementProposal]:
        """Analyze system health and generate improvement proposals."""
        proposals = []

        # Analyze system resource health (swap, memory, processes)
        proposals.extend(self._analyze_system_resources())

        # Analyze D-REAM results
        proposals.extend(self._analyze_dream_failures())

        # Analyze tool synthesis failures
        proposals.extend(self._analyze_tool_synthesis_failures())

        # Analyze reasoning quality
        proposals.extend(self._analyze_reasoning_quality())

        return proposals

    def _analyze_system_resources(self) -> List[ImprovementProposal]:
        """Analyze system resource health (swap, memory, stuck processes)."""
        proposals = []

        try:
            mem = psutil.virtual_memory()
            swap = psutil.swap_memory()

            # Check swap exhaustion
            if swap.percent >= 70:
                severity = "critical" if swap.percent >= 90 else "high"
                proposal = ImprovementProposal(
                    id=f"system_swap_exhaustion_{int(datetime.now().timestamp())}",
                    timestamp=datetime.now().isoformat(),
                    component="system",
                    issue_type="performance",
                    description=f"Swap usage at {swap.percent:.1f}% ({swap.used / (1024**3):.2f}GB used)",
                    evidence={
                        "swap_percent": swap.percent,
                        "swap_used_gb": swap.used / (1024**3),
                        "memory_available_gb": mem.available / (1024**3),
                        "memory_percent": mem.percent
                    },
                    priority=severity,
                    target_files=["/home/kloros/src/kloros_voice.py"],
                    proposed_change="Investigate memory leak or excessive memory usage patterns"
                )
                proposals.append(proposal)

            # Check low memory
            if mem.available < 2 * (1024**3):  # Less than 2GB available
                proposal = ImprovementProposal(
                    id=f"system_low_memory_{int(datetime.now().timestamp())}",
                    timestamp=datetime.now().isoformat(),
                    component="system",
                    issue_type="performance",
                    description=f"Low memory: {mem.available / (1024**3):.2f}GB available ({mem.percent:.1f}% used)",
                    evidence={
                        "memory_available_gb": mem.available / (1024**3),
                        "memory_percent": mem.percent,
                        "swap_percent": swap.percent
                    },
                    priority="high",
                    target_files=["/home/kloros/src/kloros_voice.py"],
                    proposed_change="Optimize memory usage or reduce concurrent operations"
                )
                proposals.append(proposal)

            # Check stuck processes
            stuck_processes = []
            for proc in psutil.process_iter(['pid', 'name', 'status', 'cmdline']):
                try:
                    if proc.info['status'] == psutil.STATUS_DISK_SLEEP:
                        stuck_processes.append({
                            "pid": proc.info['pid'],
                            "name": proc.info['name'],
                            "cmdline": ' '.join(proc.info['cmdline'] or [])
                        })
                except (psutil.NoSuchProcess, psutil.AccessDenied):
                    continue

            if len(stuck_processes) > 3:
                proposal = ImprovementProposal(
                    id=f"system_stuck_processes_{int(datetime.now().timestamp())}",
                    timestamp=datetime.now().isoformat(),
                    component="system",
                    issue_type="reliability",
                    description=f"Found {len(stuck_processes)} processes stuck in D state",
                    evidence={
                        "stuck_count": len(stuck_processes),
                        "sample_processes": stuck_processes[:5]
                    },
                    priority="high",
                    proposed_change="Investigate IO bottlenecks or deadlocks causing D-state processes"
                )
                proposals.append(proposal)

            # Check duplicate kloros_voice processes
            kloros_procs = []
            for proc in psutil.process_iter(['pid', 'name', 'cmdline', 'create_time']):
                try:
                    cmdline = ' '.join(proc.info['cmdline'] or [])
                    if 'kloros_voice' in cmdline:
                        kloros_procs.append(proc)
                except (psutil.NoSuchProcess, psutil.AccessDenied):
                    continue

            if len(kloros_procs) > 1:
                proposal = ImprovementProposal(
                    id=f"system_duplicate_process_{int(datetime.now().timestamp())}",
                    timestamp=datetime.now().isoformat(),
                    component="system",
                    issue_type="reliability",
                    description=f"Found {len(kloros_procs)} kloros_voice processes running",
                    evidence={
                        "process_count": len(kloros_procs),
                        "pids": [p.pid for p in kloros_procs]
                    },
                    priority="high",
                    proposed_change="Investigate why multiple instances are running and implement process lock"
                )
                proposals.append(proposal)

        except Exception as e:
            logger.error(f"Failed to analyze system resources: {e}")

        return proposals

    def _analyze_dream_failures(self) -> List[ImprovementProposal]:
        """Analyze D-REAM ledger for repeated failures."""
        proposals = []

        if not self.dream_ledger.exists():
            return proposals

        try:
            # Read recent D-REAM runs
            runs = []
            with open(self.dream_ledger, 'r') as f:
                for line in f:
                    if line.strip():
                        runs.append(json.loads(line))

            # Analyze failures by family
            family_failures = {}
            for run in runs[-100:]:  # Last 100 runs
                if not run.get("passed", False):
                    family = run.get("family", "unknown")
                    if family not in family_failures:
                        family_failures[family] = []
                    family_failures[family].append(run)

            # Create proposals for families with high failure rates
            for family, failures in family_failures.items():
                if len(failures) >= 3:  # 3+ failures
                    proposal = ImprovementProposal(
                        id=f"dream_failure_{family}_{int(datetime.now().timestamp())}",
                        timestamp=datetime.now().isoformat(),
                        component="dream",
                        issue_type="reliability",
                        description=f"D-REAM family '{family}' has {len(failures)} failures in recent runs",
                        evidence={
                            "failure_count": len(failures),
                            "family": family,
                            "sample_failures": failures[:3],
                            "common_errors": self._extract_common_errors(failures)
                        },
                        priority="high" if len(failures) >= 5 else "medium"
                    )
                    proposals.append(proposal)

        except Exception as e:
            logger.error(f"Failed to analyze D-REAM failures: {e}")

        return proposals

    def _analyze_tool_synthesis_failures(self) -> List[ImprovementProposal]:
        """Analyze tool synthesis log for failures."""
        proposals = []

        synthesis_log = self.telemetry_dir / "tool_synthesis.log"
        if not synthesis_log.exists():
            return proposals

        try:
            # Read recent synthesis attempts
            attempts = []
            with open(synthesis_log, 'r') as f:
                for line in f:
                    if line.strip():
                        attempts.append(json.loads(line))

            # Analyze recent failures
            recent_cutoff = datetime.now() - timedelta(hours=24)
            recent_failures = [
                a for a in attempts
                if "validation_failed" in a.get("status", "") or "error" in a.get("status", "")
                and datetime.fromisoformat(a["timestamp"]) > recent_cutoff
            ]

            if len(recent_failures) >= 3:
                proposal = ImprovementProposal(
                    id=f"tool_synthesis_failures_{int(datetime.now().timestamp())}",
                    timestamp=datetime.now().isoformat(),
                    component="tool_synthesis",
                    issue_type="reliability",
                    description=f"Tool synthesis has {len(recent_failures)} failures in last 24 hours",
                    evidence={
                        "failure_count": len(recent_failures),
                        "sample_failures": recent_failures[:5],
                        "common_errors": self._extract_synthesis_errors(recent_failures)
                    },
                    priority="high" if len(recent_failures) >= 10 else "medium",
                    target_files=[
                        "/home/kloros/src/tool_synthesis/synthesizer.py",
                        "/home/kloros/src/tool_synthesis/validator.py"
                    ]
                )
                proposals.append(proposal)

        except Exception as e:
            logger.error(f"Failed to analyze tool synthesis failures: {e}")

        return proposals

    def _analyze_reasoning_quality(self) -> List[ImprovementProposal]:
        """Analyze reasoning quality metrics."""
        # Placeholder for reasoning quality analysis
        # In production, this would analyze conversation logs,
        # user satisfaction metrics, hallucination rates, etc.
        return []

    def _extract_common_errors(self, failures: List[Dict]) -> Dict[str, int]:
        """Extract common error patterns from failures."""
        errors = {}
        for failure in failures:
            metrics = failure.get("metrics", {})

            # Count error types
            if not metrics.get("edit_applied", True):
                errors["edit_not_applied"] = errors.get("edit_not_applied", 0) + 1

            # Add other error pattern detection here

        return errors

    def _extract_synthesis_errors(self, failures: List[Dict]) -> Dict[str, int]:
        """Extract common error patterns from synthesis failures."""
        errors = {}
        for failure in failures:
            status = failure.get("status", "")

            if "validation_failed" in status:
                errors["validation_failed"] = errors.get("validation_failed", 0) + 1
            elif "error" in status:
                errors["generic_error"] = errors.get("generic_error", 0) + 1
            elif "quarantined" in status:
                errors["quarantined"] = errors.get("quarantined", 0) + 1

        return errors

    def _compute_proposal_hash(self, proposal: ImprovementProposal) -> str:
        """Compute unique hash for proposal deduplication.

        Hash is based on component, issue_type, and description pattern
        (not exact description to allow for dynamic counts/timestamps).
        """
        # Extract description pattern (remove dynamic numbers)
        import re
        desc_pattern = re.sub(r'\d+', 'N', proposal.description)

        hash_input = f"{proposal.component}:{proposal.issue_type}:{desc_pattern}"
        return hashlib.sha256(hash_input.encode()).hexdigest()[:16]

    def _load_active_proposals(self) -> Dict[str, ImprovementProposal]:
        """Load active proposals into memory cache for deduplication."""
        if self._active_proposals_cache is not None:
            return self._active_proposals_cache

        cache = {}
        if not self.proposals_file.exists():
            self._active_proposals_cache = cache
            return cache

        try:
            with open(self.proposals_file, 'r') as f:
                for line in f:
                    if not line.strip():
                        continue
                    data = json.loads(line)
                    proposal = ImprovementProposal(**data)

                    # Only cache active proposals (not resolved/rejected)
                    if proposal.status in ["proposed", "submitted", "in_progress"]:
                        if proposal.proposal_hash:
                            cache[proposal.proposal_hash] = proposal

        except Exception as e:
            logger.error(f"Failed to load active proposals: {e}")

        self._active_proposals_cache = cache
        return cache

    def _update_existing_proposal(self, existing: ImprovementProposal, new: ImprovementProposal) -> ImprovementProposal:
        """Update existing proposal with new occurrence data."""
        existing.last_seen = new.timestamp
        existing.occurrence_count += 1
        existing.evidence = new.evidence  # Update with latest evidence
        existing.priority = new.priority  # Update priority if it changed
        return existing

    def _rewrite_proposals_file(self, proposals: Dict[str, ImprovementProposal]):
        """Rewrite proposals file with deduplicated data."""
        try:
            # Write to temp file first
            temp_file = self.proposals_file.with_suffix('.tmp')
            with open(temp_file, 'w') as f:
                for proposal in proposals.values():
                    f.write(json.dumps(asdict(proposal)) + '\n')

            # Atomic replace
            temp_file.replace(self.proposals_file)
            logger.info(f"Rewrote proposals file with {len(proposals)} unique proposals")

        except Exception as e:
            logger.error(f"Failed to rewrite proposals file: {e}")
            raise

    def submit_proposal(self, proposal: ImprovementProposal) -> bool:
        """Submit an improvement proposal with deduplication."""
        try:
            # Compute hash for deduplication
            proposal.proposal_hash = self._compute_proposal_hash(proposal)

            # Set first_seen if not already set
            if not proposal.first_seen:
                proposal.first_seen = proposal.timestamp
            proposal.last_seen = proposal.timestamp

            # Load active proposals cache
            active_proposals = self._load_active_proposals()

            # Check if this proposal already exists
            if proposal.proposal_hash in active_proposals:
                existing = active_proposals[proposal.proposal_hash]
                updated = self._update_existing_proposal(existing, proposal)
                active_proposals[proposal.proposal_hash] = updated

                # Rewrite file with updated data
                self._rewrite_proposals_file(active_proposals)

                logger.info(f"Updated existing proposal {proposal.proposal_hash} "
                          f"(occurrence #{updated.occurrence_count})")
                return True
            else:
                # New proposal - add to cache and append to file
                active_proposals[proposal.proposal_hash] = proposal

                with open(self.proposals_file, 'a') as f:
                    f.write(json.dumps(asdict(proposal)) + '\n')

                logger.info(f"Submitted new improvement proposal: {proposal.id}")
                return True

        except Exception as e:
            logger.error(f"Failed to submit proposal: {e}")
            return False

    def get_pending_proposals(self, component: Optional[str] = None,
                             priority: Optional[str] = None) -> List[ImprovementProposal]:
        """Get pending improvement proposals."""
        if not self.proposals_file.exists():
            return []

        proposals = []
        try:
            with open(self.proposals_file, 'r') as f:
                for line in f:
                    if line.strip():
                        data = json.loads(line)
                        proposal = ImprovementProposal(**data)

                        # Filter by component if specified
                        if component and proposal.component != component:
                            continue

                        # Filter by priority if specified
                        if priority and proposal.priority != priority:
                            continue

                        # Only return pending/submitted proposals
                        if proposal.status in ["proposed", "submitted"]:
                            proposals.append(proposal)

            return proposals

        except Exception as e:
            logger.error(f"Failed to read proposals: {e}")
            return []

    def run_analysis_cycle(self) -> int:
        """Run a complete analysis cycle and submit proposals."""
        logger.info("Starting improvement analysis cycle")

        proposals = self.analyze_system_health()

        submitted = 0
        for proposal in proposals:
            if self.submit_proposal(proposal):
                submitted += 1

        logger.info(f"Analysis complete: {submitted} proposals submitted")
        return submitted


# Singleton instance
_proposer_instance = None

def get_improvement_proposer() -> ImprovementProposer:
    """Get singleton proposer instance."""
    global _proposer_instance
    if _proposer_instance is None:
        _proposer_instance = ImprovementProposer()
    return _proposer_instance
