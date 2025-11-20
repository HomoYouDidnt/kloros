"""
ToolGen Static Safety Checker: Detect forbidden API usage and syntax errors.

For PoC, we use simple AST inspection and string matching.
"""
import ast
from typing import Dict, Any, List

def check_code_safety(code: str, spec: Dict[str, Any]) -> Dict[str, Any]:
    """
    Perform static safety checks on generated code.
    
    Args:
        code: Python source code to check
        spec: Tool specification with constraints
    
    Returns:
        Dict with keys:
            - safe: bool (True if all checks passed)
            - violations: list of violation descriptions
    """
    violations = []
    forbidden = spec["constraints"]["forbidden_apis"]
    
    # Check forbidden API usage with simple string matching
    for api in forbidden:
        if api in code:
            violations.append(f"Forbidden API usage detected: {api}")
    
    # Check syntax
    try:
        ast.parse(code)
    except SyntaxError as e:
        violations.append(f"Syntax error: {e}")
    
    return {
        "safe": len(violations) == 0,
        "violations": violations
    }
