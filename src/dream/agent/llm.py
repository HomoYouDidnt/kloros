# src/dream/agent/llm.py
import json, requests, pathlib

try:
    import tomllib
except ImportError:
    import tomli as tomllib

# Load model config
CONFIG_PATH = pathlib.Path(__file__).parents[3] / "config" / "models.toml"
with open(CONFIG_PATH, "rb") as f:
    MODELS = tomllib.load(f)

MODEL = MODELS["llm"]["ollama"]["model"]  # qwen2.5-coder:32b
# Use code model URL from config (supports multi-instance routing)
from src.config.models_config import get_ollama_url_for_mode
OLLAMA_URL = get_ollama_url_for_mode("code")

def call_llm(prompt: str, system: str = "", temperature: float = 0.7, max_tokens: int = 2000) -> str:
    """Call local LLM via Ollama API"""
    url = f"{OLLAMA_URL}/api/generate"

    full_prompt = f"{system}\n\n{prompt}" if system else prompt

    payload = {
        "model": MODEL,
        "prompt": full_prompt,
        "stream": False,
        "options": {
            "temperature": temperature,
            "num_predict": max_tokens
        }
    }

    try:
        resp = requests.post(url, json=payload, timeout=120)
        resp.raise_for_status()
        return resp.json()["response"]
    except Exception as e:
        return f"LLM_ERROR: {str(e)}"


def generate_edit(repo_path: str, payload: dict, constraints: dict) -> bool:
    """
    Use LLM to generate code edits based on payload and constraints.
    Returns True if edit was applied successfully.
    """
    repo = pathlib.Path(repo_path)

    # Build context
    old_symbol = payload["symbols"]["old"]
    new_symbol = payload["symbols"]["new"]
    print(f"[LLM] Renaming '{old_symbol}' -> '{new_symbol}' in {repo}")

    # Find target files containing old symbol
    targets = []
    for base in ("src", "tests"):
        base_dir = repo / base
        if not base_dir.exists():
            print(f"[LLM] Directory not found: {base_dir}")
            continue
        for f in base_dir.rglob("*.py"):
            try:
                txt = f.read_text()
                if old_symbol in txt:
                    targets.append(f)
                    print(f"[LLM] Found '{old_symbol}' in: {f.relative_to(repo)}")
            except:
                continue

    if not targets:
        print(f"[LLM] No files found containing '{old_symbol}'")
        return False  # Nothing to edit

    print(f"[LLM] Found {len(targets)} target files")

    # For each target file, ask LLM to perform the edit
    system_prompt = f"""You are a code refactoring assistant. Your task is to rename the symbol '{old_symbol}' to '{new_symbol}' in Python code.

CONSTRAINTS:
- Maximum {constraints.get('diff_limit', 60)} lines of diff
- Maximum {constraints.get('max_files_changed', 6)} files changed
- Must preserve all existing functionality
- Must maintain code style

CRITICAL RULES:
1. Rename ALL occurrences: function definitions, imports, and function calls
2. If renaming a function, also update: from X import old_name → from X import new_name
3. If renaming a function, also update: old_name() → new_name() everywhere
4. The code must remain syntactically valid after changes

Return ONLY the complete modified file content, no explanations or markdown blocks."""

    edits_applied = 0

    for target_file in targets[:constraints.get('max_files_changed', 6)]:
        try:
            original_content = target_file.read_text()

            prompt = f"""File: {target_file.relative_to(repo)}

Original content:
```python
{original_content}
```

Task: Rename '{old_symbol}' to '{new_symbol}' throughout this file.

Output the complete modified file:"""

            print(f"[LLM] Calling LLM for: {target_file.relative_to(repo)}")
            response = call_llm(prompt, system=system_prompt, temperature=0.3)

            if "LLM_ERROR" in response:
                print(f"[LLM] LLM error: {response}")
                continue

            # Clean response (remove potential markdown blocks)
            modified = response.strip()
            if modified.startswith("```python"):
                modified = modified.split("```python")[1]
            if modified.startswith("```"):
                modified = modified.split("```")[1]
            if "```" in modified:
                modified = modified.split("```")[0]
            modified = modified.strip()

            # Validation: check new symbol exists, old symbol not in function defs, and syntax is valid
            has_new_symbol = new_symbol in modified
            has_old_func_def = f"def {old_symbol}(" in modified

            # Verify syntax validity
            syntax_valid = False
            try:
                compile(modified, '<string>', 'exec')
                syntax_valid = True
            except SyntaxError:
                pass

            print(f"[LLM] Validation: new_symbol='{new_symbol}' exists={has_new_symbol}")
            print(f"[LLM] Validation: old func def 'def {old_symbol}(' exists={has_old_func_def}")
            print(f"[LLM] Validation: syntax_valid={syntax_valid}")

            if has_new_symbol and not has_old_func_def and syntax_valid:
                target_file.write_text(modified)
                edits_applied += 1
                print(f"[LLM] Applied edit to: {target_file.relative_to(repo)}")
            else:
                print(f"[LLM] Validation failed for: {target_file.relative_to(repo)}")

        except Exception as e:
            print(f"[LLM] Exception: {e}")
            continue

    print(f"[LLM] Total edits applied: {edits_applied}")
    return edits_applied > 0
