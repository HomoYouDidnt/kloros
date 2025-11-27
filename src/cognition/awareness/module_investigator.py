#!/usr/bin/env python3
"""
Module Code Investigator - Deep LLM-powered code analysis for curiosity.

Purpose:
    Curiosity's investigative engine. When she asks "What does this module do?",
    this system reads every file, analyzes the architecture, and uses an LLM
    to deeply understand purpose, capabilities, and integration points.

    Think: Autism-spectrum engineer who obsessively figures out how everything
    works by reading all the pieces.

Architecture:
    1. Read all Python files in module directory
    2. Extract structure (classes, functions, imports, docstrings)
    3. Use LLM for deep semantic analysis:
       - What problem does this solve?
       - What are the key abstractions?
       - What capabilities does it provide?
       - How does it integrate with other systems?
    4. Document findings in structured format
    5. Write to curiosity_investigations.jsonl

Integration:
    - Called by curiosity_core when investigating undiscovered modules
    - Uses Ollama LLM (qwen2.5:72b) for code understanding
    - Results consumed by capability_integrator for registry updates
"""

import os
import ast
import logging
import requests
from pathlib import Path
from typing import Dict, Any, List, Optional
from datetime import datetime

logger = logging.getLogger(__name__)


class ModuleInvestigator:
    """
    Deep code analysis engine for understanding undiscovered modules.

    Uses LLM-powered analysis to understand what code does, not just what it exports.
    """

    def __init__(self, ollama_host: Optional[str] = None, model: str = "qwen2.5-coder:7b"):
        """
        Initialize investigator.

        Args:
            ollama_host: Ollama server URL (automatic failover to gaming rig or local)
            model: Model to use for code analysis
        """
        if ollama_host:
            self.ollama_host = ollama_host
        else:
            # Use automatic failover (gaming rig → local)
            from config.models_config import get_ollama_url
            self.ollama_host = get_ollama_url()

        self.model = os.getenv("OLLAMA_MODEL", model)

        if not self.ollama_host.startswith("http"):
            self.ollama_host = f"http://{self.ollama_host}"

        logger.info(f"[module_investigator] Initialized with {self.model} at {self.ollama_host}")

    def investigate_module(self, module_path: str, module_name: str, question: str,
                          custom_instructions: Optional[str] = None) -> Dict[str, Any]:
        """
        Deeply investigate a module to understand its purpose and capabilities.

        This is the main entry point - the autism-spectrum engineer that
        obsessively reads everything and figures it out.

        Args:
            module_path: Full path to module directory
            module_name: Name of the module
            question: The curiosity question being investigated
            custom_instructions: Optional custom instructions from meta-agent
                               (if provided, uses these instead of default prompt)

        Returns:
            Investigation results dictionary
        """
        logger.info(f"[module_investigator] Investigating {module_name} at {module_path}")

        investigation = {
            "timestamp": datetime.now().isoformat(),
            "module_name": module_name,
            "module_path": module_path,
            "question": question,
            "files_analyzed": [],
            "structure": {},
            "llm_analysis": {},
            "capabilities": [],
            "integration_points": [],
            "key_abstractions": [],
            "callable_interface": [],
            "success": False,
            "error": None
        }

        try:
            # Step 1: Read all Python files in module
            code_files = self._read_module_files(module_path)

            if not code_files:
                investigation["error"] = "No Python files found in module"
                return investigation

            investigation["files_analyzed"] = [str(f["path"]) for f in code_files]
            logger.info(f"[module_investigator] Found {len(code_files)} Python files")

            # Step 2: Extract structural information using AST
            structure = self._extract_structure(code_files)
            investigation["structure"] = structure
            logger.info(f"[module_investigator] Extracted structure: {len(structure['classes'])} classes, {len(structure['functions'])} functions")

            # Step 3: Use LLM to deeply understand the code
            llm_analysis = self._llm_deep_analysis(code_files, structure, module_name, question, custom_instructions)

            if llm_analysis:
                investigation["llm_analysis"] = llm_analysis
                investigation["capabilities"] = llm_analysis.get("capabilities", [])
                investigation["integration_points"] = llm_analysis.get("integration_points", [])
                investigation["key_abstractions"] = llm_analysis.get("key_abstractions", [])
                investigation["callable_interface"] = llm_analysis.get("callable_interface", [])
                investigation["success"] = True

                # Propagate metrics to investigation dict
                investigation["model_used"] = llm_analysis.get("model_used", "unknown")
                investigation["tokens_used"] = llm_analysis.get("tokens_used", 0)
                investigation["prompt_tokens"] = llm_analysis.get("prompt_tokens", 0)

                logger.info(f"[module_investigator] ✓ Investigation complete: {len(investigation['capabilities'])} capabilities, {len(investigation['callable_interface'])} callable interfaces identified")
            else:
                investigation["error"] = "LLM analysis failed"
                investigation["model_used"] = "unknown"
                investigation["tokens_used"] = 0
                investigation["prompt_tokens"] = 0
                logger.warning("[module_investigator] LLM analysis failed, using structural analysis only")

        except Exception as e:
            investigation["error"] = str(e)
            investigation["model_used"] = "unknown"
            investigation["tokens_used"] = 0
            investigation["prompt_tokens"] = 0
            logger.error(f"[module_investigator] Investigation failed: {e}", exc_info=True)

        return investigation

    def _read_module_files(self, module_path: str) -> List[Dict[str, Any]]:
        """
        Read all Python files in module directory.

        Args:
            module_path: Path to module

        Returns:
            List of dicts with file info and content
        """
        files = []
        module_dir = Path(module_path)

        if not module_dir.exists() or not module_dir.is_dir():
            logger.warning(f"[module_investigator] Module path does not exist or is not directory: {module_path}")
            return files

        # Find all .py files
        for py_file in module_dir.rglob("*.py"):
            try:
                # Skip __pycache__ and test files for initial analysis
                if "__pycache__" in str(py_file) or py_file.name.startswith("test_"):
                    continue

                content = py_file.read_text(errors='ignore')

                files.append({
                    "path": py_file.relative_to(module_dir),
                    "full_path": str(py_file),
                    "content": content,
                    "lines": len(content.splitlines()),
                    "size_bytes": len(content.encode())
                })

            except Exception as e:
                logger.warning(f"[module_investigator] Failed to read {py_file}: {e}")

        return files

    def _extract_structure(self, code_files: List[Dict[str, Any]]) -> Dict[str, Any]:
        """
        Extract structural information using AST parsing.

        Args:
            code_files: List of file dicts with content

        Returns:
            Structure dict with classes, functions, imports
        """
        structure = {
            "classes": [],
            "functions": [],
            "imports": [],
            "docstrings": [],
            "total_lines": 0
        }

        for file_info in code_files:
            try:
                tree = ast.parse(file_info["content"])
                structure["total_lines"] += file_info["lines"]

                # Extract module docstring
                docstring = ast.get_docstring(tree)
                if docstring:
                    structure["docstrings"].append({
                        "file": str(file_info["path"]),
                        "type": "module",
                        "text": docstring[:500]  # First 500 chars
                    })

                # Walk AST
                for node in ast.walk(tree):
                    # Classes
                    if isinstance(node, ast.ClassDef):
                        class_doc = ast.get_docstring(node)
                        structure["classes"].append({
                            "name": node.name,
                            "file": str(file_info["path"]),
                            "methods": [m.name for m in node.body if isinstance(m, ast.FunctionDef)],
                            "docstring": class_doc[:200] if class_doc else None
                        })

                    # Functions (top-level only)
                    elif isinstance(node, ast.FunctionDef) and not any(
                        isinstance(parent, ast.ClassDef)
                        for parent in ast.walk(tree)
                        if hasattr(parent, 'body') and isinstance(parent.body, list) and node in parent.body
                    ):
                        func_doc = ast.get_docstring(node)
                        structure["functions"].append({
                            "name": node.name,
                            "file": str(file_info["path"]),
                            "args": [arg.arg for arg in node.args.args],
                            "docstring": func_doc[:200] if func_doc else None
                        })

                    # Imports
                    elif isinstance(node, ast.Import):
                        for alias in node.names:
                            structure["imports"].append(alias.name)

                    elif isinstance(node, ast.ImportFrom):
                        if node.module:
                            structure["imports"].append(node.module)

            except Exception as e:
                logger.warning(f"[module_investigator] Failed to parse {file_info['path']}: {e}")

        # Deduplicate imports
        structure["imports"] = list(set(structure["imports"]))

        return structure

    def _llm_deep_analysis(
        self,
        code_files: List[Dict[str, Any]],
        structure: Dict[str, Any],
        module_name: str,
        question: str,
        custom_instructions: Optional[str] = None
    ) -> Optional[Dict[str, Any]]:
        """
        Use LLM to deeply understand what the module does.

        This is the "autism-spectrum engineer" part - give the LLM all the code
        and ask it to figure out what it does, why it exists, and how it integrates.

        Args:
            code_files: All code files
            structure: Extracted structure
            module_name: Module name
            question: Original curiosity question
            custom_instructions: Optional custom instructions from meta-agent
                               (replaces default role-playing prompt)

        Returns:
            LLM analysis dict or None if failed
            Includes model_used, tokens_used, and prompt_tokens fields
        """
        # Build comprehensive prompt with all code
        code_snippets = []

        for file_info in code_files[:10]:  # Limit to first 10 files to avoid token limits
            code_snippets.append(f"=== {file_info['path']} ===\n{file_info['content'][:3000]}")  # First 3000 chars per file

        code_context = "\n\n".join(code_snippets)

        # Use custom instructions from meta-agent if provided, otherwise default prompt
        if custom_instructions:
            # Meta-agent has delegated with her own instructions
            prompt = f"""{custom_instructions}

Module Name: {module_name}
Question to Answer: {question}

Module Structure:
- Classes: {', '.join(c['name'] for c in structure['classes'][:20])}
- Functions: {', '.join(f['name'] for f in structure['functions'][:20])}
- Key Imports: {', '.join(structure['imports'][:15])}
- Total Lines: {structure['total_lines']}

Code Files:
{code_context}

Analyze this module and provide a structured understanding in JSON format:

{{
  "purpose": "One-sentence explanation of what this module does",
  "problem_solved": "What problem does this solve?",
  "capabilities": [
    "capability_1: Brief description",
    "capability_2: Brief description"
  ],
  "key_abstractions": [
    "Class/concept 1 and what it represents",
    "Class/concept 2 and what it represents"
  ],
  "integration_points": [
    "How it connects to X system",
    "How it depends on Y"
  ],
  "callable_interface": [
    {{
      "function": "function_name",
      "parameters": [{{"name": "param_name", "type": "param_type"}}],
      "returns": "return_type",
      "description": "One-sentence description of what this function does"
    }}
  ],
  "module_kind": "service|tool|storage|utility|orchestration",
  "confidence": 0.0-1.0
}}

Output ONLY valid JSON, no markdown or explanations."""
        else:
            # Default autonomous investigation (no meta-agent delegation)
            prompt = f"""You are a senior software architect analyzing an undiscovered module in the KLoROS voice assistant system.

Module Name: {module_name}
Question to Answer: {question}

Module Structure:
- Classes: {', '.join(c['name'] for c in structure['classes'][:20])}
- Functions: {', '.join(f['name'] for f in structure['functions'][:20])}
- Key Imports: {', '.join(structure['imports'][:15])}
- Total Lines: {structure['total_lines']}

Code Files:
{code_context}

Analyze this module and provide a structured understanding in JSON format:

{{
  "purpose": "One-sentence explanation of what this module does",
  "problem_solved": "What problem does this solve in the KLoROS system?",
  "capabilities": [
    "capability_1: Brief description",
    "capability_2: Brief description"
  ],
  "key_abstractions": [
    "Class/concept 1 and what it represents",
    "Class/concept 2 and what it represents"
  ],
  "integration_points": [
    "How it connects to X system",
    "How it depends on Y"
  ],
  "callable_interface": [
    {{
      "function": "function_name",
      "parameters": [{{"name": "param_name", "type": "param_type"}}],
      "returns": "return_type",
      "description": "One-sentence description of what this function does"
    }}
  ],
  "module_kind": "service|tool|storage|utility|orchestration",
  "confidence": 0.0-1.0
}}

IMPORTANT: For callable_interface, extract the major public functions/methods that external code would call.
Include parameter names and types from docstrings or type hints, return types, and clear descriptions.
Focus on UNDERSTANDING, not just describing. What is the engineering intent behind this code?
Output ONLY valid JSON, no markdown or explanations."""

        # Cap prompt at 35k characters to prevent oversized requests
        MAX_PROMPT_CHARS = 35000
        if len(prompt) > MAX_PROMPT_CHARS:
            logger.warning(f"[module_investigator] Prompt too large ({len(prompt)} chars), truncating to {MAX_PROMPT_CHARS}")
            prompt = prompt[:MAX_PROMPT_CHARS] + "\n\n[... truncated for length ...]\n\nOutput ONLY valid JSON, no markdown or explanations."

        try:
            logger.info(f"[module_investigator] Sending {len(prompt)} chars to LLM for deep analysis")

            # Try remote first (if configured), fall back to local on failure
            urls_to_try = [self.ollama_host]
            if self.ollama_host != "http://127.0.0.1:11434":
                urls_to_try.append("http://127.0.0.1:11434")

            response = None
            last_error = None
            selected_model = None

            for url in urls_to_try:
                # Query API to select best available model for this endpoint
                from config.models_config import select_best_model_for_task
                model = select_best_model_for_task('code', url)
                selected_model = model
                try:
                    logger.info(f"[module_investigator] Trying {url} with {model}")
                    response = requests.post(
                        f"{url}/api/generate",
                        json={
                            "model": model,
                            "prompt": prompt,
                            "stream": True,
                            "options": {
                                "temperature": 0.3,
                                "num_predict": 2048
                            }
                        },
                        timeout=(5, 600),  # 5s connection, 600s read
                        stream=True
                    )
                    response.raise_for_status()
                    logger.info(f"[module_investigator] Successfully connected to {url}")
                    break
                except (requests.exceptions.Timeout, requests.exceptions.ConnectionError) as e:
                    logger.warning(f"[module_investigator] Failed to connect to {url}: {e}")
                    last_error = e
                    continue

            if response is None:
                raise last_error or Exception("All Ollama endpoints failed")

            # Handle streaming response and extract metrics
            import json
            llm_output = ""
            eval_count = 0
            prompt_eval_count = 0

            for line in response.iter_lines():
                if line:
                    try:
                        chunk = json.loads(line)
                        llm_output += chunk.get("response", "")
                        if chunk.get("done", False):
                            eval_count = chunk.get("eval_count", 0)
                            prompt_eval_count = chunk.get("prompt_eval_count", 0)
                            break
                    except json.JSONDecodeError:
                        continue

            llm_output = llm_output.strip()

            if not llm_output:
                logger.error("[module_investigator] LLM returned empty response")
                return None

            # Parse JSON response
            import json

            # Clean up markdown if present
            if llm_output.startswith("```json"):
                llm_output = llm_output.split("```json")[1].split("```")[0].strip()
            elif llm_output.startswith("```"):
                llm_output = llm_output.split("```")[1].split("```")[0].strip()

            analysis = json.loads(llm_output)

            # Add metrics to analysis before returning
            analysis["model_used"] = selected_model or "unknown"
            analysis["tokens_used"] = eval_count
            analysis["prompt_tokens"] = prompt_eval_count

            logger.info(f"[module_investigator] ✓ LLM analysis complete (confidence: {analysis.get('confidence', 0)}, model: {selected_model}, tokens: {eval_count})")

            return analysis

        except requests.exceptions.RequestException as e:
            logger.error(f"[module_investigator] LLM request failed: {e}")
            return None

        except json.JSONDecodeError as e:
            logger.error(f"[module_investigator] Failed to parse LLM response as JSON: {e}")
            logger.debug(f"[module_investigator] LLM output was: {llm_output[:500]}")
            return None

        except Exception as e:
            logger.error(f"[module_investigator] LLM analysis failed: {e}", exc_info=True)
            return None


# Singleton instance
_module_investigator = None

def get_module_investigator(ollama_host: Optional[str] = None, model: str = "deepseek-r1:14b"):
    """Get singleton module investigator instance."""
    global _module_investigator
    if _module_investigator is None:
        _module_investigator = ModuleInvestigator(ollama_host, model)
    return _module_investigator
