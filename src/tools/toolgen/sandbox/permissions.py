"""
ToolGen Permission Validator: Ensure tool capabilities are declared.

For PoC, we perform basic capability checking.
"""
from typing import Dict, Any

def validate_permissions(spec: Dict[str, Any], code: str) -> Dict[str, Any]:
    """
    Validate that tool declares required capabilities.
    
    Args:
        spec: Tool specification
        code: Generated Python code
    
    Returns:
        Dict with keys:
            - valid: bool
            - warnings: list of permission warnings
    """
    warnings = []
    
    # Check for file I/O
    if "open(" in code or "Path(" in code:
        if "file_io" not in spec.get("capabilities", []):
            warnings.append("File I/O detected but not declared in capabilities")
    
    # Check for network access
    if "requests." in code or "urllib" in code or "socket" in code:
        if "network" not in spec.get("capabilities", []):
            warnings.append("Network access detected but not declared in capabilities")
    
    return {
        "valid": len(warnings) == 0,
        "warnings": warnings
    }
