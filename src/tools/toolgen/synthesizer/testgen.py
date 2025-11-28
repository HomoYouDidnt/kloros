"""
ToolGen Test Generator: Generate unit and property tests from spec.

In production, would use LLM + mutation testing + property-based generators.
For PoC, we emit pytest tests covering spec test_cases.
"""
from typing import Dict, Any
import json

# Test template for text deduplication
UNIT_DEDUPE = '''import pytest
from tool import deduplicate_lines

{test_cases}

def test_determinism():
    """Property: Function must be deterministic."""
    text = "a\\nb\\na\\nc"
    r1 = deduplicate_lines(text, 0.9)
    r2 = deduplicate_lines(text, 0.9)
    assert r1 == r2

def test_no_input_mutation():
    """Property: Input must not be modified."""
    text = "original\\nline"
    original_copy = text
    deduplicate_lines(text, 0.8)
    assert text == original_copy

def test_exact_threshold_is_case_sensitive():
    """Property: Exact threshold (1.0) preserves case differences."""
    inp = "a\\na\\nA"
    result = deduplicate_lines(inp, 1.0)
    lines = result.splitlines()
    assert "a" in lines
    assert "A" in lines
    assert len([x for x in lines if x == "a"]) == 1  # Only one 'a'

def test_more_informative_wins_under_similarity():
    """Property: More informative line wins as representative."""
    inp = "alpha\\nalpha beta\\nALPHA"
    result = deduplicate_lines(inp, 0.5)  # 0.5 threshold to match Jaccard(alpha, alpha beta) = 0.5
    # "alpha beta" should win as representative (more tokens)
    assert result == "alpha beta"
'''

# Test template for json flattening
UNIT_FLATTEN = '''import pytest
from tool import flatten_json

{test_cases}

def test_determinism():
    """Property: Function must be deterministic."""
    data = {{"a": 1, "b": {{"c": 2}}}}
    r1 = flatten_json(data)
    r2 = flatten_json(data)
    assert r1 == r2

def test_no_input_mutation():
    """Property: Input must not be modified."""
    data = {{"original": 1}}
    original_copy = data.copy()
    flatten_json(data)
    assert data == original_copy

def test_empty_dict():
    """Edge case: Empty dict."""
    assert flatten_json({{}}) == {{}}

def test_single_level():
    """Edge case: Already flat dict."""
    data = {{"a": 1, "b": 2}}
    result = flatten_json(data)
    assert result == {{"a": 1, "b": 2}}
'''

def generate_tests(spec: Dict[str, Any]) -> str:
    """
    Generate pytest test suite for the tool.

    Args:
        spec: Tool specification dict

    Returns:
        Python test code as string
    """
    tool_id = spec["tool_id"]
    spec_id = spec.get("id", tool_id)
    test_cases = spec.get("test_cases", [])

    # Generate test case functions
    test_case_code = ""
    for i, tc in enumerate(test_cases):
        inputs = tc["input"]
        expected = tc["expected_output"]
        desc = tc.get("description", f"test case {i}")

        # Branch on spec type for test generation
        if "json_flatten" in spec_id:
            # JSON flatten test case
            test_case_code += f'''def test_{tool_id}_{i}():
    """Test: {desc}"""
    data = {inputs["data"]}
    result = flatten_json(data)
    assert result == {expected}, f"Expected {{repr({expected})}}, got {{repr(result)}}"

'''
        else:
            # Text deduplicate test case
            test_case_code += f'''def test_{tool_id}_{i}():
    """Test: {desc}"""
    text = {repr(inputs["text"])}
    threshold = {inputs["threshold"]}
    result = deduplicate_lines(text, threshold)
    assert result == {repr(expected)}, f"Expected {{repr({repr(expected)})}}, got {{repr(result)}}"

'''

    # Select appropriate template
    if "json_flatten" in spec_id:
        return UNIT_FLATTEN.format(test_cases=test_case_code)
    else:
        return UNIT_DEDUPE.format(test_cases=test_case_code)
