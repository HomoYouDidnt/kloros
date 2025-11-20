#!/usr/bin/env python3
"""
TestForge Synthesizer - Generates new test templates using LLM.

Enables KLoROS to create novel test types for D-REAM evolution.
"""

import json
import yaml
import re
from pathlib import Path
from typing import Optional, Dict, List
from datetime import datetime

try:
    import tomllib
except ImportError:
    import tomli as tomllib


class TestTemplateSynthesizer:
    """Synthesize new test templates using coder model."""

    def __init__(self):
        """Initialize synthesizer with coder model."""
        # Load model config
        config_path = Path(__file__).parents[3] / "config" / "models.toml"
        with open(config_path, "rb") as f:
            models = tomllib.load(f)

        self.model = models["llm"]["ollama"]["model"]
        self.ollama_url = models["llm"]["ollama"]["url"]
        self.templates_dir = Path(__file__).parent.parent / "templates"
        self.templates_dir.mkdir(exist_ok=True)

    def synthesize_test_template(self, test_type: str, description: str,
                                 example_code: Optional[str] = None) -> Optional[Dict]:
        """
        Synthesize a new test template.

        Args:
            test_type: Type of test (e.g., "performance", "security", "concurrency")
            description: What the test should validate
            example_code: Optional example code to test against

        Returns:
            Template dictionary if successful, None otherwise
        """
        import requests

        # Build prompt for template generation
        prompt = f"""Generate a D-REAM test template for: {test_type}

Description: {description}

Requirements:
1. YAML format with these sections:
   - family: Test family name (e.g., "{test_type}.core")
   - payload: What changes to make (type, symbols, description)
   - base: Base constraints (diff_limit, max_files_changed, etc.)
   - slots: Variable slots for randomization (optional)
   - mutators: How to adapt constraints (stricter_diff, relax_diff)
   - expected: Expected outcomes (tests_pass, no_crashes, etc.)

2. Payload types available:
   - symbol_rename: Rename symbols
   - add_validation: Add input validation
   - optimize_algorithm: Optimize performance
   - add_concurrency: Add thread safety
   - refactor_structure: Restructure code

3. Mutators should trigger on last_passed_true/false

Example existing template:
```yaml
family: bugfix.core
payload:
  type: symbol_rename
  symbols:
    old: divide
    new: safe_divide
base:
  diff_limit: 60
  max_files_changed: 6
mutators:
  - type: stricter_diff
    trigger: last_passed_false
    action: reduce_diff_limit
    factor: 0.8
expected:
  tests_pass: true
```

Generate complete YAML template for {test_type}:"""

        if example_code:
            prompt += f"\n\nExample code to test:\n```python\n{example_code}\n```"

        try:
            # Call coder model
            response = requests.post(
                f"{self.ollama_url}/api/generate",
                json={
                    "model": self.model,
                    "prompt": prompt,
                    "stream": False,
                    "options": {"temperature": 0.3}
                },
                timeout=60
            )

            if response.status_code != 200:
                print(f"[testforge] LLM request failed: {response.status_code}")
                return None

            llm_output = response.json().get("response", "").strip()

            # Extract YAML from response
            yaml_content = self._extract_yaml(llm_output)
            if not yaml_content:
                print("[testforge] Failed to extract YAML from LLM response")
                return None

            # Parse and validate template
            template = yaml.safe_load(yaml_content)
            if self._validate_template(template):
                return template
            else:
                print("[testforge] Template validation failed")
                return None

        except Exception as e:
            print(f"[testforge] Synthesis failed: {e}")
            return None

    def _extract_yaml(self, text: str) -> Optional[str]:
        """Extract YAML content from LLM response."""
        # Try to find YAML code block
        yaml_match = re.search(r'```yaml\n(.*?)\n```', text, re.DOTALL)
        if yaml_match:
            return yaml_match.group(1)

        # Try to find any code block
        code_match = re.search(r'```\n(.*?)\n```', text, re.DOTALL)
        if code_match:
            return code_match.group(1)

        # Assume entire response is YAML
        return text

    def _validate_template(self, template: Dict) -> bool:
        """Validate template structure."""
        required_keys = ["family", "payload", "base", "expected"]

        for key in required_keys:
            if key not in template:
                print(f"[testforge] Missing required key: {key}")
                return False

        # Validate payload
        payload = template.get("payload", {})
        if "type" not in payload:
            print("[testforge] Payload missing 'type'")
            return False

        # Validate base constraints
        base = template.get("base", {})
        if "diff_limit" not in base:
            print("[testforge] Base missing 'diff_limit'")
            return False

        return True

    def save_template(self, template: Dict, filename: Optional[str] = None) -> Path:
        """Save template to file."""
        if not filename:
            family = template["family"].replace(".", "_")
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            filename = f"{family}_{timestamp}.yaml"

        filepath = self.templates_dir / filename
        with open(filepath, 'w') as f:
            yaml.dump(template, f, default_flow_style=False, sort_keys=False)

        print(f"[testforge] Saved template: {filepath}")
        return filepath

    def list_templates(self) -> List[Path]:
        """List all available templates."""
        return sorted(self.templates_dir.glob("*.yaml"))

    def synthesize_test_family(self, family_name: str, test_types: List[str],
                               description: str) -> List[Dict]:
        """
        Synthesize multiple related test templates.

        Args:
            family_name: Family name (e.g., "performance")
            test_types: List of test types to create
            description: Overall family description

        Returns:
            List of synthesized templates
        """
        templates = []

        for test_type in test_types:
            print(f"[testforge] Synthesizing: {family_name}.{test_type}")

            template = self.synthesize_test_template(
                test_type=f"{family_name}.{test_type}",
                description=f"{description} - {test_type} variant"
            )

            if template:
                templates.append(template)
                self.save_template(template)

        return templates


# Singleton instance
_synthesizer_instance = None

def get_test_synthesizer() -> TestTemplateSynthesizer:
    """Get singleton synthesizer instance."""
    global _synthesizer_instance
    if _synthesizer_instance is None:
        _synthesizer_instance = TestTemplateSynthesizer()
    return _synthesizer_instance


# CLI for manual test synthesis
if __name__ == "__main__":
    import sys

    synthesizer = get_test_synthesizer()

    if len(sys.argv) < 3:
        print("Usage: python synthesizer.py <test_type> <description>")
        print("\nExample:")
        print("  python synthesizer.py performance 'Add caching to improve lookup speed'")
        sys.exit(1)

    test_type = sys.argv[1]
    description = sys.argv[2]
    example_code = sys.argv[3] if len(sys.argv) > 3 else None

    print(f"[testforge] Synthesizing test template: {test_type}")
    template = synthesizer.synthesize_test_template(test_type, description, example_code)

    if template:
        filepath = synthesizer.save_template(template)
        print(f"\n✅ Template created: {filepath}")
        print(f"\nTemplate content:")
        print(yaml.dump(template, default_flow_style=False, sort_keys=False))
    else:
        print("\n❌ Failed to synthesize template")
        sys.exit(1)
