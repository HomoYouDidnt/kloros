"""
Automatic documentation generator for tool synthesis.

Scans spec files and generates:
- Searchable index.json
- Markdown documentation
- API reference
"""

import json
import datetime
from pathlib import Path
from typing import Dict, List, Optional


class AutoDocsGenerator:
    """
    Generate documentation from spec files.

    Scans /home/kloros/specs/ for tool specs and creates:
    - index.json: Searchable catalog of all tools
    - {tool}-{version}.md: Individual tool docs
    - README.md: Overview with table of contents
    """

    def __init__(self, spec_dir: str = "/home/kloros/specs"):
        self.spec_dir = Path(spec_dir)
        self.spec_dir.mkdir(parents=True, exist_ok=True)

    def scan_specs(self) -> List[Dict]:
        """
        Scan spec directory for tool specs.

        Returns:
            List of spec dicts
        """
        specs = []

        # Find all spec files (tool-version.json)
        for spec_file in self.spec_dir.glob("*.json"):
            # Skip index.json itself
            if spec_file.name == "index.json":
                continue

            try:
                with open(spec_file, 'r') as f:
                    spec = json.load(f)
                    spec['_file'] = spec_file.name
                    specs.append(spec)
            except Exception as e:
                print(f"Warning: Failed to parse {spec_file}: {e}")
                continue

        return specs

    def build_index(self, specs: List[Dict]) -> Dict:
        """
        Build searchable index from specs.

        Args:
            specs: List of spec dicts

        Returns:
            Index dict with metadata
        """
        index = {
            "generated_at": datetime.datetime.utcnow().isoformat() + "Z",
            "total_tools": len(specs),
            "tools": []
        }

        for spec in specs:
            tool_name = spec.get("tool", "unknown")
            version = spec.get("version", "unknown")
            manifest = spec.get("manifest", {})
            io_models = spec.get("io_models", {})

            tool_entry = {
                "name": tool_name,
                "version": version,
                "file": spec.get("_file"),
                "summary": {
                    "intent_tags": manifest.get("intent_tags", []),
                    "description": manifest.get("description", ""),
                    "has_io_models": len(io_models) > 0,
                    "has_fallbacks": len(manifest.get("fallbacks", [])) > 0,
                    "visibility": manifest.get("deployment", {}).get("visibility", "public")
                },
                "manifest": {
                    "intent_tags": manifest.get("intent_tags", []),
                    "planning": manifest.get("planning", {}),
                    "retries": manifest.get("retries", {}),
                    "fallbacks": manifest.get("fallbacks", []),
                    "permissions": manifest.get("permissions", {}),
                    "deployment": manifest.get("deployment", {}),
                    "slo": manifest.get("slo", {})
                },
                "io_models": list(io_models.keys())
            }

            index["tools"].append(tool_entry)

        # Sort by name, then version
        index["tools"].sort(key=lambda t: (t["name"], t["version"]))

        return index

    def generate_markdown(self, spec: Dict) -> str:
        """
        Generate markdown documentation for a tool.

        Args:
            spec: Spec dict

        Returns:
            Markdown string
        """
        tool_name = spec.get("tool", "unknown")
        version = spec.get("version", "unknown")
        manifest = spec.get("manifest", {})
        io_models = spec.get("io_models", {})

        md = []

        # Header
        md.append(f"# {tool_name}")
        md.append(f"**Version:** {version}\n")

        # Description
        desc = manifest.get("description", "")
        if desc:
            md.append(f"## Description\n{desc}\n")

        # Intent tags
        intent_tags = manifest.get("intent_tags", [])
        if intent_tags:
            md.append(f"## Intent Tags\n")
            for tag in intent_tags:
                md.append(f"- `{tag}`")
            md.append("")

        # When to use
        planning = manifest.get("planning", {})
        when_to_use = planning.get("when_to_use", "")
        if when_to_use:
            md.append(f"## When to Use\n{when_to_use}\n")

        # Preconditions
        preconditions = planning.get("preconditions", [])
        if preconditions:
            md.append("## Preconditions\n")
            for pre in preconditions:
                md.append(f"- {pre}")
            md.append("")

        # Postconditions
        postconditions = planning.get("postconditions", [])
        if postconditions:
            md.append("## Postconditions\n")
            for post in postconditions:
                md.append(f"- {post}")
            md.append("")

        # I/O Models
        if io_models:
            md.append("## Input/Output Models\n")
            for model_name, schema in io_models.items():
                md.append(f"### {model_name}\n")
                md.append("```json")
                md.append(json.dumps(schema, indent=2))
                md.append("```\n")

        # Fallbacks
        fallbacks = manifest.get("fallbacks", [])
        if fallbacks:
            md.append("## Fallbacks\n")
            for fb in fallbacks:
                skill = fb.get("skill", "unknown")
                md.append(f"- `{skill}`")
            md.append("")

        # Retries
        retries = manifest.get("retries", {})
        if retries:
            attempts = retries.get("attempts", 0)
            backoff = retries.get("backoff_ms", 0)
            md.append(f"## Retry Policy\n")
            md.append(f"- Attempts: {attempts}")
            md.append(f"- Backoff: {backoff}ms\n")

        # SLO
        slo = manifest.get("slo", {})
        if slo:
            md.append("## SLO Requirements\n")
            md.append(f"- Min Calls: {slo.get('min_calls', 'default')}")
            md.append(f"- p95 Latency: {slo.get('p95_latency_ms', 'default')}ms")
            md.append(f"- Max Error Rate: {slo.get('max_error_rate', 'default')}\n")

        # Permissions
        permissions = manifest.get("permissions", {})
        if permissions:
            md.append("## Permissions\n")
            network = permissions.get("network", [])
            if network:
                md.append("### Network Access")
                for domain in network:
                    md.append(f"- `{domain}`")
            filesystem = permissions.get("filesystem", [])
            if filesystem:
                md.append("### Filesystem Access")
                for path in filesystem:
                    md.append(f"- `{path}`")
            md.append("")

        # Deployment
        deployment = manifest.get("deployment", {})
        if deployment:
            md.append("## Deployment\n")
            md.append(f"- Visibility: `{deployment.get('visibility', 'public')}`")
            mask_rules = deployment.get("mask_rules", [])
            if mask_rules:
                md.append("- Mask Rules:")
                for rule in mask_rules:
                    md.append(f"  - `{rule}`")
            md.append("")

        # Footer
        md.append("---")
        md.append(f"*Generated by AutoDocsGenerator on {datetime.datetime.utcnow().isoformat()}Z*")

        return "\n".join(md)

    def generate_readme(self, specs: List[Dict]) -> str:
        """
        Generate README.md with table of contents.

        Args:
            specs: List of spec dicts

        Returns:
            Markdown string
        """
        md = []

        md.append("# Tool Synthesis Documentation\n")
        md.append(f"**Generated:** {datetime.datetime.utcnow().isoformat()}Z")
        md.append(f"**Total Tools:** {len(specs)}\n")

        md.append("## Tool Catalog\n")
        md.append("| Tool | Version | Intent Tags | I/O Models | Visibility |")
        md.append("|------|---------|-------------|------------|------------|")

        for spec in sorted(specs, key=lambda s: s.get("tool", "")):
            tool = spec.get("tool", "unknown")
            version = spec.get("version", "unknown")
            manifest = spec.get("manifest", {})
            io_models = spec.get("io_models", {})

            intent_tags = ", ".join(manifest.get("intent_tags", []))
            has_io = "✓" if io_models else ""
            visibility = manifest.get("deployment", {}).get("visibility", "public")

            md.append(f"| [{tool}]({tool}-{version}.md) | {version} | {intent_tags} | {has_io} | {visibility} |")

        md.append("")
        md.append("## Usage\n")
        md.append("See individual tool documentation for detailed usage information.")
        md.append("The `index.json` file provides a machine-readable catalog of all tools.\n")

        return "\n".join(md)

    def run(self):
        """
        Run auto-docs generation.

        Scans specs, generates index and markdown docs.
        """
        print("🔍 Scanning for tool specs...")
        specs = self.scan_specs()
        print(f"  Found {len(specs)} spec files")

        print("\n📚 Building index...")
        index = self.build_index(specs)
        index_path = self.spec_dir / "index.json"
        with open(index_path, 'w') as f:
            json.dump(index, indent=2, fp=f)
        print(f"  ✓ Wrote {index_path}")

        print("\n📝 Generating markdown docs...")
        for spec in specs:
            tool = spec.get("tool", "unknown")
            version = spec.get("version", "unknown")

            # Generate tool-specific doc
            md = self.generate_markdown(spec)
            md_path = self.spec_dir / f"{tool}-{version}.md"
            with open(md_path, 'w') as f:
                f.write(md)
            print(f"  ✓ {md_path.name}")

        # Generate README
        readme = self.generate_readme(specs)
        readme_path = self.spec_dir / "README.md"
        with open(readme_path, 'w') as f:
            f.write(readme)
        print(f"  ✓ {readme_path.name}")

        print(f"\n✅ Documentation generated successfully!")
        print(f"   Index: {index_path}")
        print(f"   Docs: {self.spec_dir}")


def main():
    """Main entry point for auto-docs generation."""
    import argparse

    parser = argparse.ArgumentParser(description="Generate tool documentation")
    parser.add_argument("--spec-dir", default="/home/kloros/specs",
                        help="Directory containing spec files")
    args = parser.parse_args()

    generator = AutoDocsGenerator(spec_dir=args.spec_dir)
    generator.run()


if __name__ == "__main__":
    main()
