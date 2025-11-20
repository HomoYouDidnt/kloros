"""
Tool validation and testing framework for KLoROS tool synthesis.

Ensures synthesized tools are safe and functional before deployment.
"""

import ast
import re
import subprocess
import tempfile
import os
import inspect
from typing import Dict, List, Optional, Tuple
import json
from .venv_guard import create_venv_isolated_namespace, validate_tool_venv_safety


REQ_SECTIONS = ("Args:", "Returns:")


def validate_docstring(func) -> list[str]:
    """Validate that a function has required docstring sections.

    Args:
        func: Function to validate

    Returns:
        List of validation error messages (empty if valid)
    """
    doc = inspect.getdoc(func) or ""
    gaps = []
    for sec in REQ_SECTIONS:
        if sec not in doc:
            gaps.append(f"docstring missing section: {sec}")
    for p in inspect.signature(func).parameters:
        if p not in doc:
            gaps.append(f"docstring missing param: {p}")
    return gaps


class ToolValidator:
    """Validator for synthesized tool code."""

    def __init__(self):
        self.dangerous_patterns = self._initialize_dangerous_patterns()
        self.required_patterns = self._initialize_required_patterns()

    def validate_tool_code(self, code: str) -> bool:
        """
        Validate generated tool code for safety and correctness.

        Args:
            code: Python code to validate

        Returns:
            True if code passes all validation checks, False otherwise
        """
        # Step 1: Basic syntax validation
        if not self._validate_syntax(code):
            return False

        # Step 2: Security validation
        if not self._validate_security(code):
            return False

        # Step 3: Structure validation
        if not self._validate_structure(code):
            return False

        # Step 4: API usage validation
        if not self._validate_api_usage(code):
            return False

        return True

    def _validate_syntax(self, code: str) -> bool:
        """Check if code has valid Python syntax."""
        try:
            ast.parse(code)
            return True
        except SyntaxError:
            return False

    def _validate_security(self, code: str) -> bool:
        """Check for dangerous operations and security issues."""

        # Check for actual dangerous imports using AST
        try:
            tree = ast.parse(code)
            for node in ast.walk(tree):
                if isinstance(node, ast.Import):
                    for alias in node.names:
                        if self._is_dangerous_import(alias.name):
                            return False
                elif isinstance(node, ast.ImportFrom):
                    if node.module and self._is_dangerous_import(node.module):
                        return False
                    for alias in node.names:
                        if self._is_dangerous_import(alias.name):
                            return False
        except:
            # If AST parsing fails, fall back to basic checks
            pass

        # Check for truly dangerous function calls
        dangerous_calls = [
            r'\beval\s*\(',  # Code execution
            r'\bexec\s*\(',  # Code execution
            r'\bcompile\s*\(',  # Code compilation
            r'\b__import__\s*\(',  # Dynamic imports
            r'\bglobals\s*\(',  # Global scope manipulation
            r'\blocals\s*\(',  # Local scope manipulation
            r'\bos\.system\s*\(',  # Shell command execution
            # Note: input(), dir(), vars() are useful for introspection and allowed
        ]

        for call_pattern in dangerous_calls:
            if re.search(call_pattern, code):
                return False

        # Check for dangerous patterns
        for pattern in self.dangerous_patterns:
            if re.search(pattern, code, re.IGNORECASE):
                return False

        return True

    def _is_dangerous_import(self, module_name: str) -> bool:
        """Check if an import is actually dangerous."""
        # Truly dangerous modules - completely blocked
        highly_dangerous = [
            'shutil',  # File system destruction
            'socket',  # Raw network access
            'multiprocessing',  # Process spawning
            'threading',  # Thread spawning
            'signal',  # Process signals
            'ctypes',  # C library access
            'imp',  # Import manipulation
            'importlib',  # Import manipulation
            'pkgutil'  # Package manipulation
        ]

        # Allow useful modules for introspection and system queries
        allowed_modules = [
            'os', 'sys', 'glob', 'json', 'time', 'datetime', 'math', 're', 'numpy',
            'subprocess',  # For read-only system commands (ps, nvidia-smi, etc)
            'requests', 'urllib', 'http',  # For API/web queries
            'pathlib',  # Modern file path handling
            'collections',  # Data structures
            'itertools',  # Iteration tools
            'functools',  # Function tools
            'platform',  # Platform info
            'psutil',  # Process/system utilities
        ]

        # GPU libraries are safe for read-only queries
        gpu_libraries = [
            'torch', 'tensorflow', 'faster_whisper', 'whisper',
            'librosa', 'torchaudio', 'nvidia', 'cuda', 'pynvml'
        ]

        if module_name in allowed_modules or module_name in gpu_libraries:
            return False

        return module_name in highly_dangerous

    def _validate_structure(self, code: str) -> bool:
        """Validate code structure and function signature."""

        # Must contain a function definition
        if 'def tool_' not in code:
            return False

        # Function must have correct signature pattern
        func_pattern = r'def tool_\w+\(kloros_instance[^)]*\)\s*->\s*str:'
        if not re.search(func_pattern, code):
            return False

        # Must have try/except block
        if 'try:' not in code or 'except' not in code:
            return False

        # Must return string
        if 'return' not in code:
            return False

        return True

    def _validate_api_usage(self, code: str) -> bool:
        """Validate proper usage of KLoROS APIs."""

        # Check for kloros_instance usage
        if 'kloros_instance' not in code:
            return False

        # Check for proper error handling patterns
        error_patterns = [
            r'except\s+\w*Exception',
            r'except\s*:',
            r'return\s+["\'].*error.*["\']'
        ]

        has_error_handling = any(re.search(pattern, code, re.IGNORECASE)
                               for pattern in error_patterns)
        if not has_error_handling:
            return False

        # Check for hallucinated attributes (common errors)
        # These attributes don't exist on StandaloneKLoROS
        hallucinated_attrs = [
            r'kloros_instance\.audio_backend(?!\s*=)',  # Accessing, not setting
            r'kloros_instance\.stt_backend(?!\s*=)',
            r'kloros_instance\.tts_backend(?!\s*=)',
            r'kloros_instance\.tool_registry(?!\s*=)',
            r'kloros_instance\.conversation_flow(?!\s*=)',
            r'kloros_instance\.enrollment_mode(?!\s*=)',
            r'kloros_instance\.memory(?!\s*=|\s*_)',  # .memory but not .memory_enhanced
            r'kloros_instance\.database(?!\s*=)',
        ]

        for pattern in hallucinated_attrs:
            if re.search(pattern, code):
                # Only fail if there's no hasattr check protecting it
                attr_name = pattern.split(r'\.')[1].split(r'(?')[0]
                hasattr_check = f"hasattr(kloros_instance, '{attr_name}')"
                if hasattr_check not in code:
                    return False

        return True


    def test_tool_functionality(self, tool_name: str, tool_code: str,
                              mock_kloros: Optional[object] = None) -> Dict:
        """
        Test tool functionality in isolated environment.

        Args:
            tool_name: Name of the tool
            tool_code: Python code for the tool
            mock_kloros: Mock KLoROS instance for testing

        Returns:
            Test results dictionary
        """
        results = {
            'success': False,
            'error': None,
            'execution_time': 0,
            'return_type': None,
            'return_value': None
        }

        try:
            # First check venv safety
            is_venv_safe, venv_msg = validate_tool_venv_safety(tool_code)
            if not is_venv_safe:
                results['error'] = f"Venv safety violation: {venv_msg}"
                return results

            # Create venv-isolated namespace for validation
            venv_namespace = create_venv_isolated_namespace()

            # Execute tool code with venv protection
            exec(tool_code, venv_namespace)

            # Find tool function in the execution namespace
            func_name = f"tool_{tool_name.replace('-', '_').replace(' ', '_')}"
            if func_name not in venv_namespace:
                results['error'] = f"Function {func_name} not found"
                return results

            tool_func = venv_namespace[func_name]

            # Create mock KLoROS instance if not provided
            if mock_kloros is None:
                mock_kloros = self._create_mock_kloros()

            # Test tool execution
            import time
            start_time = time.time()

            result = tool_func(mock_kloros)

            end_time = time.time()

            # Record results
            results['success'] = True
            results['execution_time'] = end_time - start_time
            results['return_type'] = type(result).__name__
            results['return_value'] = str(result)[:200]  # Truncate for safety

        except Exception as e:
            results['error'] = str(e)

        return results

    def _create_mock_kloros(self) -> object:
        """Create a mock StandaloneKLoROS instance for testing.

        IMPORTANT: This mock must match the actual StandaloneKLoROS interface.
        StandaloneKLoROS only has: conversation_history, reason_backend, memory_enhanced
        It does NOT have: audio_backend, stt_backend, tts_backend, tool_registry,
                         conversation_flow, enrollment_mode (voice mode only)
        """

        class MockReasonBackend:
            def reply(self, message, kloros_instance=None, mode=None):
                return type('obj', (object,), {'reply_text': 'Mock response'})()

        class MockMemoryLogger:
            def log_user_input(self, transcript, confidence):
                pass
            def log_llm_response(self, response, model):
                pass

        class MockMemoryEnhanced:
            def __init__(self):
                self.memory_logger = MockMemoryLogger()

        class MockStandaloneKLoROS:
            """Mock that matches actual StandaloneKLoROS interface."""
            def __init__(self):
                # Only the attributes that actually exist on StandaloneKLoROS
                self.conversation_history = []
                self.reason_backend = MockReasonBackend()
                self.memory_enhanced = MockMemoryEnhanced()

            def chat(self, message):
                return "Mock chat response"

        return MockStandaloneKLoROS()

    def _initialize_dangerous_patterns(self) -> List[str]:
        """Initialize patterns for truly dangerous code."""

        return [
            # Truly dangerous operations only
            r'rm\s+-rf',  # Recursive file deletion
            r'sudo\s+',  # Privilege escalation
            r'passwd\s+',  # Password changes
            r'chmod\s+777',  # Dangerous permissions
            r'setattr\s*\(',  # Dynamic attribute setting
            r'delattr\s*\(',  # Dynamic attribute deletion

            # Destructive file operations
            r'\.unlink\s*\(',  # File deletion
            r'\.rmdir\s*\(',  # Directory deletion
            r'os\.remove\s*\(',  # File removal via os module
            r'shutil\.rmtree\s*\(',  # Recursive directory deletion

            # Process manipulation
            r'\.kill\s*\(',  # Process killing
            r'\.terminate\s*\(',  # Process termination
            r'signal\.SIGKILL',  # Kill signals

            # Infinite loops (but allow reasonable bounded loops)
            r'while\s+True\s*:(?!\s*#\s*intentional)',  # Infinite loops without explicit comment
            r'for\s+.*\s+in\s+range\s*\(\s*\d{7,}',  # Very large loops (10M+ iterations)
        ]

    def _initialize_required_patterns(self) -> List[str]:
        """Initialize patterns that must be present."""

        return [
            r'def\s+tool_\w+',  # Function definition
            r'kloros_instance',  # KLoROS instance usage
            r'try\s*:',  # Error handling
            r'except',  # Exception handling
            r'return\s+',  # Return statement
        ]

    def get_validation_report(self, tool_name: str, tool_code: str) -> Dict:
        """
        Generate comprehensive validation report.

        Args:
            tool_name: Name of the tool
            tool_code: Python code to validate

        Returns:
            Detailed validation report
        """

        report = {
            'tool_name': tool_name,
            'validation_passed': False,
            'checks': {
                'syntax': False,
                'security': False,
                'structure': False,
                'api_usage': False
            },
            'functionality_test': {},
            'warnings': [],
            'errors': []
        }

        # Run validation checks
        try:
            report['checks']['syntax'] = self._validate_syntax(tool_code)
            if not report['checks']['syntax']:
                report['errors'].append("Invalid Python syntax")

            report['checks']['security'] = self._validate_security(tool_code)
            if not report['checks']['security']:
                report['errors'].append("Security validation failed")

            report['checks']['structure'] = self._validate_structure(tool_code)
            if not report['checks']['structure']:
                report['errors'].append("Invalid function structure")

            report['checks']['api_usage'] = self._validate_api_usage(tool_code)
            if not report['checks']['api_usage']:
                report['errors'].append("Invalid API usage")

            # Overall validation
            report['validation_passed'] = all(report['checks'].values())

            # Functionality test
            if report['validation_passed']:
                report['functionality_test'] = self.test_tool_functionality(
                    tool_name, tool_code
                )

        except Exception as e:
            report['errors'].append(f"Validation error: {e}")

        return report