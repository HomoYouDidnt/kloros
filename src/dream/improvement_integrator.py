#!/usr/bin/env python3
"""
Improvement Integrator - Deploys validated improvements from D-REAM to KLoROS.

This module takes validated improvements from D-REAM evolution runs and
safely integrates them into the live KLoROS system with rollback capabilities.

Uses D-REAM's no-git snapshot/diff system for all version control.
"""

import json
import logging
import shutil
import subprocess
import sys
from typing import Dict, List, Optional, Tuple
from datetime import datetime
from pathlib import Path
from dataclasses import dataclass, asdict

# Import D-REAM snapshot system
sys.path.insert(0, '/home/kloros')
from src.dream.runtime.workspace import snapshot_create, snapshot_restore, diff_report, enforce_allowlist, ARTS

logger = logging.getLogger(__name__)


@dataclass
class IntegrationRecord:
    """Record of an improvement integration."""
    id: str
    timestamp: str
    proposal_id: str
    component: str
    files_modified: List[str]
    backup_path: str
    validation_status: str  # "pending", "passed", "failed"
    deployment_status: str  # "pending", "deployed", "rolled_back"
    test_results: Dict
    rollback_available: bool


class ImprovementIntegrator:
    """Integrates validated improvements from D-REAM into KLoROS."""

    def __init__(self):
        """Initialize improvement integrator."""
        self.integration_dir = Path("/home/kloros/var/dream/integrations")
        self.integration_dir.mkdir(parents=True, exist_ok=True)

        self.backups_dir = self.integration_dir / "backups"
        self.backups_dir.mkdir(parents=True, exist_ok=True)

        self.integration_log = self.integration_dir / "integration_history.jsonl"
        self.dream_workspace = Path("/home/kloros/work")

    def validate_improvement(self, run_id: str, component: str) -> Tuple[bool, Dict]:
        """
        Validate an improvement from a D-REAM run.

        Args:
            run_id: D-REAM run ID
            component: Component name (e.g., "tool_synthesis")

        Returns:
            (success, test_results)
        """
        try:
            # Find workspace for this run
            workspace_dir = self.dream_workspace / run_id
            if not workspace_dir.exists():
                logger.error(f"Workspace not found for run {run_id}")
                return False, {"error": "workspace_not_found"}

            # Run validation tests
            test_results = self._run_validation_tests(workspace_dir, component)

            # Check if all tests passed
            all_passed = all(
                result.get("status") == "passed"
                for result in test_results.values()
            )

            return all_passed, test_results

        except Exception as e:
            logger.error(f"Validation failed for {run_id}: {e}")
            return False, {"error": str(e)}

    def _run_validation_tests(self, workspace_dir: Path, component: str) -> Dict:
        """Run validation tests on improved code."""
        results = {}

        # Unit tests
        results["unit_tests"] = self._run_pytest(workspace_dir, f"tests/unit/test_{component}.py")

        # Integration tests
        results["integration_tests"] = self._run_pytest(workspace_dir, f"tests/integration/test_{component}_integration.py")

        # Syntax check
        results["syntax_check"] = self._check_python_syntax(workspace_dir)

        # Import check
        results["import_check"] = self._check_imports(workspace_dir, component)

        return results

    def _run_pytest(self, workspace_dir: Path, test_path: str) -> Dict:
        """Run pytest on specific test file."""
        full_test_path = workspace_dir / test_path

        if not full_test_path.exists():
            return {"status": "skipped", "reason": "test_not_found"}

        try:
            result = subprocess.run(
                ["/home/kloros/.venv/bin/pytest", str(full_test_path), "-v"],
                cwd=workspace_dir,
                capture_output=True,
                text=True,
                timeout=60
            )

            return {
                "status": "passed" if result.returncode == 0 else "failed",
                "returncode": result.returncode,
                "stdout": result.stdout,
                "stderr": result.stderr
            }

        except subprocess.TimeoutExpired:
            return {"status": "failed", "reason": "timeout"}
        except Exception as e:
            return {"status": "failed", "error": str(e)}

    def _check_python_syntax(self, workspace_dir: Path) -> Dict:
        """Check Python syntax for all .py files."""
        try:
            result = subprocess.run(
                ["python3", "-m", "py_compile"] + [
                    str(f) for f in workspace_dir.rglob("*.py")
                    if "/.venv/" not in str(f) and "/__pycache__/" not in str(f)
                ],
                capture_output=True,
                text=True,
                timeout=30
            )

            return {
                "status": "passed" if result.returncode == 0 else "failed",
                "errors": result.stderr if result.returncode != 0 else None
            }

        except Exception as e:
            return {"status": "failed", "error": str(e)}

    def _check_imports(self, workspace_dir: Path, component: str) -> Dict:
        """Check that improved component can be imported."""
        try:
            # Try to import the component module
            result = subprocess.run(
                [
                    "python3", "-c",
                    f"import sys; sys.path.insert(0, '{workspace_dir}'); import src.{component}"
                ],
                capture_output=True,
                text=True,
                timeout=10
            )

            return {
                "status": "passed" if result.returncode == 0 else "failed",
                "error": result.stderr if result.returncode != 0 else None
            }

        except Exception as e:
            return {"status": "failed", "error": str(e)}

    def create_backup(self, label: str = "integration") -> Optional[str]:
        """
        Create snapshot backup using D-REAM snapshot system.

        Args:
            label: Label for the snapshot

        Returns:
            Snapshot ID, or None on failure
        """
        try:
            snapshot_id = snapshot_create(label=label)
            logger.info(f"Created snapshot: {snapshot_id}")
            return snapshot_id

        except Exception as e:
            logger.error(f"Failed to create snapshot: {e}")
            return None

    def integrate_improvement(self, run_id: str, proposal_id: str,
                            component: str, files: List[str]) -> Optional[IntegrationRecord]:
        """
        Integrate validated improvement into KLoROS using D-REAM snapshot system.

        Args:
            run_id: D-REAM run ID
            proposal_id: Improvement proposal ID
            component: Component name
            files: List of files to update

        Returns:
            IntegrationRecord if successful, None otherwise
        """
        snapshot_id = None
        try:
            # Create snapshot (no-git backup)
            snapshot_id = self.create_backup(label=f"integration_{component}")
            if not snapshot_id:
                logger.error("Failed to create snapshot, aborting integration")
                return None

            # Validate improvement
            validation_passed, test_results = self.validate_improvement(run_id, component)

            if not validation_passed:
                logger.warning(f"Validation failed for {run_id}, not deploying")
                snapshot_restore(snapshot_id)
                return self._create_integration_record(
                    proposal_id, component, files, snapshot_id,
                    "failed", "pending", test_results, True
                )

            # Check allowlist before deployment
            if not enforce_allowlist(files):
                logger.error(f"Files outside allowlist: {files}")
                snapshot_restore(snapshot_id)
                return None

            # Copy improved files
            workspace_dir = self.dream_workspace / run_id
            deployment_success = self._deploy_files(workspace_dir, files)

            if not deployment_success:
                logger.error("Deployment failed, rolling back")
                snapshot_restore(snapshot_id)
                return None

            # Generate diff report
            diff_rep = diff_report(snapshot_id)

            # Create integration record
            record = self._create_integration_record(
                proposal_id, component, files, snapshot_id,
                "passed", "deployed", test_results, True
            )

            # Log integration
            self._log_integration(record)

            logger.info(f"Successfully integrated improvement: {record.id}")
            return record

        except Exception as e:
            logger.error(f"Integration failed: {e}")
            # Automatic rollback on any failure
            if snapshot_id:
                snapshot_restore(snapshot_id)
            return None

    def _deploy_files(self, workspace_dir: Path, files: List[str]) -> bool:
        """Deploy improved files to KLoROS."""
        try:
            for file_path in files:
                src = workspace_dir / Path(file_path).relative_to("/home/kloros")
                dest = Path(file_path)

                if src.exists():
                    dest.parent.mkdir(parents=True, exist_ok=True)
                    shutil.copy2(src, dest)
                    logger.info(f"Deployed: {file_path}")
                else:
                    logger.warning(f"Source file not found: {src}")

            return True

        except Exception as e:
            logger.error(f"Deployment failed: {e}")
            return False

    def rollback(self, snapshot_id: str) -> bool:
        """
        Rollback to snapshot using D-REAM snapshot system.

        Args:
            snapshot_id: Snapshot ID to restore

        Returns:
            True if successful
        """
        try:
            snapshot_restore(snapshot_id)
            logger.info(f"Rollback complete from snapshot: {snapshot_id}")
            return True

        except Exception as e:
            logger.error(f"Rollback failed: {e}")
            return False

    def _create_integration_record(self, proposal_id: str, component: str,
                                   files: List[str], backup_path: str,
                                   validation_status: str, deployment_status: str,
                                   test_results: Dict, rollback_available: bool) -> IntegrationRecord:
        """Create integration record."""
        return IntegrationRecord(
            id=f"integration_{int(datetime.now().timestamp())}",
            timestamp=datetime.now().isoformat(),
            proposal_id=proposal_id,
            component=component,
            files_modified=files,
            backup_path=backup_path,
            validation_status=validation_status,
            deployment_status=deployment_status,
            test_results=test_results,
            rollback_available=rollback_available
        )

    def _log_integration(self, record: IntegrationRecord):
        """Log integration record."""
        try:
            with open(self.integration_log, 'a') as f:
                f.write(json.dumps(asdict(record)) + '\n')
        except Exception as e:
            logger.error(f"Failed to log integration: {e}")

    def get_integration_history(self, component: Optional[str] = None,
                               limit: int = 100) -> List[IntegrationRecord]:
        """Get integration history."""
        if not self.integration_log.exists():
            return []

        records = []
        try:
            with open(self.integration_log, 'r') as f:
                for line in f:
                    if line.strip():
                        data = json.loads(line)
                        record = IntegrationRecord(**data)

                        if component and record.component != component:
                            continue

                        records.append(record)

            # Return most recent first
            return records[-limit:][::-1]

        except Exception as e:
            logger.error(f"Failed to read integration history: {e}")
            return []


# Singleton instance
_integrator_instance = None

def get_improvement_integrator() -> ImprovementIntegrator:
    """Get singleton integrator instance."""
    global _integrator_instance
    if _integrator_instance is None:
        _integrator_instance = ImprovementIntegrator()
    return _integrator_instance
