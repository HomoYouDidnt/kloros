"""
Manifest loader and validator for skill authoring template system.

Loads YAML manifests and validates against JSON Schema.
"""

import yaml
import json
import jsonschema
from pathlib import Path


_SCHEMA_PATH = Path("/home/kloros/src/tool_synthesis/skills/_schema/manifest.schema.json")


class ManifestLoader:
    """Load and validate skill manifests."""

    def load(self, path: str) -> dict:
        """
        Load and validate a skill manifest.

        Args:
            path: Path to manifest YAML file

        Returns:
            Validated manifest dict

        Raises:
            jsonschema.ValidationError: If manifest is invalid
            FileNotFoundError: If manifest file not found
        """
        manifest_path = Path(path)
        if not manifest_path.exists():
            raise FileNotFoundError(f"Manifest not found: {path}")

        # Load YAML
        doc = yaml.safe_load(manifest_path.read_text())

        # Load schema
        schema = json.loads(_SCHEMA_PATH.read_text())

        # Validate
        jsonschema.validate(instance=doc, schema=schema)

        return doc
