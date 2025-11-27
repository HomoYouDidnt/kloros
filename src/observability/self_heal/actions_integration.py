"""Integration fix actions - Code patching for architectural issues.

Extends the self-heal action system with code modification capabilities.
"""

import os
from typing import Dict, Any, Optional
from pathlib import Path
from .actions import HealAction

# Import the existing patchers
try:
    from src.dream.deploy.patcher import ChangeRequest, PatchManager
    DREAM_PATCHER_AVAILABLE = True
except ImportError:
    DREAM_PATCHER_AVAILABLE = False

try:
    from src.agents.dev_agent.tools.patcher import apply_patch_with_validation
    DEV_AGENT_PATCHER_AVAILABLE = True
except ImportError:
    DEV_AGENT_PATCHER_AVAILABLE = False


class AddMissingCallAction(HealAction):
    """
    Add a missing method call to fix orphaned queue/broken integration.

    Use case: Alert queue is populated but never consumed
    Solution: Add poll call in handle_conversation()

    Parameters:
        file: Path to file to modify
        function: Function to add call to
        call_code: Code to insert (list of lines)
        insert_after_line: Line number to insert after (optional)
        insert_at_start: Insert at start of function body (default: True)
    """

    def __init__(self, name: str, params: Dict[str, Any]):
        super().__init__(name, params)
        self.patch_manager = None
        if DREAM_PATCHER_AVAILABLE:
            self.patch_manager = PatchManager(artifacts_dir="/home/kloros/.kloros/integration_patches")

    def apply(self, kloros_instance) -> bool:
        if not DREAM_PATCHER_AVAILABLE:
            print(f"[action] Code patching not available (libcst missing)")
            return False

        file_path = self.params.get("file")
        function_name = self.params.get("function")
        call_code = self.params.get("call_code", [])

        if not file_path or not function_name or not call_code:
            print(f"[action] Missing required parameters")
            return False

        # Read original function
        try:
            with open(file_path, 'r') as f:
                source = f.read()
        except Exception as e:
            print(f"[action] Failed to read {file_path}: {e}")
            return False

        # Parse and find the function
        import ast
        try:
            tree = ast.parse(source)
        except SyntaxError as e:
            print(f"[action] Syntax error in {file_path}: {e}")
            return False

        # Find function and extract current body
        func_node = None
        for node in ast.walk(tree):
            if isinstance(node, ast.FunctionDef) and node.name == function_name:
                func_node = node
                break

        if not func_node:
            print(f"[action] Function {function_name} not found in {file_path}")
            return False

        # Get function source (approximate - we'll use line numbers)
        func_start_line = func_node.lineno

        # Build new implementation with call added
        # This is simplified - full version would use AST manipulation
        lines = source.split('\n')

        # Find first line after function definition (skip decorator, def line)
        insert_line = func_start_line  # After 'def function():'

        # Find first non-comment, non-docstring line
        in_docstring = False
        for i in range(func_start_line, min(func_start_line + 20, len(lines))):
            line = lines[i].strip()
            if '"""' in line or "'''" in line:
                in_docstring = not in_docstring
                continue
            if not in_docstring and line and not line.startswith('#'):
                insert_line = i + 1
                break

        # Insert the call code
        indent = self._detect_indent(lines[insert_line] if insert_line < len(lines) else "    ")
        formatted_code = [indent + line for line in call_code]

        # Insert and create new source
        new_lines = lines[:insert_line] + formatted_code + lines[insert_line:]
        new_source = '\n'.join(new_lines)

        # Validate syntax
        try:
            ast.parse(new_source)
        except SyntaxError as e:
            print(f"[action] Generated code has syntax error: {e}")
            return False

        # Save rollback data
        self._rollback_data = {
            "file_path": file_path,
            "original_content": source,
            "patch_manager": self.patch_manager
        }

        # Apply using PatchManager (creates backup)
        try:
            # Write new version
            with open(file_path, 'w') as f:
                f.write(new_source)

            print(f"[action] Added call to {function_name} in {file_path}")
            print(f"[action] Inserted {len(formatted_code)} lines at line {insert_line}")
            return True

        except Exception as e:
            print(f"[action] Failed to write patched file: {e}")
            return False

    def rollback(self, kloros_instance) -> bool:
        if not self._rollback_data:
            return False

        file_path = self._rollback_data["file_path"]
        original_content = self._rollback_data["original_content"]

        try:
            with open(file_path, 'w') as f:
                f.write(original_content)
            print(f"[action] Rolled back {file_path}")
            return True
        except Exception as e:
            print(f"[action] Rollback failed: {e}")
            return False

    def _detect_indent(self, line: str) -> str:
        """Detect indentation from a line."""
        indent = ""
        for char in line:
            if char in [' ', '\t']:
                indent += char
            else:
                break
        return indent if indent else "    "


