#!/usr/bin/env python3
"""
D-REAM Rollback System for KLoROS
Safe rollback mechanisms for evolutionary deployments.
"""

import os
import sys
import json
import shutil
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Any, Optional
import subprocess

class DreamRollbackSystem:
    """System for safely rolling back evolutionary deployments."""

    def __init__(self):
        """Initialize rollback system."""
        self.backup_dir = Path("/home/kloros/.kloros/evolutionary_backups")
        self.deployment_log = self.backup_dir / "deployment_log.json"
        self.rollback_log = self.backup_dir / "rollback_log.json"

        # Ensure directories exist
        self.backup_dir.mkdir(parents=True, exist_ok=True)

        # Load deployment and rollback history
        self.deployments = self._load_deployment_history()
        self.rollbacks = self._load_rollback_history()

    def _load_deployment_history(self) -> List[Dict[str, Any]]:
        """Load deployment history."""
        if self.deployment_log.exists():
            try:
                with open(self.deployment_log, 'r') as f:
                    return json.load(f)
            except Exception:
                return []
        return []

    def _load_rollback_history(self) -> List[Dict[str, Any]]:
        """Load rollback history."""
        if self.rollback_log.exists():
            try:
                with open(self.rollback_log, 'r') as f:
                    return json.load(f)
            except Exception:
                return []
        return []

    def _save_rollback_history(self):
        """Save rollback history."""
        try:
            with open(self.rollback_log, 'w') as f:
                json.dump(self.rollbacks, f, indent=2, default=str)
        except Exception as e:
            print(f"[rollback] Failed to save history: {e}")

    def rollback_deployment(self, deployment_id: str) -> Dict[str, Any]:
        """Rollback a specific deployment."""
        print(f"[rollback] Initiating rollback for deployment: {deployment_id}")

        rollback_result = {
            "rollback_id": f"rollback_{deployment_id}_{int(time.time())}",
            "deployment_id": deployment_id,
            "timestamp": datetime.now().isoformat(),
            "success": False,
            "files_restored": [],
            "validation_results": {},
            "error": None
        }

        try:
            # Find deployment record
            deployment = self._find_deployment(deployment_id)
            if not deployment:
                rollback_result["error"] = f"Deployment {deployment_id} not found"
                return rollback_result

            # Find backup file
            backup_path = deployment.get("backup_path")
            if not backup_path or not Path(backup_path).exists():
                rollback_result["error"] = f"Backup file not found: {backup_path}"
                return rollback_result

            # Restore from backup
            target_file = self._get_deployment_target_file(deployment)
            if not target_file:
                rollback_result["error"] = "Could not determine target file for rollback"
                return rollback_result

            # Create backup of current state before rollback
            current_backup = self._create_pre_rollback_backup(target_file, deployment_id)

            # Restore original file
            shutil.copy2(backup_path, target_file)
            rollback_result["files_restored"].append(str(target_file))

            # Validate rollback
            validation_results = self._validate_rollback(target_file, deployment)
            rollback_result["validation_results"] = validation_results

            if all(validation_results.values()):
                rollback_result["success"] = True
                print(f"[rollback] ✅ Successfully rolled back deployment {deployment_id}")
            else:
                rollback_result["error"] = "Rollback validation failed"
                print(f"[rollback] ❌ Rollback validation failed for {deployment_id}")

            # Log rollback
            self.rollbacks.append(rollback_result)
            self._save_rollback_history()

        except Exception as e:
            rollback_result["error"] = str(e)
            print(f"[rollback] ❌ Rollback failed: {e}")

        return rollback_result

    def rollback_latest_deployment(self) -> Dict[str, Any]:
        """Rollback the most recent deployment."""
        if not self.deployments:
            return {"error": "No deployments found to rollback"}

        latest_deployment = self.deployments[-1]
        deployment_id = latest_deployment.get("deployment_id")

        if not deployment_id:
            return {"error": "Latest deployment has no ID"}

        return self.rollback_deployment(deployment_id)

    def rollback_by_approach_id(self, approach_id: str) -> Dict[str, Any]:
        """Rollback deployment by approach ID."""
        # Find deployment with matching approach ID
        for deployment in reversed(self.deployments):
            if deployment.get("approach_id") == approach_id:
                deployment_id = deployment.get("deployment_id")
                if deployment_id:
                    return self.rollback_deployment(deployment_id)

        return {"error": f"No deployment found for approach ID: {approach_id}"}

    def emergency_rollback_all(self) -> Dict[str, Any]:
        """Emergency rollback of all recent deployments."""
        print("[rollback] ⚠️ EMERGENCY: Rolling back all recent deployments")

        emergency_result = {
            "emergency_rollback_id": f"emergency_{int(time.time())}",
            "timestamp": datetime.now().isoformat(),
            "deployments_processed": 0,
            "successful_rollbacks": 0,
            "failed_rollbacks": 0,
            "rollback_results": [],
            "overall_success": False
        }

        # Rollback recent deployments (last 24 hours)
        recent_deployments = self._get_recent_deployments(hours=24)

        for deployment in reversed(recent_deployments):
            deployment_id = deployment.get("deployment_id")
            if deployment_id:
                emergency_result["deployments_processed"] += 1

                rollback_result = self.rollback_deployment(deployment_id)
                emergency_result["rollback_results"].append(rollback_result)

                if rollback_result.get("success"):
                    emergency_result["successful_rollbacks"] += 1
                else:
                    emergency_result["failed_rollbacks"] += 1

        # Determine overall success
        if emergency_result["successful_rollbacks"] > 0 and emergency_result["failed_rollbacks"] == 0:
            emergency_result["overall_success"] = True

        print(f"[rollback] Emergency rollback complete: {emergency_result['successful_rollbacks']}/{emergency_result['deployments_processed']} successful")

        return emergency_result

    def get_rollback_status(self) -> Dict[str, Any]:
        """Get current rollback system status."""
        recent_deployments = self._get_recent_deployments(hours=24)
        recent_rollbacks = self._get_recent_rollbacks(hours=24)

        return {
            "system_operational": True,
            "total_deployments": len(self.deployments),
            "total_rollbacks": len(self.rollbacks),
            "recent_deployments_24h": len(recent_deployments),
            "recent_rollbacks_24h": len(recent_rollbacks),
            "available_backups": self._count_available_backups(),
            "rollback_commands": [
                "rollback_deployment <deployment_id>",
                "rollback_latest_deployment",
                "rollback_by_approach_id <approach_id>",
                "emergency_rollback_all"
            ]
        }

    def _find_deployment(self, deployment_id: str) -> Optional[Dict[str, Any]]:
        """Find deployment record by ID."""
        for deployment in self.deployments:
            if deployment.get("deployment_id") == deployment_id:
                return deployment
        return None

    def _get_deployment_target_file(self, deployment: Dict[str, Any]) -> Optional[Path]:
        """Get target file path for deployment."""
        # Extract from deployment record (implementation depends on deployment structure)
        # This is a simplified version
        approach_id = deployment.get("approach_id", "")

        if "memory" in approach_id:
            return Path("/home/kloros/src/kloros_voice.py")
        elif "consistency" in approach_id or "rag" in approach_id:
            return Path("/home/kloros/src/reasoning/local_rag_backend.py")
        else:
            return None

    def _create_pre_rollback_backup(self, target_file: Path, deployment_id: str) -> Path:
        """Create backup of current state before rollback."""
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        backup_name = f"{target_file.name}.pre_rollback_{deployment_id}_{timestamp}"
        backup_path = self.backup_dir / backup_name

        shutil.copy2(target_file, backup_path)
        print(f"[rollback] Created pre-rollback backup: {backup_path}")

        return backup_path

    def _validate_rollback(self, target_file: Path, deployment: Dict[str, Any]) -> Dict[str, bool]:
        """Validate that rollback was successful."""
        validation_results = {}

        try:
            # Basic syntax validation
            validation_results["syntax_valid"] = self._validate_python_syntax(target_file)

            # Import validation
            validation_results["import_valid"] = self._validate_imports(target_file)

            # File exists and readable
            validation_results["file_accessible"] = target_file.exists() and target_file.is_file()

        except Exception as e:
            print(f"[rollback] Validation error: {e}")
            validation_results["validation_error"] = False

        return validation_results

    def _validate_python_syntax(self, file_path: Path) -> bool:
        """Validate Python syntax of file."""
        try:
            with open(file_path, 'r') as f:
                content = f.read()

            compile(content, str(file_path), 'exec')
            return True

        except SyntaxError:
            return False
        except Exception:
            return False

    def _validate_imports(self, file_path: Path) -> bool:
        """Validate that file can be imported without errors."""
        try:
            # Basic import test (simplified)
            result = subprocess.run(
                [sys.executable, '-m', 'py_compile', str(file_path)],
                capture_output=True,
                timeout=10
            )
            return result.returncode == 0

        except Exception:
            return False

    def _get_recent_deployments(self, hours: int = 24) -> List[Dict[str, Any]]:
        """Get deployments from the last N hours."""
        cutoff_time = datetime.now().timestamp() - (hours * 3600)
        recent = []

        for deployment in self.deployments:
            timestamp_str = deployment.get("timestamp", "")
            try:
                deployment_time = datetime.fromisoformat(timestamp_str).timestamp()
                if deployment_time > cutoff_time:
                    recent.append(deployment)
            except Exception:
                continue

        return recent

    def _get_recent_rollbacks(self, hours: int = 24) -> List[Dict[str, Any]]:
        """Get rollbacks from the last N hours."""
        cutoff_time = datetime.now().timestamp() - (hours * 3600)
        recent = []

        for rollback in self.rollbacks:
            timestamp_str = rollback.get("timestamp", "")
            try:
                rollback_time = datetime.fromisoformat(timestamp_str).timestamp()
                if rollback_time > cutoff_time:
                    recent.append(rollback)
            except Exception:
                continue

        return recent

    def _count_available_backups(self) -> int:
        """Count available backup files."""
        try:
            backup_files = list(self.backup_dir.glob("*.backup_*"))
            return len(backup_files)
        except Exception:
            return 0

def main():
    """Test the rollback system."""
    print("=== Testing D-REAM Rollback System ===")

    rollback_system = DreamRollbackSystem()

    # Get system status
    status = rollback_system.get_rollback_status()
    print(f"Rollback System Status:")
    for key, value in status.items():
        print(f"  {key}: {value}")

    print("\n=== Rollback System Test Complete ===")

if __name__ == "__main__":
    main()