"""
Capability documentation generator with drift detection.

Reads capabilities_enhanced.yaml and generates markdown documentation for each
capability with drift detection against the indexed modules in index.json.
"""

import json
import re
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Tuple

import yaml


class DriftDetector:
    """Detects drift between capability preconditions and indexed modules."""

    def __init__(self, index: Dict[str, Any]):
        """Initialize the drift detector.

        Args:
            index: The modules index from index.json
        """
        self.modules = index.get("modules", {})
        self.module_ids = set(self.modules.keys())

    def detect_drift(self, preconditions: List[str]) -> Tuple[str, List[str]]:
        """Detect drift for a capability's preconditions.

        Args:
            preconditions: List of precondition strings (e.g., "path:...", "module:...")

        Returns:
            Tuple of (drift_status, drift_details) where drift_status is one of:
            - "ok": all preconditions satisfied
            - "missing_module": referenced module not found in index
            - "mismatch": other inconsistencies
        """
        drift_details = []

        for precond in preconditions:
            precond = precond.strip()

            if precond.startswith("module:"):
                module_ref = precond.replace("module:", "").strip()
                module_id = module_ref.split()[0]

                if module_id not in self.module_ids:
                    drift_details.append(
                        f"Module '{module_id}' referenced but not found in index"
                    )

            elif precond.startswith("path:"):
                pass

            elif precond.startswith("group:"):
                pass

            elif precond.startswith("command:"):
                pass

            elif precond.startswith("http:"):
                pass

            elif not any(
                precond.startswith(prefix)
                for prefix in ["module:", "path:", "group:", "command:", "http:"]
            ):
                if ":" in precond and not precond.startswith(
                    ("pipewire_session", "audio.input", "audio.output")
                ):
                    drift_details.append(f"Unknown precondition format: '{precond}'")

        if drift_details:
            return "missing_module" if "Module" in drift_details[0] else "mismatch", drift_details
        return "ok", []


