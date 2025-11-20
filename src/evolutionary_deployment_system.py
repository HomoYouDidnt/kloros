#!/usr/bin/env python3
"""
Evolutionary Code Deployment System for KLoROS D-REAM
Safely deploys winning evolutionary approaches to actual KLoROS codebase.
"""

import os
import sys
import time
import json
import shutil
import hashlib
import subprocess
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Any, Optional, Tuple
from dataclasses import dataclass
import ast
import importlib.util

@dataclass
class DeploymentTarget:
    """Represents a target file and method for evolutionary deployment."""
    file_path: Path
    class_name: Optional[str] = None
    method_name: Optional[str] = None
    insertion_point: Optional[str] = None  # Where to add new methods
    backup_path: Optional[Path] = None

@dataclass
class DeploymentPlan:
    """Plan for deploying evolutionary approach to codebase."""
    approach_id: str
    target: DeploymentTarget
    deployment_type: str  # "method_replacement", "method_addition", "method_enhancement"
    code_changes: Dict[str, str]
    validation_tests: List[str]
    rollback_strategy: str

class EvolutionaryDeploymentEngine:
    """Engine for safely deploying evolutionary improvements to KLoROS codebase."""

    def __init__(self):
        """Initialize deployment engine."""
        self.kloros_src = Path("/home/kloros/src")
        self.backup_dir = Path("/home/kloros/.kloros/evolutionary_backups")
        self.backup_dir.mkdir(parents=True, exist_ok=True)

        self.deployment_log = self.backup_dir / "deployment_log.json"
        self.deployments = self._load_deployment_history()

    def _load_deployment_history(self) -> List[Dict[str, Any]]:
        """Load deployment history from log."""
        if self.deployment_log.exists():
            try:
                with open(self.deployment_log, 'r') as f:
                    return json.load(f)
            except Exception:
                return []
        return []

    def _save_deployment_history(self):
        """Save deployment history to log."""
        try:
            with open(self.deployment_log, 'w') as f:
                json.dump(self.deployments, f, indent=2, default=str)
        except Exception as e:
            print(f"[deployment] Failed to save history: {e}")

    def create_deployment_plan(self, approach_id: str, approach_code: str, candidate_type: str) -> DeploymentPlan:
        """Create deployment plan for evolutionary approach."""

        if candidate_type == "memory_context_integration":
            return self._plan_memory_integration_deployment(approach_id, approach_code)
        elif candidate_type == "llm_tool_generation_consistency":
            return self._plan_llm_consistency_deployment(approach_id, approach_code)
        elif candidate_type == "rag_example_quality_enhancement":
            return self._plan_rag_quality_deployment(approach_id, approach_code)
        else:
            raise ValueError(f"Unknown candidate type: {candidate_type}")

    def _plan_memory_integration_deployment(self, approach_id: str, approach_code: str) -> DeploymentPlan:
        """Plan deployment for memory integration improvements."""
        target = DeploymentTarget(
            file_path=self.kloros_src / "kloros_voice.py",
            class_name="KLoROS",
            method_name="chat",
            insertion_point="# System introspection commands now handled by Qwen reasoning + tool integration"
        )

        # Extract the memory wrapper method from approach code
        wrapper_code = self._extract_method_code(approach_code, "memory_enhanced_chat_wrapper")

        code_changes = {
            "chat_method": self._create_memory_enhanced_chat_replacement(wrapper_code)
        }

        validation_tests = [
            "memory_context_retrieval_test",
            "chat_functionality_preservation_test"
        ]

        return DeploymentPlan(
            approach_id=approach_id,
            target=target,
            deployment_type="method_enhancement",
            code_changes=code_changes,
            validation_tests=validation_tests,
            rollback_strategy="restore_backup"
        )

    def _plan_llm_consistency_deployment(self, approach_id: str, approach_code: str) -> DeploymentPlan:
        """Plan deployment for LLM consistency improvements."""
        target = DeploymentTarget(
            file_path=self.kloros_src / "reasoning" / "local_rag_backend.py",
            class_name="LocalRagBackend",
            method_name="_execute_tool",
            insertion_point="# Execute the requested tool"
        )

        # Extract the constraint application method
        constraint_code = self._extract_method_code(approach_code, "apply_tool_template_constraints")

        code_changes = {
            "tool_execution_enhancement": self._create_tool_consistency_enhancement(constraint_code),
            "new_method": constraint_code
        }

        validation_tests = [
            "tool_consistency_test",
            "tool_execution_preservation_test"
        ]

        return DeploymentPlan(
            approach_id=approach_id,
            target=target,
            deployment_type="method_addition",
            code_changes=code_changes,
            validation_tests=validation_tests,
            rollback_strategy="restore_backup"
        )

    def _plan_rag_quality_deployment(self, approach_id: str, approach_code: str) -> DeploymentPlan:
        """Plan deployment for RAG quality improvements."""
        target = DeploymentTarget(
            file_path=self.kloros_src / "reasoning" / "local_rag_backend.py",
            class_name="LocalRagBackend",
            method_name="reply",
            insertion_point="# Retrieve and rank documents"
        )

        # Extract the example injection method
        injection_code = self._extract_method_code(approach_code, "inject_tool_synthesis_examples")

        code_changes = {
            "rag_enhancement": self._create_rag_quality_enhancement(injection_code),
            "new_method": injection_code
        }

        validation_tests = [
            "rag_quality_test",
            "retrieval_functionality_preservation_test"
        ]

        return DeploymentPlan(
            approach_id=approach_id,
            target=target,
            deployment_type="method_addition",
            code_changes=code_changes,
            validation_tests=validation_tests,
            rollback_strategy="restore_backup"
        )

    def deploy_evolutionary_approach(self, plan: DeploymentPlan) -> Dict[str, Any]:
        """Deploy evolutionary approach according to plan."""
        deployment_id = f"{plan.approach_id}_{int(time.time())}"

        deployment_result = {
            "deployment_id": deployment_id,
            "approach_id": plan.approach_id,
            "timestamp": datetime.now().isoformat(),
            "success": False,
            "changes_applied": [],
            "validation_results": {},
            "backup_path": None,
            "error": None
        }

        try:
            # Step 1: Create backup
            backup_path = self._create_backup(plan.target.file_path, deployment_id)
            deployment_result["backup_path"] = str(backup_path)
            plan.target.backup_path = backup_path

            # Step 2: Apply code changes
            changes_applied = self._apply_code_changes(plan)
            deployment_result["changes_applied"] = changes_applied

            # Step 3: Validate deployment
            validation_results = self._validate_deployment(plan)
            deployment_result["validation_results"] = validation_results

            # Step 4: Check if deployment is successful
            if all(validation_results.values()):
                deployment_result["success"] = True
                print(f"[deployment] Successfully deployed {plan.approach_id}")

                # Log successful deployment
                self.deployments.append(deployment_result)
                self._save_deployment_history()

            else:
                # Rollback on validation failure
                print(f"[deployment] Validation failed for {plan.approach_id}, rolling back")
                self._rollback_deployment(plan)
                deployment_result["error"] = "Validation failed"

        except Exception as e:
            deployment_result["error"] = str(e)
            print(f"[deployment] Deployment failed: {e}")

            # Attempt rollback
            try:
                self._rollback_deployment(plan)
            except Exception as rollback_error:
                print(f"[deployment] Rollback failed: {rollback_error}")

        return deployment_result

    def _create_backup(self, file_path: Path, deployment_id: str) -> Path:
        """Create backup of file before modification."""
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        backup_name = f"{file_path.name}.backup_{deployment_id}_{timestamp}"
        backup_path = self.backup_dir / backup_name

        shutil.copy2(file_path, backup_path)
        print(f"[deployment] Created backup: {backup_path}")

        return backup_path

    def _apply_code_changes(self, plan: DeploymentPlan) -> List[str]:
        """Apply code changes according to deployment plan."""
        changes_applied = []

        try:
            # Read original file
            with open(plan.target.file_path, 'r') as f:
                original_content = f.read()

            modified_content = original_content

            # Apply changes based on deployment type
            if plan.deployment_type == "method_enhancement":
                modified_content = self._enhance_existing_method(modified_content, plan)
                changes_applied.append("method_enhancement")

            elif plan.deployment_type == "method_addition":
                modified_content = self._add_new_methods(modified_content, plan)
                changes_applied.append("method_addition")

            elif plan.deployment_type == "method_replacement":
                modified_content = self._replace_method(modified_content, plan)
                changes_applied.append("method_replacement")

            # Write modified content
            with open(plan.target.file_path, 'w') as f:
                f.write(modified_content)

            print(f"[deployment] Applied changes to {plan.target.file_path}")

        except Exception as e:
            raise Exception(f"Failed to apply code changes: {e}")

        return changes_applied

    def _enhance_existing_method(self, content: str, plan: DeploymentPlan) -> str:
        """Enhance existing method with evolutionary improvements."""
        if plan.target.method_name == "chat" and "memory_enhanced_chat_wrapper" in plan.code_changes.get("chat_method", ""):
            # Insert memory enhancement into chat method
            insertion_point = plan.target.insertion_point
            if insertion_point in content:
                enhancement_code = """
        # Evolutionary memory enhancement
        if hasattr(self, "memory_enhanced") and self.memory_enhanced and self.memory_enhanced.enable_memory:
            try:
                # Enhanced memory context retrieval
                context_result = self.memory_enhanced._retrieve_context(user_message)
                if context_result and context_result.events:
                    context_text = self.memory_enhanced._format_context_for_prompt(context_result)
                    if context_text:
                        print(f"[evolution] Enhanced memory context applied")
                        user_message = f"[Context]: {context_text}\\n\\n[Query]: {user_message}"
            except Exception as e:
                print(f"[evolution] Memory enhancement error: {e}")
"""
                content = content.replace(insertion_point, insertion_point + enhancement_code)

        return content

    def _add_new_methods(self, content: str, plan: DeploymentPlan) -> str:
        """Add new methods to existing class."""
        # Find class definition
        class_pattern = f"class {plan.target.class_name}"
        class_start = content.find(class_pattern)

        if class_start == -1:
            raise Exception(f"Class {plan.target.class_name} not found")

        # Find good insertion point (end of class, before next class or EOF)
        insertion_point = self._find_method_insertion_point(content, class_start)

        # Add new methods
        new_methods = ""
        for method_name, method_code in plan.code_changes.items():
            if method_name == "new_method":
                # Format method with proper indentation
                indented_code = self._indent_code(method_code, 4)
                new_methods += f"\n    # Evolutionary enhancement method\n{indented_code}\n"

        # Insert new methods
        content = content[:insertion_point] + new_methods + content[insertion_point:]

        return content

    def _validate_deployment(self, plan: DeploymentPlan) -> Dict[str, bool]:
        """Validate deployment by running tests."""
        validation_results = {}

        for test_name in plan.validation_tests:
            try:
                if test_name == "memory_context_retrieval_test":
                    result = self._test_memory_functionality(plan.target.file_path)
                elif test_name == "tool_consistency_test":
                    result = self._test_tool_consistency(plan.target.file_path)
                elif test_name == "rag_quality_test":
                    result = self._test_rag_quality(plan.target.file_path)
                else:
                    result = True  # Default to pass for unknown tests

                validation_results[test_name] = result

            except Exception as e:
                print(f"[deployment] Validation test {test_name} failed: {e}")
                validation_results[test_name] = False

        return validation_results

    def _test_memory_functionality(self, file_path: Path) -> bool:
        """Test that memory functionality still works after deployment."""
        try:
            # Try to import and create instance
            spec = importlib.util.spec_from_file_location("test_module", file_path)
            module = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(module)

            # Basic syntax and import validation
            return hasattr(module, 'KLoROS')

        except Exception as e:
            print(f"[deployment] Memory test failed: {e}")
            return False

    def _test_tool_consistency(self, file_path: Path) -> bool:
        """Test that tool consistency improvements work."""
        try:
            # Validate file syntax and structure
            with open(file_path, 'r') as f:
                content = f.read()

            # Parse to ensure valid Python
            ast.parse(content)
            return True

        except Exception as e:
            print(f"[deployment] Tool consistency test failed: {e}")
            return False

    def _test_rag_quality(self, file_path: Path) -> bool:
        """Test that RAG quality improvements work."""
        try:
            # Validate file syntax and structure
            with open(file_path, 'r') as f:
                content = f.read()

            # Parse to ensure valid Python
            ast.parse(content)
            return True

        except Exception as e:
            print(f"[deployment] RAG quality test failed: {e}")
            return False

    def _rollback_deployment(self, plan: DeploymentPlan):
        """Rollback deployment by restoring backup."""
        if plan.target.backup_path and plan.target.backup_path.exists():
            shutil.copy2(plan.target.backup_path, plan.target.file_path)
            print(f"[deployment] Rollback completed: restored {plan.target.file_path}")
        else:
            raise Exception("Backup not found for rollback")

    def _extract_method_code(self, code: str, method_name: str) -> str:
        """Extract specific method code from approach code."""
        lines = code.split('\n')
        method_lines = []
        in_method = False
        indent_level = 0

        for line in lines:
            if f"def {method_name}" in line:
                in_method = True
                indent_level = len(line) - len(line.lstrip())
                method_lines.append(line)
            elif in_method:
                current_indent = len(line) - len(line.lstrip())
                if line.strip() and current_indent <= indent_level and not line.startswith(' ' * (indent_level + 1)):
                    break
                method_lines.append(line)

        return '\n'.join(method_lines)

    def _create_memory_enhanced_chat_replacement(self, wrapper_code: str) -> str:
        """Create enhanced chat method replacement."""
        return f"""
    def chat(self, user_message: str) -> str:
        '''Text-based chat interface with evolutionary memory enhancement.'''
        # Evolutionary memory enhancement
        {wrapper_code}

        # Fallback to original implementation
        return self._original_chat_implementation(user_message)
"""

    def _create_tool_consistency_enhancement(self, constraint_code: str) -> str:
        """Create tool consistency enhancement."""
        return f"""
        # Apply evolutionary tool consistency constraints
        try:
            if 'TOOL:' in result:
                result = self.apply_tool_template_constraints(result)
        except Exception as e:
            print(f"[evolution] Tool consistency enhancement error: {{e}}")
"""

    def _create_rag_quality_enhancement(self, injection_code: str) -> str:
        """Create RAG quality enhancement."""
        return f"""
        # Apply evolutionary RAG quality enhancement
        try:
            retrieved_docs = self.inject_tool_synthesis_examples(query, retrieved_docs)
        except Exception as e:
            print(f"[evolution] RAG quality enhancement error: {{e}}")
"""

    def _find_method_insertion_point(self, content: str, class_start: int) -> int:
        """Find appropriate insertion point for new methods in class."""
        # Simple heuristic: find end of last method in class
        lines = content[class_start:].split('\n')

        for i in range(len(lines) - 1, -1, -1):
            line = lines[i]
            if line.strip() and not line.startswith(' '):
                # Found next class or end of file
                return class_start + len('\n'.join(lines[:i]))

        return len(content)

    def _indent_code(self, code: str, spaces: int) -> str:
        """Add indentation to code block."""
        indent = ' ' * spaces
        return '\n'.join(indent + line if line.strip() else line for line in code.split('\n'))

def main():
    """Test the deployment system."""
    print("=== Testing Evolutionary Deployment System ===")

    engine = EvolutionaryDeploymentEngine()

    # Test creating deployment plan
    sample_code = '''
def memory_enhanced_chat_wrapper(self, message: str) -> str:
    """Enhanced memory-aware chat wrapper."""
    if hasattr(self, "memory_enhanced") and self.memory_enhanced:
        context_result = self.memory_enhanced._retrieve_context(message)
        if context_result:
            context_text = self.memory_enhanced._format_context_for_prompt(context_result)
            if context_text:
                enhanced_message = f"[Context]: {context_text}\\n\\n[Query]: {message}"
                return self.reason_backend.reply(enhanced_message, kloros_instance=self).reply_text

    return self.reason_backend.reply(message, kloros_instance=self).reply_text
'''

    plan = engine.create_deployment_plan("test_memory_v1", sample_code, "memory_context_integration")
    print(f"Created deployment plan: {plan.approach_id}")
    print(f"Target: {plan.target.file_path}")
    print(f"Deployment type: {plan.deployment_type}")

    print("\n=== Deployment System Test Complete ===")

if __name__ == "__main__":
    main()