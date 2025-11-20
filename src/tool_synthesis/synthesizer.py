"""
Main tool synthesis engine for KLoROS.

Analyzes failed tool requests and generates implementations using local LLM.
"""

import json
import requests
import re
import os
import sys
from typing import Dict, List, Optional, Tuple
from datetime import datetime

from ..introspection_tools import IntrospectionTool
from .templates import ToolTemplateEngine
from .validator import ToolValidator
from .storage import SynthesizedToolStorage
from .venv_guard import create_venv_isolated_namespace, validate_tool_venv_safety

# Governance system
try:
    from .governance import SynthesisGovernance
    GOVERNANCE_AVAILABLE = True
except ImportError:
    GOVERNANCE_AVAILABLE = False
    print("[synthesis] Governance module not available - running without quarantine")


class ToolSynthesizer:
    """Main engine for autonomous tool creation."""

    def __init__(self, kloros_instance=None):
        self.kloros = kloros_instance
        self.template_engine = ToolTemplateEngine()
        self.validator = ToolValidator()
        self.storage = SynthesizedToolStorage()

        # Use code-specific model for tool synthesis
        from src.config.models_config import get_ollama_model_for_mode, get_ollama_url_for_mode
        self.model = get_ollama_model_for_mode("code")
        self.ollama_url = get_ollama_url_for_mode("code") + "/api/generate"

        # Governance system
        self.governance = SynthesisGovernance() if GOVERNANCE_AVAILABLE else None

        # Track synthesis attempts to prevent loops
        self.synthesis_attempts = {}
        self.max_attempts_per_tool = 3


    def submit_to_dream(self, tool_name: str, tool_code: str, analysis: dict, 
                       success: bool, error_msg: str = "") -> bool:
        """
        Submit synthesized tool to D-REAM for evolutionary refinement.
        
        Args:
            tool_name: Name of the synthesized tool
            tool_code: Generated code for the tool
            analysis: Tool requirements analysis
            success: Whether initial synthesis succeeded
            error_msg: Error message if synthesis failed
            
        Returns:
            True if submitted successfully to D-REAM
        """
        try:
            sys.path.insert(0, '/home/kloros/src/dream')
            from tool_dream_connector import get_tool_dream_connector
            
            # Get the real D-REAM connector
            connector = get_tool_dream_connector()
            
            # Submit tool for evolution
            submitted = connector.submit_tool_for_evolution(
                tool_name=tool_name,
                tool_code=tool_code,
                analysis=analysis,
                success=success,
                error_msg=error_msg
            )
            
            if submitted:
                print(f"[synthesis] ✅ Submitted tool '{tool_name}' to D-REAM evolution queue")
                self._log_synthesis_attempt(tool_name, "", f"submitted_to_dream_success={success}")
            else:
                print(f"[synthesis] ⚠️ Failed to submit tool '{tool_name}' to D-REAM")
                
            return submitted
            
        except Exception as e:
            print(f"[synthesis] ❌ Error submitting to D-REAM: {e}")
            return False

    def _manifest_to_analysis(self, mf: dict) -> dict:
        """
        Convert manifest to analysis dict for synthesis pipeline.

        Args:
            mf: Manifest dictionary

        Returns:
            Analysis dictionary compatible with existing synthesis flow
        """
        return {
            "purpose": mf.get("summary", ""),
            "category": ",".join(mf.get("category", [])),
            "data_sources": mf.get("permissions", {}).get("network", {}).get("allow_domains", []),
            "intent_tags": mf.get("intent_tags", []),
            "constraints": mf.get("constraints", {}),
            "planning": mf.get("planning", {}),
        }

    def capture_failed_tool_request(self, tool_name: str, context: str = "") -> bool:
        """
        Capture a failed tool request for potential synthesis.

        Args:
            tool_name: Name of the requested tool
            context: Context in which the tool was requested

        Returns:
            True if synthesis should be attempted, False otherwise
        """
        # Check if we have already attempted this tool too many times
        attempts = self.synthesis_attempts.get(tool_name, 0)
        if attempts >= self.max_attempts_per_tool:
            return False

        # Increment attempt counter
        self.synthesis_attempts[tool_name] = attempts + 1

        # Log the request
        self._log_synthesis_attempt(tool_name, context, "captured")

        return True

    def synthesize_tool(self, tool_name: str, context: str = "") -> Optional[IntrospectionTool]:
        """
        Synthesize a new tool based on name and context.

        With governance enabled, tools are quarantined and must pass promotion gates.

        Args:
            tool_name: Name of the tool to create
            context: Context in which the tool was requested

        Returns:
            IntrospectionTool instance if successful, None otherwise
        """
        try:
            # Step 1: Analyze tool requirements
            analysis = self._analyze_tool_requirements(tool_name, context)
            if not analysis:
                return None

            # Step 2: Select appropriate template
            template = self.template_engine.select_template(tool_name, analysis)
            if not template:
                return None

            # Step 3: Generate tool implementation
            tool_code = self._generate_tool_code(tool_name, analysis, template)
            if not tool_code:
                return None

            # Step 4: Validate the generated tool
            validation_report = self.validator.get_validation_report(tool_name, tool_code)
            if not validation_report.get('validation_passed', False):
                error_details = "; ".join(validation_report.get('errors', ['Unknown validation error']))
                # Submit validation failure to D-REAM for repair
                self.submit_to_dream(tool_name, tool_code, analysis, success=False,
                                   error_msg=f"Validation failed: {error_details}")
                self._log_synthesis_attempt(tool_name, context, f"validation_failed: {error_details}")
                return None

            # Step 4.5: Bridge missing methods on kloros_instance
            if self.kloros:
                from .method_bridge import MethodBridge
                bridge = MethodBridge(self.kloros)
                bridge_success, bridges_created = bridge.bridge_tool_requirements(tool_code, tool_name)

                if bridges_created:
                    print(f"[synthesis] Created {len(bridges_created)} bridges for {tool_name}")
                    for bridge_name in bridges_created:
                        print(f"[synthesis]   • {bridge_name}")
                    self._log_synthesis_attempt(tool_name, context, f"bridged: {len(bridges_created)} methods")

                if not bridge_success:
                    print(f"[synthesis] Method bridging failed for {tool_name}")
                    # Continue anyway - the tool might still work

            # Step 5: GOVERNANCE - Quarantine tool
            if self.governance:
                return self._synthesize_with_governance(
                    tool_name, tool_code, analysis, template, context
                )
            else:
                # Legacy path (no governance)
                return self._synthesize_legacy(tool_name, tool_code, analysis, context)

        except Exception as e:
            # Submit failure to D-REAM for repair attempt
            if 'analysis' in locals() and analysis:
                self.submit_to_dream(tool_name, tool_code if 'tool_code' in locals() else "",
                                   analysis, success=False, error_msg=str(e))

            self._log_synthesis_attempt(tool_name, context, f"error: {e}")
            return None

    def _synthesize_with_governance(self, tool_name: str, tool_code: str,
                                    analysis: Dict, template: str, context: str) -> Optional[IntrospectionTool]:
        """
        Synthesize tool with governance: Quarantine → Test → Promote → Register.

        Returns:
            IntrospectionTool if promoted, None if quarantined or failed
        """
        # Generate prompt for provenance
        prompt = self._reconstruct_prompt(tool_name, analysis, template)

        # Quarantine tool
        versioned_name, provenance = self.governance.quarantine_tool(
            tool_name=tool_name,
            tool_code=tool_code,
            reason=context or f"Synthesized for: {analysis.get('purpose', 'Unknown')}",
            model=self.model,
            prompt=prompt
        )

        print(f"[synthesis] Quarantined: {versioned_name} (risk={provenance.risk})")

        # Generate tests
        tests = self._generate_tool_tests(tool_name, tool_code, analysis)

        # Run tests
        test_results = self._run_tool_tests(tool_name, tests)

        # Update metadata with test results
        self.governance._update_test_results(tool_name, "0.1.0", test_results)

        # Check promotion gates
        can_promote, reasons = self.governance.check_promotion_gates(tool_name, "0.1.0")

        if not can_promote:
            print(f"[synthesis] Cannot promote {tool_name}: {', '.join(reasons)}")
            self._log_synthesis_attempt(tool_name, context, f"quarantined: {', '.join(reasons)}")

            # Submit to D-REAM for potential fixes
            self.submit_to_dream(tool_name, tool_code, analysis, success=False,
                               error_msg=f"Promotion blocked: {', '.join(reasons)}")
            return None

        # Promote tool
        promoted_version = self.governance.promote_tool(tool_name, "0.1.0")
        if not promoted_version:
            print(f"[synthesis] Promotion failed for {tool_name}")
            return None

        # Create IntrospectionTool instance
        tool = self._create_tool_instance(tool_name, analysis, tool_code)
        if not tool:
            return None

        # Store the synthesized tool
        self.storage.save_tool(tool_name, tool_code, analysis)

        # Submit to D-REAM for evolutionary refinement
        self.submit_to_dream(tool_name, tool_code, analysis, success=True)

        self._log_synthesis_attempt(tool_name, context, f"success: promoted to {promoted_version}")
        return tool

    def _synthesize_legacy(self, tool_name: str, tool_code: str,
                          analysis: Dict, context: str) -> Optional[IntrospectionTool]:
        """Legacy synthesis path without governance (for backward compatibility)."""
        # Create IntrospectionTool instance
        tool = self._create_tool_instance(tool_name, analysis, tool_code)
        if not tool:
            return None

        # Store the synthesized tool
        self.storage.save_tool(tool_name, tool_code, analysis)

        # Submit to D-REAM for evolutionary refinement
        self.submit_to_dream(tool_name, tool_code, analysis, success=True)

        self._log_synthesis_attempt(tool_name, context, "success")
        return tool

    def _analyze_tool_requirements(self, tool_name: str, context: str) -> Optional[Dict]:
        """Use LLM to analyze what the tool should do."""

        prompt = f"""Analyze this tool request and provide a JSON specification:

Tool Name: {tool_name}
Context: {context}

Based on the tool name and context, determine:
1. What the tool should accomplish
2. What data sources it needs (audio, system, memory, etc.)
3. What output format it should return
4. What category it belongs to (audio, system, user_management, utility)

Respond with ONLY a JSON object containing:
{{
    "purpose": "brief description of what the tool does",
    "category": "audio|system|user_management|utility",
    "data_sources": ["list", "of", "required", "data"],
    "output_format": "description of expected output",
    "complexity": "low|medium|high",
    "safety_level": "safe|review_required|potentially_dangerous"
}}
"""

        try:
            response = requests.post(
                self.ollama_url,
                json={
                    "model": self.model,
                    "prompt": prompt,
                    "stream": False,
                    "options": {"temperature": 0.3}
                },
                timeout=30
            )

            if response.status_code == 200:
                llm_response = response.json().get("response", "").strip()

                # Extract JSON from response
                json_match = re.search(r'{.*}', llm_response, re.DOTALL)
                if json_match:
                    return json.loads(json_match.group(0))

        except Exception:
            pass

        return None

    def _generate_tool_code(self, tool_name: str, analysis: Dict, template: Dict) -> Optional[str]:
        """Generate Python code for the tool using LLM."""

        # Sanitize tool name: extract base name before parameters and remove invalid chars
        # Handle cases like "check_errors parameters: {...}"
        base_name = tool_name.split(' parameters:')[0] if ' parameters:' in tool_name else tool_name

        # Replace invalid Python identifier characters with underscores
        # Keep only alphanumeric and underscores, replace everything else
        safe_name = re.sub(r'[^a-zA-Z0-9_]', '_', base_name)

        # Remove consecutive underscores and leading/trailing underscores
        safe_name = re.sub(r'_+', '_', safe_name).strip('_')

        # Ensure doesn't start with digit
        if safe_name and safe_name[0].isdigit():
            safe_name = f'tool_{safe_name}'

        prompt = f"""Generate a Python function for a KLoROS introspection tool:

Tool Name: {tool_name}
Purpose: {analysis.get('purpose', '')}
Category: {analysis.get('category', '')}
Data Sources: {analysis.get('data_sources', [])}
Template: {template.get('name', 'basic')}

Requirements:
1. Function should be named: tool_{safe_name}
2. Function signature: def tool_{safe_name}(kloros_instance, **kwargs) -> str:
3. Return string result, never raise exceptions
4. Use try/except blocks for ALL attribute access and operations
5. Access KLoROS data through kloros_instance parameter
6. Maintain KLoROS personality in responses
7. IMPORTANT: Always check hasattr() before accessing attributes

Available on StandaloneKLoROS (kloros_instance):
- kloros_instance.conversation_history (list) - conversation turns
- kloros_instance.reason_backend (LocalRagBackend) - reasoning system
- kloros_instance.memory_enhanced (MemoryEnhancedKLoROS or None) - memory wrapper if enabled
- kloros_instance.chat(message) (method) - main chat interface

To access tools: Use introspection tool registry, NOT kloros_instance.tool_registry
To access memory: Check if kloros_instance.memory_enhanced exists first
To access system info: Use os, platform, subprocess modules safely

DO NOT assume these exist (they don't on StandaloneKLoROS):
- audio_backend, stt_backend, tts_backend (voice mode only)
- tool_registry (use IntrospectionToolRegistry instead)
- conversation_flow, enrollment_mode (voice mode only)
- memory, database (use memory_enhanced.memory_store if available)

Pattern for safe attribute access:
if hasattr(kloros_instance, 'attribute_name') and kloros_instance.attribute_name:
    # use attribute
else:
    return "Feature not available in current mode"

Template guidance: {template.get('implementation_guide', '')}

Generate ONLY the Python function, no explanations or markdown:
"""

        try:
            response = requests.post(
                self.ollama_url,
                json={
                    "model": self.model,
                    "prompt": prompt,
                    "stream": False,
                    "options": {"temperature": 0.2}
                },
                timeout=60
            )

            if response.status_code == 200:
                code = response.json().get("response", "").strip()

                # Clean up the code
                code = self._clean_generated_code(code)
                return code

        except Exception:
            pass

        return None

    def _clean_generated_code(self, code: str) -> str:
        """Clean and format generated code."""

        # Remove markdown code blocks
        code = re.sub(r'```python\n?', '', code)
        code = re.sub(r'\n?```', '', code)

        # Ensure proper indentation
        lines = code.split('\n')
        cleaned_lines = []

        for line in lines:
            if line.strip():
                cleaned_lines.append(line)

        return '\n'.join(cleaned_lines)

    def _create_tool_instance(self, tool_name: str, analysis: Dict, tool_code: str) -> Optional[IntrospectionTool]:
        """Create an IntrospectionTool instance from generated code."""

        try:
            # Validate venv safety first
            is_safe, safety_msg = validate_tool_venv_safety(tool_code)
            if not is_safe:
                print(f"[synthesis] Tool '{tool_name}' failed venv safety check: {safety_msg}")
                return None

            # Create venv-isolated namespace for execution
            venv_namespace = create_venv_isolated_namespace()

            # Execute the generated code with venv protection
            exec(tool_code, venv_namespace)

            # Find the tool function
            func_name = f"tool_{tool_name.replace('-', '_').replace(' ', '_')}"
            if func_name not in venv_namespace:
                return None

            tool_func = venv_namespace[func_name]

            # Create the IntrospectionTool
            return IntrospectionTool(
                name=tool_name,
                description=analysis.get('purpose', f"Synthesized tool: {tool_name}"),
                func=tool_func,
                parameters=[]
            )

        except Exception:
            return None

    def _log_synthesis_attempt(self, tool_name: str, context: str, status: str):
        """Log synthesis attempts for debugging and analysis."""

        log_entry = {
            "timestamp": datetime.now().isoformat(),
            "tool_name": tool_name,
            "context": context[:200] if context else "",
            "status": status,
            "attempt_count": self.synthesis_attempts.get(tool_name, 0)
        }

        # Log to KLoROS event system if available
        if self.kloros and hasattr(self.kloros, 'log_event'):
            try:
                self.kloros.log_event("tool_synthesis", **log_entry)
            except:
                pass

        # Also log to synthesis log file
        log_file = "/home/kloros/.kloros/tool_synthesis.log"
        try:
            os.makedirs(os.path.dirname(log_file), exist_ok=True)
            with open(log_file, 'a') as f:
                f.write(json.dumps(log_entry) + '\n')
        except:
            pass

    def get_synthesis_stats(self) -> Dict:
        """Get statistics about tool synthesis attempts."""

        stats = {
            "total_attempts": sum(self.synthesis_attempts.values()),
            "unique_tools_attempted": len(self.synthesis_attempts),
            "tools_by_attempt_count": dict(self.synthesis_attempts),
            "storage_stats": self.storage.get_stats()
        }

        # Add governance stats if available
        if self.governance:
            stats["quarantined_tools"] = len(self.governance.list_quarantined_tools())
            stats["governance_enabled"] = True
        else:
            stats["governance_enabled"] = False

        return stats

    def _reconstruct_prompt(self, tool_name: str, analysis: Dict, template: str) -> str:
        """Reconstruct synthesis prompt for provenance tracking."""
        return f"""Tool: {tool_name}
Purpose: {analysis.get('purpose', 'Unknown')}
Category: {analysis.get('category', 'utility')}
Data Sources: {', '.join(analysis.get('data_sources', []))}
Template: {template}"""

    def _generate_tool_tests(self, tool_name: str, tool_code: str, analysis: Dict) -> Dict[str, str]:
        """
        Generate test suite for synthesized tool.

        Returns:
            Dict with 'unit', 'contract', and 'e2e' test code
        """
        tests = {}

        # Unit test (basic validation)
        tests['unit'] = self._generate_unit_test(tool_name, tool_code, analysis)

        # Contract test (protocol compliance)
        tests['contract'] = self._generate_contract_test(tool_name)

        # E2E test (scenario-based)
        tests['e2e'] = self._generate_e2e_test(tool_name, analysis)

        return tests

    def _generate_unit_test(self, tool_name: str, tool_code: str, analysis: Dict) -> str:
        """Generate basic unit test."""
        return f"""#!/usr/bin/env python3
\"\"\"Unit test for {tool_name}\"\"\"
import pytest

def test_{tool_name}_exists():
    '''Test that {tool_name} function exists'''
    import sys
    sys.path.insert(0, '/home/kloros')
    from src.introspection_tools import IntrospectionToolRegistry

    registry = IntrospectionToolRegistry()
    assert '{tool_name}' in registry.tools

def test_{tool_name}_returns_string():
    '''Test that {tool_name} returns a string'''
    import sys
    sys.path.insert(0, '/home/kloros')
    from src.introspection_tools import IntrospectionToolRegistry

    registry = IntrospectionToolRegistry()
    tool = registry.get_tool('{tool_name}')

    if tool:
        # Create mock kloros instance
        class MockKLoROS:
            pass

        result = tool.execute(MockKLoROS())
        assert isinstance(result, str), f"Tool returned {{type(result)}}, expected str"
"""

    def _generate_contract_test(self, tool_name: str) -> str:
        """Generate contract test (protocol compliance)."""
        return f"""#!/usr/bin/env python3
\"\"\"Contract test for {tool_name}\"\"\"
import pytest

def test_{tool_name}_protocol_compliance():
    '''Test that {tool_name} follows IntrospectionTool protocol'''
    import sys
    sys.path.insert(0, '/home/kloros')
    from src.introspection_tools import IntrospectionToolRegistry

    registry = IntrospectionToolRegistry()
    tool = registry.get_tool('{tool_name}')

    assert tool is not None, "Tool not found in registry"
    assert hasattr(tool, 'name'), "Tool missing 'name' attribute"
    assert hasattr(tool, 'description'), "Tool missing 'description' attribute"
    assert hasattr(tool, 'execute'), "Tool missing 'execute' method"
    assert callable(tool.execute), "Tool execute must be callable"
"""

    def _generate_e2e_test(self, tool_name: str, analysis: Dict) -> str:
        """Generate E2E test scenario (YAML format for harness)."""
        purpose = analysis.get('purpose', f'Test {tool_name}')
        category = analysis.get('category', 'utility')

        return f"""name: "E2E Test: {tool_name}"
description: "{purpose}"
tags: [synthesis, {category}, quarantine]

steps:
  - say: "Use {tool_name}"

expect:
  tool_called: "{tool_name}"
  tool_result_not_empty: true
  no_errors: true

promotion_policy:
  risk: "medium"
  require_shadow: false
  require_tests: true
"""

    def _run_tool_tests(self, tool_name: str, tests: Dict[str, str]) -> Dict[str, str]:
        """
        Run generated tests and return results.

        Returns:
            Dict mapping test type to result ('pass', 'fail', 'skip')
        """
        import subprocess
        import textwrap
        from pathlib import Path

        results = {}
        base = Path(f"/tmp/kloros_tool_tests/{tool_name}")
        base.mkdir(parents=True, exist_ok=True)

        for test_name, test_code in tests.items():
            tf = base / f"test_{test_name}.py"
            tf.write_text(textwrap.dedent(test_code))

            try:
                proc = subprocess.run(
                    ["pytest", "-q", str(tf)],
                    capture_output=True,
                    text=True,
                    timeout=60
                )
                results[test_name] = "pass" if proc.returncode == 0 else "fail"
            except subprocess.TimeoutExpired:
                results[test_name] = "fail"
            except Exception as e:
                print(f"[test] Error running {test_name}: {e}")
                results[test_name] = "fail"

        return results