class CapabilityDocgen:
    """Generates capability documentation with drift detection."""

    def __init__(self, yaml_path: str, index_path: str, output_dir: str):
        """Initialize the capability documentation generator.

        Args:
            yaml_path: Path to capabilities_enhanced.yaml
            index_path: Path to index.json
            output_dir: Directory to write capability markdown files
        """
        self.yaml_path = Path(yaml_path)
        self.index_path = Path(index_path)
        self.output_dir = Path(output_dir)
        self.capabilities = []
        self.index = {}
        self.drift_detector = None

    def load_capabilities(self) -> List[Dict[str, Any]]:
        """Load capabilities from YAML file.

        Returns:
            List of capability dictionaries
        """
        with open(self.yaml_path, "r") as f:
            self.capabilities = yaml.safe_load(f) or []
        return self.capabilities

    def load_index(self) -> Dict[str, Any]:
        """Load the modules index from index.json.

        Returns:
            Index dictionary
        """
        with open(self.index_path, "r") as f:
            self.index = json.load(f)
        self.drift_detector = DriftDetector(self.index)
        return self.index

    def format_frontmatter(self, capability: Dict[str, Any], drift_status: str) -> str:
        """Generate YAML frontmatter for a capability markdown file.

        Args:
            capability: Capability dictionary
            drift_status: Drift status from detection

        Returns:
            YAML frontmatter string
        """
        timestamp = datetime.now().isoformat()
        enabled = capability.get("enabled", False)
        status = "enabled" if enabled else "disabled"

        frontmatter = {
            "doc_type": "capability",
            "capability_id": capability.get("key"),
            "status": status,
            "last_updated": timestamp,
            "drift_status": drift_status,
        }

        yaml_str = yaml.dump(frontmatter, default_flow_style=False, sort_keys=False)
        return f"---\n{yaml_str}---\n"

    def extract_module_references(self, preconditions: List[str]) -> List[str]:
        """Extract module IDs from preconditions.

        Args:
            preconditions: List of precondition strings

        Returns:
            List of module IDs referenced
        """
        module_refs = []
        for precond in preconditions:
            if precond.startswith("module:"):
                module_ref = precond.replace("module:", "").strip()
                module_id = module_ref.split()[0]
                module_refs.append(module_id)
        return module_refs

    def generate_purpose_section(self, capability: Dict[str, Any]) -> str:
        """Generate the Purpose section of capability documentation.

        Args:
            capability: Capability dictionary

        Returns:
            Markdown section
        """
        provides = capability.get("provides", [])
        kind = capability.get("kind", "unknown")

        section = "## Purpose\n\n"
        section += f"Provides: {', '.join(provides)}\n\n"
        section += f"Kind: {kind}\n"

        return section

    def generate_scope_section(self, capability: Dict[str, Any]) -> str:
        """Generate the Scope section of capability documentation.

        Args:
            capability: Capability dictionary

        Returns:
            Markdown section
        """
        docs = capability.get("docs", "")
        tests = capability.get("tests", [])

        section = "## Scope\n\n"

        if docs:
            section += f"Documentation: {docs}\n\n"

        if tests:
            section += f"Tests:\n"
            for test in tests:
                section += f"- {test}\n"
        else:
            section += "Tests: None\n"

        section += "\n"
        return section

    def generate_implementations_section(
        self, preconditions: List[str], module_refs: List[str]
    ) -> str:
        """Generate the Implementations section of capability documentation.

        Args:
            preconditions: List of precondition strings
            module_refs: List of referenced module IDs

        Returns:
            Markdown section
        """
        section = "## Implementations\n\n"

        if module_refs:
            section += "Referenced modules:\n"
            for module_id in module_refs:
                if module_id in self.index.get("modules", {}):
                    module = self.index["modules"][module_id]
                    code_paths = module.get("code_paths", [])
                    section += f"\n### {module_id}\n"
                    for path in code_paths:
                        section += f"- {path}\n"
                else:
                    section += f"\n### {module_id} (NOT FOUND)\n"
            section += "\n"
        else:
            section += "No module dependencies.\n\n"

        section += "Preconditions:\n"
        for precond in preconditions:
            section += f"- {precond}\n"

        section += "\n"
        return section

    def generate_telemetry_section(self, capability: Dict[str, Any]) -> str:
        """Generate the Telemetry section of capability documentation.

        Args:
            capability: Capability dictionary

        Returns:
            Markdown section
        """
        section = "## Telemetry\n\n"

        health_check = capability.get("health_check", "")
        if health_check:
            section += f"Health check: `{health_check}`\n\n"

        cost = capability.get("cost", {})
        if cost:
            section += "Cost:\n"
            section += f"- CPU: {cost.get('cpu', 'N/A')}\n"
            section += f"- Memory: {cost.get('mem', 'N/A')} MB\n"
            section += f"- Risk: {cost.get('risk', 'unknown')}\n"
            section += "\n"

        return section

    def generate_drift_section(self, drift_status: str, drift_details: List[str]) -> str:
        """Generate the Drift Status section of capability documentation.

        Args:
            drift_status: Drift status
            drift_details: List of drift detail messages

        Returns:
            Markdown section
        """
        section = "## Drift Status\n\n"

        status_msgs = {
            "ok": "All preconditions are satisfied. Module dependencies are available in index.",
            "missing_module": "One or more required modules are not found in the index.",
            "mismatch": "Inconsistencies detected in preconditions or module references.",
        }

        section += f"**Status:** {drift_status.upper()}\n\n"
        section += status_msgs.get(drift_status, "Unknown status")
        section += "\n"

        if drift_details:
            section += "\nDetails:\n"
            for detail in drift_details:
                section += f"- {detail}\n"
            section += "\n"

        return section

    def generate_markdown(self, capability: Dict[str, Any], drift_status: str, drift_details: List[str]) -> str:
        """Generate complete markdown documentation for a capability.

        Args:
            capability: Capability dictionary
            drift_status: Drift status
            drift_details: List of drift detail messages

        Returns:
            Complete markdown content
        """
        frontmatter = self.format_frontmatter(capability, drift_status)
        preconditions = capability.get("preconditions", [])
        module_refs = self.extract_module_references(preconditions)

        markdown = frontmatter
        markdown += f"# {capability.get('key', 'Unknown Capability')}\n\n"
        markdown += self.generate_purpose_section(capability)
        markdown += self.generate_scope_section(capability)
        markdown += self.generate_implementations_section(preconditions, module_refs)
        markdown += self.generate_telemetry_section(capability)
        markdown += self.generate_drift_section(drift_status, drift_details)

        return markdown

    def generate_capability_pages(self) -> Dict[str, str]:
        """Generate markdown files for all capabilities.

        Returns:
            Dictionary mapping capability_id to drift_status
        """
        self.output_dir.mkdir(parents=True, exist_ok=True)
        drift_report = {}

        for capability in self.capabilities:
            capability_id = capability.get("key")
            if not capability_id:
                continue

            preconditions = capability.get("preconditions", [])
            drift_status, drift_details = self.drift_detector.detect_drift(preconditions)

            markdown = self.generate_markdown(capability, drift_status, drift_details)

            output_path = self.output_dir / f"{capability_id}.md"
            with open(output_path, "w") as f:
                f.write(markdown)

            drift_report[capability_id] = drift_status

        return drift_report

    def run(self) -> Dict[str, str]:
        """Run the capability documentation generator.

        Returns:
            Dictionary mapping capability_id to drift_status
        """
        self.load_capabilities()
        self.load_index()
        drift_report = self.generate_capability_pages()
        return drift_report


def main() -> None:
    """Main entry point for the capability documentation generator CLI."""
    yaml_path = "/home/kloros/src/registry/capabilities_enhanced.yaml"
    index_path = "/home/kloros/wiki/index.json"
    output_dir = "/home/kloros/wiki/capabilities"

    docgen = CapabilityDocgen(yaml_path, index_path, output_dir)
    drift_report = docgen.run()

    capability_count = len(drift_report)
    ok_count = sum(1 for status in drift_report.values() if status == "ok")
    missing_count = sum(1 for status in drift_report.values() if status == "missing_module")
    mismatch_count = sum(1 for status in drift_report.values() if status == "mismatch")

    print("Capability documentation generation completed successfully")
    print(f"  Capabilities documented: {capability_count}")
    print(f"  Drift status OK: {ok_count}")
    print(f"  Missing modules: {missing_count}")
    print(f"  Mismatches: {mismatch_count}")
    print(f"  Output directory: {output_dir}")

    if missing_count > 0 or mismatch_count > 0:
        print("\nCapabilities with drift:")
        for cap_id, status in sorted(drift_report.items()):
            if status != "ok":
                print(f"  - {cap_id}: {status}")


if __name__ == "__main__":
    main()
