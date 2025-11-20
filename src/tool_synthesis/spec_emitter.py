"""
Spec emission for Spec-GroundTruth compliance.

Emits spec_model.json for each promoted tool with full specifications.
"""

from pathlib import Path
import json


def emit_spec(
    tool_name: str,
    version: str,
    manifest: dict | None = None,
    io_models: dict | None = None
) -> None:
    """
    Emit spec JSON for a tool.

    Args:
        tool_name: Tool name
        version: Tool version
        manifest: Optional manifest dict
        io_models: Optional dict of Pydantic models

    Output:
        /home/kloros/specs/{tool_name}-{version}.json
    """
    out = {
        "tool": tool_name,
        "version": version,
        "manifest": manifest or {},
        "io_models": {}
    }

    # Extract Pydantic schema if available
    if io_models:
        for k, v in io_models.items():
            try:
                out["io_models"][k] = v.model_json_schema()
            except Exception:
                out["io_models"][k] = {}

    # Write to specs directory
    spec_path = Path(f"/home/kloros/specs/{tool_name}-{version}.json")
    spec_path.parent.mkdir(parents=True, exist_ok=True)
    spec_path.write_text(json.dumps(out, indent=2))
