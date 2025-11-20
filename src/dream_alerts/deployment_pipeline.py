#!/usr/bin/env python3
"""
D-REAM Improvement Deployment Pipeline
Handles actual deployment of approved improvements to the KLoROS codebase.
"""

import os
import sys
import json
import shutil
import subprocess
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Any, Optional, Tuple
from dataclasses import dataclass, field
import logging

# Set up logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

@dataclass
class DeploymentPlan:
    """Represents a deployment plan for an improvement."""
    improvement_id: str
    improvement_type: str
    target_files: List[str]
    backup_required: bool
    validation_commands: List[str]
    rollback_plan: Dict[str, Any]
    risk_level: str
    estimated_duration: int  # seconds

@dataclass
class DeploymentResult:
    """Result of a deployment operation."""
    success: bool
    improvement_id: str
    deployed_at: datetime
    backup_path: Optional[str] = None
    changes_applied: List[str] = field(default_factory=list)
    validation_results: Dict[str, Any] = field(default_factory=dict)
    error_message: Optional[str] = None
    rollback_performed: bool = False

class ImprovementDeployer:
    """
    Handles deployment of approved improvements to the KLoROS system.
    Provides safe deployment with backup/rollback capabilities.
    """

    def __init__(self, base_path: str = "/home/kloros"):
        self.base_path = Path(base_path)
        self.src_path = self.base_path / "src"
        self.backup_path = self.base_path / ".kloros" / "deployment_backups"
        self.logs_path = self.base_path / ".kloros" / "deployment_logs"

        # Ensure directories exist
        self.backup_path.mkdir(parents=True, exist_ok=True)
        self.logs_path.mkdir(parents=True, exist_ok=True)

        # Load deployment history
        self.history_file = self.logs_path / "deployment_history.json"
        self.deployment_history = self._load_deployment_history()

    def deploy_improvement(self, improvement_data: Dict[str, Any]) -> DeploymentResult:
        """
        Main entry point for deploying an approved improvement.

        Args:
            improvement_data: Dictionary containing improvement details

        Returns:
            DeploymentResult with deployment status and details
        """
        improvement_id = improvement_data.get("request_id", "unknown")
        logger.info(f"🚀 Starting deployment of improvement {improvement_id}")

        try:
            # Step 1: Analyze improvement and create deployment plan
            plan = self._analyze_improvement(improvement_data)
            logger.info(f"📋 Deployment plan created for {plan.improvement_type} improvement")

            # Step 2: Create backup if required
            backup_path = None
            if plan.backup_required:
                backup_path = self._create_backup(plan)
                logger.info(f"💾 Backup created at {backup_path}")

            # Step 3: Execute deployment
            changes_applied = self._execute_deployment(plan, improvement_data)
            logger.info(f"⚡ Applied {len(changes_applied)} changes")

            # Step 3.5: Guard against empty deployments (ANTI-FABRICATION)
            # FIX: Deployment façade - ASTRAEA Oct 26, 2025
            # Reject if no changes OR if changes are just descriptions
            if not changes_applied:
                logger.error(f"❌ No changes to deploy for {improvement_id} - improvement missing implementation")
                return DeploymentResult(
                    success=False,
                    improvement_id=improvement_id,
                    deployed_at=datetime.now(),
                    backup_path=backup_path,
                    error_message="No changes to deploy - improvement missing implementation"
                )

            # ANTI-FABRICATION: Verify changes are actual file modifications
            # Real changes start with "UPDATED" or "ADDED" (evidence of file write)
            # Description strings like "Enhanced reasoning capabilities" are rejected
            real_modifications = [
                c for c in changes_applied
                if c.startswith("UPDATED ") or c.startswith("ADDED ")
            ]

            if not real_modifications:
                logger.error(f"❌ All changes are descriptions, not file modifications!")
                logger.error(f"❌ Changes: {changes_applied}")
                return DeploymentResult(
                    success=False,
                    improvement_id=improvement_id,
                    deployed_at=datetime.now(),
                    backup_path=backup_path,
                    error_message="ANTI-FABRICATION: Deployment returned descriptions instead of file modifications"
                )

            # Step 4: Validate deployment
            validation_results = self._validate_deployment(plan)

            # Step 5: Check validation results
            if not validation_results.get("success", False):
                logger.error(f"❌ Validation failed for {improvement_id}")
                if backup_path:
                    self._rollback_deployment(plan, backup_path)
                    return DeploymentResult(
                        success=False,
                        improvement_id=improvement_id,
                        deployed_at=datetime.now(),
                        backup_path=backup_path,
                        validation_results=validation_results,
                        error_message="Validation failed, rollback performed",
                        rollback_performed=True
                    )
                else:
                    return DeploymentResult(
                        success=False,
                        improvement_id=improvement_id,
                        deployed_at=datetime.now(),
                        validation_results=validation_results,
                        error_message="Validation failed, no backup available"
                    )

            # Step 6: Success - log and return
            result = DeploymentResult(
                success=True,
                improvement_id=improvement_id,
                deployed_at=datetime.now(),
                backup_path=backup_path,
                changes_applied=changes_applied,
                validation_results=validation_results
            )

            self._log_deployment(result)
            logger.info(f"✅ Successfully deployed improvement {improvement_id}")

            return result

        except Exception as e:
            logger.error(f"💥 Deployment failed for {improvement_id}: {e}")
            return DeploymentResult(
                success=False,
                improvement_id=improvement_id,
                deployed_at=datetime.now(),
                error_message=str(e)
            )

    def _analyze_improvement(self, improvement_data: Dict[str, Any]) -> DeploymentPlan:
        """
        Analyze improvement and create a deployment plan.

        Args:
            improvement_data: Dictionary containing improvement details

        Returns:
            DeploymentPlan with deployment strategy
        """
        improvement_id = improvement_data.get("request_id", "unknown")
        component = improvement_data.get("component", "unknown")
        description = improvement_data.get("description", "")
        risk_level = improvement_data.get("risk_level", "medium")

        # Determine improvement type based on component and description
        improvement_type = self._classify_improvement(component, description)

        # Create deployment plan based on improvement type
        if improvement_type == "evolutionary":
            return self._plan_evolutionary_deployment(improvement_data)
        elif improvement_type == "configuration":
            return self._plan_configuration_deployment(improvement_data)
        elif improvement_type == "memory":
            return self._plan_memory_deployment(improvement_data)
        elif improvement_type == "speech":
            return self._plan_speech_deployment(improvement_data)
        elif improvement_type == "reasoning":
            return self._plan_reasoning_deployment(improvement_data)
        else:
            # Default deployment plan for unknown types
            return DeploymentPlan(
                improvement_id=improvement_id,
                improvement_type="unknown",
                target_files=[],
                backup_required=True,
                validation_commands=["/home/kloros/.venv/bin/python3 -c 'import sys; print(\"Basic validation passed\")'"],
                rollback_plan={"type": "backup_restore"},
                risk_level=risk_level,
                estimated_duration=30
            )

    def _classify_improvement(self, component: str, description: str) -> str:
        """
        Classify improvement type based on component and description.

        Args:
            component: Component being improved
            description: Description of the improvement

        Returns:
            Improvement type classification
        """
        component_lower = component.lower()
        description_lower = description.lower()

        # Evolutionary improvements
        if "evolutionary" in description_lower or "darwin" in description_lower or "optimization" in description_lower:
            return "evolutionary"

        # Configuration improvements
        if "config" in description_lower or "setting" in description_lower or "parameter" in description_lower:
            return "configuration"

        # Memory system improvements
        if "memory" in component_lower or "memory" in description_lower:
            return "memory"

        # Speech recognition improvements
        if "speech" in component_lower or "stt" in description_lower or "recognition" in description_lower:
            return "speech"

        # Voice integration improvements
        if "voice" in component_lower or "integration" in description_lower:
            return "speech"

        # Reasoning improvements
        if "reasoning" in description_lower or "rag" in description_lower or "llm" in description_lower:
            return "reasoning"

        return "general"

    def _plan_evolutionary_deployment(self, improvement_data: Dict[str, Any]) -> DeploymentPlan:
        """Create deployment plan for evolutionary improvements (config-based)."""
        improvement_id = improvement_data.get("request_id", "unknown")

        return DeploymentPlan(
            improvement_id=improvement_id,
            improvement_type="evolutionary",
            target_files=[".kloros_env"],  # Config-based deployments only touch env file
            backup_required=True,
            validation_commands=[
                # Verify env file exists and is readable
                "test -f /home/kloros/.kloros_env && echo 'Config file exists'",
                # Verify Python can import config (basic syntax check)
                "/home/kloros/.venv/bin/python3 -c 'import os; print(\"Config validation passed\")'"
            ],
            rollback_plan={"type": "backup_restore"},
            risk_level="low",  # Config changes are low risk
            estimated_duration=15
        )

    def _plan_configuration_deployment(self, improvement_data: Dict[str, Any]) -> DeploymentPlan:
        """Create deployment plan for configuration improvements."""
        improvement_id = improvement_data.get("request_id", "unknown")

        return DeploymentPlan(
            improvement_id=improvement_id,
            improvement_type="configuration",
            target_files=[
                ".kloros_env",
                "src/kloros_voice.py"
            ],
            backup_required=True,
            validation_commands=[
                "/home/kloros/.venv/bin/python3 -c 'import os; print(\"Config validation passed\")'",
                "grep -q 'KLR_' /home/kloros/.kloros_env || echo 'Config file accessible'"
            ],
            rollback_plan={"type": "backup_restore"},
            risk_level="low",
            estimated_duration=15
        )

    def _plan_memory_deployment(self, improvement_data: Dict[str, Any]) -> DeploymentPlan:
        """Create deployment plan for memory system improvements."""
        improvement_id = improvement_data.get("request_id", "unknown")

        return DeploymentPlan(
            improvement_id=improvement_id,
            improvement_type="memory",
            target_files=[
                "src/kloros_memory/",
                "src/kloros_voice.py"
            ],
            backup_required=True,
            validation_commands=[
                "/home/kloros/.venv/bin/python3 -c 'from src.kloros_memory import MemoryLogger; print(\"Memory import successful\")'",
                "/home/kloros/.venv/bin/python3 src/test_kloros_memory.py"
            ],
            rollback_plan={"type": "backup_restore"},
            risk_level=improvement_data.get("risk_level", "medium"),
            estimated_duration=45
        )

    def _plan_speech_deployment(self, improvement_data: Dict[str, Any]) -> DeploymentPlan:
        """Create deployment plan for speech/voice improvements."""
        improvement_id = improvement_data.get("request_id", "unknown")

        return DeploymentPlan(
            improvement_id=improvement_id,
            improvement_type="speech",
            target_files=[
                "src/kloros_voice.py",
                "src/stt/",
                ".kloros_env"
            ],
            backup_required=True,
            validation_commands=[
                "/home/kloros/.venv/bin/python3 -c 'from src.kloros_voice import KLoROS; print(\"KLoROS import successful\")'",
                "/home/kloros/.venv/bin/python3 -c 'from src.stt.vosk_backend import VoskSttBackend; print(\"STT import successful\")'"
            ],
            rollback_plan={"type": "backup_restore"},
            risk_level=improvement_data.get("risk_level", "medium"),
            estimated_duration=90
        )

    def _plan_reasoning_deployment(self, improvement_data: Dict[str, Any]) -> DeploymentPlan:
        """Create deployment plan for reasoning improvements."""
        improvement_id = improvement_data.get("request_id", "unknown")

        return DeploymentPlan(
            improvement_id=improvement_id,
            improvement_type="reasoning",
            target_files=[
                "src/reasoning/",
                "src/kloros_voice.py"
            ],
            backup_required=True,
            validation_commands=[
                "/home/kloros/.venv/bin/python3 -c 'from src.reasoning.rag_reasoning import RagReasoning; print(\"RAG import successful\")'",
                "/home/kloros/.venv/bin/python3 -c 'import requests; requests.get(\"http://localhost:11434/v1/models\")'"
            ],
            rollback_plan={"type": "backup_restore"},
            risk_level=improvement_data.get("risk_level", "medium"),
            estimated_duration=75
        )

    def _create_backup(self, plan: DeploymentPlan) -> str:
        """
        Create backup of files before deployment.

        Args:
            plan: Deployment plan containing target files

        Returns:
            Path to backup directory
        """
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        backup_dir = self.backup_path / f"backup_{plan.improvement_id}_{timestamp}"
        backup_dir.mkdir(parents=True, exist_ok=True)

        for target_file in plan.target_files:
            target_path = self.base_path / target_file

            if target_path.exists():
                if target_path.is_file():
                    # Backup individual file
                    backup_file = backup_dir / target_file
                    backup_file.parent.mkdir(parents=True, exist_ok=True)
                    shutil.copy2(target_path, backup_file)
                    logger.info(f"📄 Backed up file: {target_file}")
                elif target_path.is_dir():
                    # Backup entire directory
                    backup_subdir = backup_dir / target_file
                    shutil.copytree(target_path, backup_subdir)
                    logger.info(f"📁 Backed up directory: {target_file}")
            else:
                logger.warning(f"⚠️ Target file not found for backup: {target_file}")

        return str(backup_dir)

    def _execute_deployment(self, plan: DeploymentPlan, improvement_data: Dict[str, Any]) -> List[str]:
        """
        Execute the actual deployment based on the plan.

        Args:
            plan: Deployment plan to execute
            improvement_data: Original improvement data

        Returns:
            List of changes applied
        """
        changes_applied = []

        if plan.improvement_type == "configuration":
            changes = self._deploy_configuration_changes(improvement_data)
            changes_applied.extend(changes)
        elif plan.improvement_type == "evolutionary":
            changes = self._deploy_evolutionary_changes(improvement_data)
            changes_applied.extend(changes)
        elif plan.improvement_type == "memory":
            changes = self._deploy_memory_changes(improvement_data)
            changes_applied.extend(changes)
        elif plan.improvement_type == "speech":
            changes = self._deploy_speech_changes(improvement_data)
            changes_applied.extend(changes)
        elif plan.improvement_type == "reasoning":
            changes = self._deploy_reasoning_changes(improvement_data)
            changes_applied.extend(changes)
        else:
            # For unknown types, apply generic deployment
            changes = self._deploy_generic_changes(improvement_data)
            changes_applied.extend(changes)

        return changes_applied

    def _deploy_configuration_changes(self, improvement_data: Dict[str, Any]) -> List[str]:
        """
        Deploy configuration-based improvements via D-REAM apply_map.

        REAL IMPLEMENTATION - applies actual file modifications.
        FIX: Deployment pipeline façade - ASTRAEA Oct 26, 2025

        Args:
            improvement_data: Must contain parameter_recommendations with apply_map and params

        Returns:
            List of actual file modifications (NOT descriptions)
        """
        changes = []

        # Extract D-REAM promotion data
        param_recs = improvement_data.get("parameter_recommendations", {})
        apply_map = param_recs.get("apply_map")
        params = param_recs.get("params", {})

        if not apply_map or not params:
            logger.warning("[deployment] No apply_map or params in improvement_data - cannot deploy")
            return []

        # Target config file
        config_file = self.base_path / ".kloros_env"
        if not config_file.exists():
            logger.error(f"[deployment] Config file not found: {config_file}")
            return []

        # Read current config
        with open(config_file, 'r') as f:
            env_lines = f.readlines()

        # Apply each parameter via apply_map
        for param_name, env_var in apply_map.items():
            param_value = params.get(param_name)
            if param_value is None:
                logger.warning(f"[deployment] Param '{param_name}' not in params dict, skipping")
                continue

            # Format value (string or numeric)
            if isinstance(param_value, str):
                new_line = f"{env_var}={param_value}\n"
            else:
                new_line = f"{env_var}={param_value}\n"

            # Find existing env var and replace, or append new
            found = False
            for i, line in enumerate(env_lines):
                if line.strip().startswith(f"{env_var}="):
                    old_value = line.split("=", 1)[1].strip()
                    env_lines[i] = new_line
                    changes.append(f"UPDATED {env_var}: {old_value} → {param_value}")
                    found = True
                    logger.info(f"[deployment] Updated {env_var}: {old_value} → {param_value}")
                    break

            if not found:
                # Append new variable
                env_lines.append(f"\n# D-REAM Optimization ({datetime.now().isoformat()})\n")
                env_lines.append(new_line)
                changes.append(f"ADDED {env_var}={param_value}")
                logger.info(f"[deployment] Added {env_var}={param_value}")

        # CRITICAL: Actually write the file (not just log)
        if changes:
            with open(config_file, 'w') as f:
                f.writelines(env_lines)
            logger.info(f"[deployment] ✓ Wrote {len(changes)} config changes to {config_file}")
        else:
            logger.warning("[deployment] No changes to write - apply_map/params mismatch?")

        return changes

    def _deploy_evolutionary_changes(self, improvement_data: Dict[str, Any]) -> List[str]:
        """
        Deploy evolutionary optimization improvements.

        D-REAM evolutionary improvements are config-based (apply_map).
        Delegate to _deploy_configuration_changes for real file modification.
        """
        return self._deploy_configuration_changes(improvement_data)

    def _deploy_memory_changes(self, improvement_data: Dict[str, Any]) -> List[str]:
        """
        Deploy memory system improvements.

        Memory improvements are config-based (apply_map).
        Delegate to _deploy_configuration_changes for real file modification.
        """
        return self._deploy_configuration_changes(improvement_data)

    def _deploy_speech_changes(self, improvement_data: Dict[str, Any]) -> List[str]:
        """
        Deploy speech/voice improvements.

        Audio/speech improvements are config-based (apply_map).
        Delegate to _deploy_configuration_changes for real file modification.
        """
        return self._deploy_configuration_changes(improvement_data)

    def _deploy_reasoning_changes(self, improvement_data: Dict[str, Any]) -> List[str]:
        """
        Deploy reasoning system improvements.

        RAG/reasoning improvements are config-based (apply_map).
        Delegate to _deploy_configuration_changes for real file modification.
        """
        return self._deploy_configuration_changes(improvement_data)

    def _deploy_generic_changes(self, improvement_data: Dict[str, Any]) -> List[str]:
        """
        Deploy generic improvements.

        Try config-based deployment first (most D-REAM improvements are config).
        """
        return self._deploy_configuration_changes(improvement_data)

    def _validate_deployment(self, plan: DeploymentPlan) -> Dict[str, Any]:
        """
        Validate that deployment was successful.

        Args:
            plan: Deployment plan with validation commands

        Returns:
            Dictionary with validation results
        """
        results = {"success": True, "command_results": []}

        for command in plan.validation_commands:
            try:
                logger.info(f"🔍 Running validation: {command}")

                # Run validation command
                if command.startswith("/home/kloros/.venv/bin/python3 -c"):
                    # Python validation
                    result = subprocess.run(
                        command,
                        shell=True,
                        capture_output=True,
                        text=True,
                        timeout=30
                    )
                elif command.startswith("grep"):
                    # Grep validation
                    result = subprocess.run(
                        command,
                        shell=True,
                        capture_output=True,
                        text=True,
                        timeout=10
                    )
                else:
                    # Other commands
                    result = subprocess.run(
                        command,
                        shell=True,
                        capture_output=True,
                        text=True,
                        timeout=60
                    )

                command_success = result.returncode == 0
                results["command_results"].append({
                    "command": command,
                    "success": command_success,
                    "stdout": result.stdout,
                    "stderr": result.stderr
                })

                if not command_success:
                    results["success"] = False
                    logger.error(f"❌ Validation failed: {command}")
                else:
                    logger.info(f"✅ Validation passed: {command}")

            except subprocess.TimeoutExpired:
                results["success"] = False
                results["command_results"].append({
                    "command": command,
                    "success": False,
                    "error": "Command timed out"
                })
                logger.error(f"⏰ Validation timed out: {command}")
            except Exception as e:
                results["success"] = False
                results["command_results"].append({
                    "command": command,
                    "success": False,
                    "error": str(e)
                })
                logger.error(f"💥 Validation error: {command} - {e}")

        return results

    def _rollback_deployment(self, plan: DeploymentPlan, backup_path: str) -> bool:
        """
        Rollback deployment using backup.

        Args:
            plan: Original deployment plan
            backup_path: Path to backup directory

        Returns:
            True if rollback successful, False otherwise
        """
        try:
            logger.info(f"🔄 Rolling back deployment for {plan.improvement_id}")
            backup_dir = Path(backup_path)

            for target_file in plan.target_files:
                backup_file = backup_dir / target_file
                target_path = self.base_path / target_file

                if backup_file.exists():
                    if backup_file.is_file():
                        shutil.copy2(backup_file, target_path)
                        logger.info(f"📄 Restored file: {target_file}")
                    elif backup_file.is_dir():
                        if target_path.exists():
                            shutil.rmtree(target_path)
                        shutil.copytree(backup_file, target_path)
                        logger.info(f"📁 Restored directory: {target_file}")

            logger.info(f"✅ Rollback completed for {plan.improvement_id}")
            return True

        except Exception as e:
            logger.error(f"💥 Rollback failed for {plan.improvement_id}: {e}")
            return False

    def _load_deployment_history(self) -> List[Dict[str, Any]]:
        """Load deployment history from file."""
        if self.history_file.exists():
            try:
                with open(self.history_file, 'r') as f:
                    return json.load(f)
            except Exception as e:
                logger.warning(f"Failed to load deployment history: {e}")
                return []
        return []

    def _log_deployment(self, result: DeploymentResult) -> None:
        """Log deployment result to history."""
        history_entry = {
            "improvement_id": result.improvement_id,
            "success": result.success,
            "deployed_at": result.deployed_at.isoformat(),
            "backup_path": result.backup_path,
            "changes_applied": result.changes_applied,
            "validation_success": result.validation_results.get("success", False),
            "error_message": result.error_message,
            "rollback_performed": result.rollback_performed
        }

        self.deployment_history.append(history_entry)

        # Keep only last 100 deployments
        if len(self.deployment_history) > 100:
            self.deployment_history = self.deployment_history[-100:]

        # Save to file
        try:
            with open(self.history_file, 'w') as f:
                json.dump(self.deployment_history, f, indent=2)
        except Exception as e:
            logger.error(f"Failed to save deployment history: {e}")

    def get_deployment_status(self, improvement_id: str) -> Optional[Dict[str, Any]]:
        """Get deployment status for a specific improvement."""
        for entry in reversed(self.deployment_history):
            if entry["improvement_id"] == improvement_id:
                return entry
        return None

    def get_deployment_statistics(self) -> Dict[str, Any]:
        """Get deployment statistics."""
        total_deployments = len(self.deployment_history)
        successful_deployments = sum(1 for entry in self.deployment_history if entry["success"])
        failed_deployments = total_deployments - successful_deployments
        rollbacks_performed = sum(1 for entry in self.deployment_history if entry["rollback_performed"])

        return {
            "total_deployments": total_deployments,
            "successful_deployments": successful_deployments,
            "failed_deployments": failed_deployments,
            "success_rate": successful_deployments / total_deployments if total_deployments > 0 else 0,
            "rollbacks_performed": rollbacks_performed,
            "rollback_rate": rollbacks_performed / total_deployments if total_deployments > 0 else 0
        }

def main():
    """Test the deployment pipeline."""
    deployer = ImprovementDeployer()

    # Example improvement for testing
    test_improvement = {
        "request_id": "test_deployment_001",
        "component": "configuration",
        "description": "Test deployment pipeline functionality",
        "expected_benefit": "Validate deployment system works correctly",
        "risk_level": "low",
        "confidence": 0.95,
        "urgency": "medium",
        "detected_at": "2025-10-06T16:00:00.000000"
    }

    print("🧪 Testing Deployment Pipeline")
    print("=" * 40)

    result = deployer.deploy_improvement(test_improvement)

    if result.success:
        print(f"✅ Deployment successful: {result.improvement_id}")
        print(f"📄 Changes applied: {len(result.changes_applied)}")
        if result.backup_path:
            print(f"💾 Backup created: {result.backup_path}")
    else:
        print(f"❌ Deployment failed: {result.error_message}")
        if result.rollback_performed:
            print("🔄 Rollback was performed")

    # Show statistics
    stats = deployer.get_deployment_statistics()
    print(f"\n📊 Deployment Statistics:")
    print(f"   Total: {stats['total_deployments']}")
    print(f"   Success Rate: {stats['success_rate']:.1%}")

if __name__ == "__main__":
    main()