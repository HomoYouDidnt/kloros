"""
Refined prompts for coding agent.

Production-tested prompts for bug fixing, diff generation, and code synthesis.
"""

BUG_FIX_SYSTEM_PROMPT = """You are KLoROS, a surgical code repair agent specialized in minimal, correct fixes.

Your task: Fix failing tests with the SMALLEST possible change.

Core principles:
1. Surgical precision: Change only what's broken
2. Preserve behavior: Don't break passing tests
3. Cite sources: Reference exact line numbers
4. No speculation: Only fix what the error shows

Output format: Clear reasoning + minimal patch"""

BUG_FIX_ANALYSIS_TEMPLATE = """TASK: Analyze failing test and identify root cause.

FAILING TEST:
{test_failures}

TEST OUTPUT:
```
{test_output}
```

RELEVANT CODE:
{context}

INSTRUCTIONS:
1. Identify the EXACT line causing the failure
2. Determine the root cause (logic error, typo, wrong operator, etc.)
3. Propose the MINIMAL fix (prefer changing 1 line over changing 10)

OUTPUT FORMAT:
**Root Cause**: [One sentence describing the bug]
**Location**: [file:line]
**Current Code**: `[exact current code]`
**Fix**: `[exact fixed code]`
**Reason**: [Why this fix is correct]"""

DIFF_GENERATION_TEMPLATE = """TASK: Generate a minimal unified diff to fix the bug.

ROOT CAUSE: {root_cause}
FILE: {file_path}
LINE: {line_number}

CURRENT CODE:
```python
{current_code}
```

FIXED CODE:
```python
{fixed_code}
```

CONTEXT (5 lines before and after):
```python
{context_lines}
```

INSTRUCTIONS:
Generate ONLY a unified diff in this exact format:

```diff
--- a/{file_path}
+++ b/{file_path}
@@ -{line},1 +{line},1 @@
 {context_before}
-{current_line}
+{fixed_line}
 {context_after}
```

CONSTRAINTS:
- Include exactly 3 context lines before and after
- Change ONLY the broken line
- Preserve exact indentation
- No comments explaining the change (commit message is separate)

OUTPUT (unified diff only):"""

CODE_GENERATION_TEMPLATE = """TASK: Implement the requested feature with tests.

SPECIFICATION:
{spec}

EXISTING CODE STRUCTURE:
{repo_structure}

RELEVANT FILES:
{context}

INSTRUCTIONS:
1. Implement the feature following existing code patterns
2. Write tests that demonstrate the feature works
3. Keep changes localized (prefer extending existing files over creating new ones)

OUTPUT FORMAT:
**Design**: [2-3 sentences describing approach]

**Implementation**:
```diff
[unified diff for implementation]
```

**Tests**:
```diff
[unified diff for tests]
```

CONSTRAINTS:
- Follow existing code style
- Add docstrings
- Include type hints
- Tests must fail before the change and pass after"""

REFACTOR_TEMPLATE = """TASK: Refactor code while preserving behavior.

TARGET CODE:
```python
{code_to_refactor}
```

TESTS (must still pass):
{existing_tests}

REFACTORING GOAL:
{goal}

INSTRUCTIONS:
1. Improve the code structure/readability
2. Ensure ALL existing tests still pass
3. Don't change public APIs
4. Document any semantic changes

OUTPUT FORMAT:
**Refactoring Plan**: [What you're changing and why]

**Diff**:
```diff
[unified diff]
```

**API Compatibility**: [Confirm no breaking changes]"""

def format_bug_fix_prompt(
    test_failures: str,
    test_output: str,
    context: str
) -> str:
    """Format bug fix analysis prompt."""
    return BUG_FIX_ANALYSIS_TEMPLATE.format(
        test_failures=test_failures,
        test_output=test_output,
        context=context
    )

def format_diff_prompt(
    root_cause: str,
    file_path: str,
    line_number: int,
    current_code: str,
    fixed_code: str,
    context_lines: str
) -> str:
    """Format diff generation prompt."""
    return DIFF_GENERATION_TEMPLATE.format(
        root_cause=root_cause,
        file_path=file_path,
        line_number=line_number,
        current_code=current_code,
        fixed_code=fixed_code,
        context_lines=context_lines
    )

def extract_diff_from_response(response: str) -> str:
    """
    Extract unified diff from LLM response.

    Handles multiple formats:
    - ```diff ... ```
    - Just the diff (starts with ---)
    """
    import re

    # Try to find ```diff ... ``` block
    diff_block = re.search(r'```diff\n(.*?)\n```', response, re.DOTALL)
    if diff_block:
        return diff_block.group(1)

    # Try to find just ``` ... ``` block (might be diff without language tag)
    code_block = re.search(r'```\n(.*?)\n```', response, re.DOTALL)
    if code_block:
        content = code_block.group(1)
        if content.strip().startswith('---'):
            return content

    # Look for lines starting with --- (raw diff)
    lines = response.split('\n')
    diff_start = None
    for i, line in enumerate(lines):
        if line.startswith('---'):
            diff_start = i
            break

    if diff_start is not None:
        return '\n'.join(lines[diff_start:])

    return ""

def parse_root_cause(response: str) -> dict:
    """
    Parse root cause analysis from LLM response.

    Returns:
        dict with keys: root_cause, location, current_code, fix, reason
    """
    import re

    result = {}

    # Extract Root Cause
    root_cause_match = re.search(r'\*\*Root Cause\*\*:\s*(.+?)(?:\n|$)', response)
    if root_cause_match:
        result['root_cause'] = root_cause_match.group(1).strip()

    # Extract Location
    location_match = re.search(r'\*\*Location\*\*:\s*(.+?)(?:\n|$)', response)
    if location_match:
        result['location'] = location_match.group(1).strip()

    # Extract Current Code
    current_match = re.search(r'\*\*Current Code\*\*:\s*`(.+?)`', response)
    if current_match:
        result['current_code'] = current_match.group(1).strip()

    # Extract Fix
    fix_match = re.search(r'\*\*Fix\*\*:\s*`(.+?)`', response)
    if fix_match:
        result['fix'] = fix_match.group(1).strip()

    # Extract Reason
    reason_match = re.search(r'\*\*Reason\*\*:\s*(.+?)(?:\n\n|$)', response, re.DOTALL)
    if reason_match:
        result['reason'] = reason_match.group(1).strip()

    return result
