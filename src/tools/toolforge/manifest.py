"""Tool manifest definitions."""
from dataclasses import dataclass, field
from typing import Dict, Any, List, Optional
import yaml


@dataclass
class ToolManifest:
    """Manifest describing a tool for synthesis and deployment."""

    name: str
    version: str
    owner: str
    purpose: str

    # JSON schemas
    input_schema: Dict[str, Any]
    output_schema: Dict[str, Any]

    # Policies
    policies: Dict[str, Any] = field(default_factory=dict)

    # Tests
    tests: Dict[str, List[Dict[str, Any]]] = field(default_factory=dict)

    # Risk classification
    risk: str = "medium"  # low, medium, high

    # Metadata
    metadata: Dict[str, Any] = field(default_factory=dict)

    @classmethod
    def from_yaml(cls, yaml_path: str) -> 'ToolManifest':
        """Load manifest from YAML file.

        Args:
            yaml_path: Path to YAML manifest

        Returns:
            ToolManifest instance
        """
        with open(yaml_path, "r", encoding="utf-8") as f:
            data = yaml.safe_load(f)

        # Extract signature
        signature = data.get("signature", {})

        return cls(
            name=data["name"],
            version=data["version"],
            owner=data["owner"],
            purpose=data["purpose"],
            input_schema=signature.get("input_schema", {}),
            output_schema=signature.get("output_schema", {}),
            policies=data.get("policies", {}),
            tests=data.get("tests", {}),
            risk=data.get("risk", "medium"),
            metadata=data.get("metadata", {})
        )

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary.

        Returns:
            Dict representation
        """
        return {
            "name": self.name,
            "version": self.version,
            "owner": self.owner,
            "purpose": self.purpose,
            "signature": {
                "input_schema": self.input_schema,
                "output_schema": self.output_schema
            },
            "policies": self.policies,
            "tests": self.tests,
            "risk": self.risk,
            "metadata": self.metadata
        }

    def to_yaml(self, yaml_path: str):
        """Save manifest to YAML file.

        Args:
            yaml_path: Output path
        """
        with open(yaml_path, "w", encoding="utf-8") as f:
            yaml.dump(self.to_dict(), f, default_flow_style=False)

    def get_policy(self, policy_name: str, default: Any = None) -> Any:
        """Get policy value.

        Args:
            policy_name: Policy key
            default: Default value if not found

        Returns:
            Policy value
        """
        return self.policies.get(policy_name, default)