class AddNullCheckAction(HealAction):
    """
    Add null/existence check before using a component.

    Use case: self.alert_manager used but may not be initialized
    Solution: Wrap usage in if hasattr(self, 'alert_manager') and self.alert_manager:

    Parameters:
        file: Path to file
        component: Component name (e.g., 'alert_manager')
        usage_line: Line number where component is used unsafely
    """

    def apply(self, kloros_instance) -> bool:
        file_path = self.params.get("file")
        component = self.params.get("component")
        usage_line = self.params.get("usage_line")

        if not all([file_path, component, usage_line]):
            print(f"[action] Missing required parameters")
            return False

        try:
            with open(file_path, 'r') as f:
                lines = f.readlines()
        except Exception as e:
            print(f"[action] Failed to read {file_path}: {e}")
            return False

        if usage_line < 1 or usage_line > len(lines):
            print(f"[action] Invalid line number: {usage_line}")
            return False

        # Get the line and its indentation
        target_line = lines[usage_line - 1]
        indent = self._get_indent(target_line)

        # IDEMPOTENCY: Check if this exact null check already exists
        check_pattern = f"if hasattr(self, '{component}') and self.{component}:"
        if check_pattern in target_line:
            print(f"[action] Null check for {component} already exists at line {usage_line}, skipping")
            # Already applied, not an error
            return True

        # Also check the line before (in case it was added as separate line)
        if usage_line > 1 and check_pattern in lines[usage_line - 2]:
            print(f"[action] Null check for {component} already exists at line {usage_line - 1}, skipping")
            return True

        # Wrap in null check
        check_line = f"{indent}if hasattr(self, '{component}') and self.{component}:\n"
        indented_target = f"{indent}    {target_line.lstrip()}"

        # Save original
        self._rollback_data = {
            "file_path": file_path,
            "original_lines": lines.copy()
        }

        # Replace line with check + indented original
        lines[usage_line - 1] = check_line + indented_target

        # Write back
        try:
            with open(file_path, 'w') as f:
                f.writelines(lines)
            print(f"[action] Added null check for {component} at line {usage_line}")
            return True
        except Exception as e:
            print(f"[action] Failed to write file: {e}")
            return False

    def rollback(self, kloros_instance) -> bool:
        if not self._rollback_data:
            return False

        file_path = self._rollback_data["file_path"]
        original_lines = self._rollback_data["original_lines"]

        try:
            with open(file_path, 'w') as f:
                f.writelines(original_lines)
            print(f"[action] Rolled back {file_path}")
            return True
        except Exception as e:
            print(f"[action] Rollback failed: {e}")
            return False

    def _get_indent(self, line: str) -> str:
        """Get indentation from line."""
        return line[:len(line) - len(line.lstrip())]


class ConsolidateDuplicatesAction(HealAction):
    """
    Mark duplicate components for manual review/consolidation.

    This action is safer as a documentation/flagging action rather than
    automatic code consolidation (too risky).

    Parameters:
        components: List of duplicate component names
        files: List of files where duplicates exist
        responsibility: What the components do
    """

    def apply(self, kloros_instance) -> bool:
        # Handle both duplicate components and orphaned queues
        channel = self.params.get("channel")
        producer_file = self.params.get("producer_file")
        evidence = self.params.get("evidence", [])

        # Legacy duplicate component params
        components = self.params.get("components", [])
        files = self.params.get("files", [])
        responsibility = self.params.get("responsibility", "unknown")

        # Create issue file for manual review
        issue_dir = Path("/home/kloros/.kloros/integration_issues")
        issue_dir.mkdir(parents=True, exist_ok=True)

        # Determine issue type and generate appropriate report
        if channel:
            # Orphaned queue issue
            issue_file = issue_dir / f"orphaned_queue_{channel}.md"
            content = f"""# Orphaned Queue Detected

**Channel:** {channel}

**Producer File:** {producer_file or "Unknown"}

**Evidence:**
{chr(10).join(f'- {e}' for e in evidence)}

**Problem:**
This data structure is being populated but never consumed. This may indicate:
- A broken integration (consumer was removed/disabled)
- An incomplete feature (consumer not yet implemented)
- Dead code (producer is no longer needed)

**Recommendation:**
1. Verify if this queue is still needed
2. If yes: Add consumer in appropriate location
3. If no: Remove producer code

**Status:** Pending manual review

**Generated:** {__import__('datetime').datetime.now().isoformat()}
"""
        else:
            # Duplicate component issue
            issue_file = issue_dir / f"duplicate_{components[0]}.md"
            content = f"""# Duplicate Responsibility Detected

**Responsibility:** {responsibility}

**Duplicate Components:**
{chr(10).join(f'- {c}' for c in components)}

**Files:**
{chr(10).join(f'- {f}' for f in files)}

**Recommendation:**
Choose one as the canonical implementation and deprecate others.

**Status:** Pending manual review

**Generated:** {__import__('datetime').datetime.now().isoformat()}
"""

        try:
            with open(issue_file, 'w') as f:
                f.write(content)
            print(f"[action] Created integration issue report: {issue_file}")

            # Save for rollback
            self._rollback_data = {"issue_file": str(issue_file)}
            return True
        except Exception as e:
            print(f"[action] Failed to create issue file: {e}")
            return False

    def rollback(self, kloros_instance) -> bool:
        if not self._rollback_data:
            return False

        issue_file = Path(self._rollback_data["issue_file"])
        try:
            issue_file.unlink(missing_ok=True)
            print(f"[action] Removed issue file: {issue_file}")
            return True
        except Exception as e:
            print(f"[action] Rollback failed: {e}")
            return False


# Extended action registry
INTEGRATION_ACTION_CLASSES = {
    "add_missing_call": AddMissingCallAction,
    "add_null_check": AddNullCheckAction,
    "consolidate_duplicates": ConsolidateDuplicatesAction,
}


def create_integration_action(action_def: Dict[str, Any]) -> Optional[HealAction]:
    """
    Factory for creating integration fix actions.

    Args:
        action_def: Action definition with 'action' and 'params'

    Returns:
        HealAction instance or None if unknown action
    """
    action_name = action_def.get("action")
    params = action_def.get("params", {})

    action_class = INTEGRATION_ACTION_CLASSES.get(action_name)
    if not action_class:
        print(f"[actions_integration] Unknown action: {action_name}")
        return None

    return action_class(action_name, params)
