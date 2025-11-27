"""
Reference Analyzer - Semantic classification of code references

Analyzes HOW a term is referenced in code to distinguish between:
- IMPORT: "from inference import model" (dependency - real gap if missing)
- IMPLEMENTATION: "class InferenceEngine:" (provider - not a gap)
- COMMENT: "# TODO: add inference support" (discussion - not a gap)
- DOCSTRING: "Handles model inference..." (description - not a gap)
- ATTRIBUTE: "self.inference_backend" (usage - possible gap)
- LITERAL: "inference" in strings (mention - not a gap)
"""

import ast
import re
from enum import Enum
from pathlib import Path
from typing import List, Dict, Any, Optional, Tuple
from dataclasses import dataclass


class ReferenceType(Enum):
    """Classification of how a term is referenced in code."""
    IMPORT_STATEMENT = "import"           # from X import Y, import X
    CLASS_DEFINITION = "class_def"        # class InferenceEngine
    FUNCTION_DEFINITION = "func_def"      # def run_inference()
    VARIABLE_ASSIGNMENT = "var_assign"    # inference_model = ...
    ATTRIBUTE_ACCESS = "attr_access"      # obj.inference_method()
    COMMENT = "comment"                   # # inference stuff
    DOCSTRING = "docstring"               # """inference docs"""
    STRING_LITERAL = "string_literal"     # "inference"
    IDENTIFIER = "identifier"             # inference (generic usage)


@dataclass
class CodeReference:
    """A single reference to a term in code."""
    file_path: str
    line_number: int
    ref_type: ReferenceType
    context: str              # Surrounding code/text
    full_line: str           # Complete line where found
    module_name: Optional[str] = None  # For imports
    confidence: float = 1.0  # How sure we are of classification


class ReferenceAnalyzer:
    """
    Analyzes code to semantically classify references to a term.

    Example:
        >>> analyzer = ReferenceAnalyzer()
        >>> refs = analyzer.analyze_term_in_codebase("inference", "/home/kloros/src")
        >>> imports = [r for r in refs if r.ref_type == ReferenceType.IMPORT_STATEMENT]
        >>> implementations = [r for r in refs if r.ref_type == ReferenceType.CLASS_DEFINITION]
    """

    def __init__(self):
        self.comment_pattern = re.compile(r'#\s*(.*)')
        self.string_pattern = re.compile(r'["\']([^"\']*)["\']')

    def analyze_term_in_codebase(
        self,
        term: str,
        base_path: str,
        max_files: int = 100
    ) -> List[CodeReference]:
        """
        Find and classify all references to a term in codebase.

        Args:
            term: The term to search for (e.g., "inference")
            base_path: Root directory to search
            max_files: Limit scanning for performance

        Returns:
            List of CodeReference objects
        """
        references = []
        base = Path(base_path)

        # Find Python files mentioning the term
        py_files = []
        for py_file in base.rglob("*.py"):
            if len(py_files) >= max_files:
                break

            # Quick grep to see if term appears
            try:
                content = py_file.read_text(errors='ignore')
                if term.lower() in content.lower():
                    py_files.append(py_file)
            except Exception:
                continue

        # Analyze each file
        for py_file in py_files:
            refs = self._analyze_file(py_file, term)
            references.extend(refs)

        return references

    def _analyze_file(self, file_path: Path, term: str) -> List[CodeReference]:
        """Analyze a single Python file for references to term."""
        references = []

        try:
            content = file_path.read_text(errors='ignore')
            lines = content.split('\n')

            # Try AST parsing for structured analysis
            try:
                tree = ast.parse(content)
                ast_refs = self._analyze_ast(tree, file_path, term, lines)
                references.extend(ast_refs)
            except SyntaxError:
                # Fallback to regex if AST fails
                pass

            # Regex-based analysis for comments, strings, etc.
            regex_refs = self._analyze_regex(file_path, term, lines)
            references.extend(regex_refs)

        except Exception:
            pass

        return references

    def _analyze_ast(
        self,
        tree: ast.AST,
        file_path: Path,
        term: str,
        lines: List[str]
    ) -> List[CodeReference]:
        """Analyze AST for structured references."""
        references = []

        for node in ast.walk(tree):
            # Import statements
            if isinstance(node, (ast.Import, ast.ImportFrom)):
                ref = self._check_import(node, file_path, term, lines)
                if ref:
                    references.append(ref)

            # Class definitions
            elif isinstance(node, ast.ClassDef):
                if term.lower() in node.name.lower():
                    references.append(CodeReference(
                        file_path=str(file_path),
                        line_number=node.lineno,
                        ref_type=ReferenceType.CLASS_DEFINITION,
                        context=node.name,
                        full_line=lines[node.lineno - 1] if node.lineno <= len(lines) else "",
                        confidence=0.9
                    ))

            # Function definitions
            elif isinstance(node, ast.FunctionDef):
                if term.lower() in node.name.lower():
                    references.append(CodeReference(
                        file_path=str(file_path),
                        line_number=node.lineno,
                        ref_type=ReferenceType.FUNCTION_DEFINITION,
                        context=node.name,
                        full_line=lines[node.lineno - 1] if node.lineno <= len(lines) else "",
                        confidence=0.9
                    ))

            # Attribute access
            elif isinstance(node, ast.Attribute):
                if term.lower() in node.attr.lower():
                    references.append(CodeReference(
                        file_path=str(file_path),
                        line_number=getattr(node, 'lineno', 0),
                        ref_type=ReferenceType.ATTRIBUTE_ACCESS,
                        context=node.attr,
                        full_line=lines[node.lineno - 1] if hasattr(node, 'lineno') and node.lineno <= len(lines) else "",
                        confidence=0.7
                    ))

        return references

    def _check_import(
        self,
        node: ast.AST,
        file_path: Path,
        term: str,
        lines: List[str]
    ) -> Optional[CodeReference]:
        """Check if import statement references the term."""
        if isinstance(node, ast.ImportFrom):
            module = node.module or ""
            if term.lower() in module.lower():
                return CodeReference(
                    file_path=str(file_path),
                    line_number=node.lineno,
                    ref_type=ReferenceType.IMPORT_STATEMENT,
                    context=f"from {module} import ...",
                    full_line=lines[node.lineno - 1] if node.lineno <= len(lines) else "",
                    module_name=module,
                    confidence=1.0  # High confidence - this is a real dependency
                )

            # Check imported names
            for alias in node.names:
                if term.lower() in alias.name.lower():
                    return CodeReference(
                        file_path=str(file_path),
                        line_number=node.lineno,
                        ref_type=ReferenceType.IMPORT_STATEMENT,
                        context=f"from {module} import {alias.name}",
                        full_line=lines[node.lineno - 1] if node.lineno <= len(lines) else "",
                        module_name=module,
                        confidence=1.0
                    )

        elif isinstance(node, ast.Import):
            for alias in node.names:
                if term.lower() in alias.name.lower():
                    return CodeReference(
                        file_path=str(file_path),
                        line_number=node.lineno,
                        ref_type=ReferenceType.IMPORT_STATEMENT,
                        context=f"import {alias.name}",
                        full_line=lines[node.lineno - 1] if node.lineno <= len(lines) else "",
                        module_name=alias.name,
                        confidence=1.0
                    )

        return None

    def _analyze_regex(
        self,
        file_path: Path,
        term: str,
        lines: List[str]
    ) -> List[CodeReference]:
        """Regex-based analysis for comments, strings, etc."""
        references = []

        for line_num, line in enumerate(lines, start=1):
            # Comments
            if '#' in line:
                comment_match = self.comment_pattern.search(line)
                if comment_match and term.lower() in comment_match.group(1).lower():
                    references.append(CodeReference(
                        file_path=str(file_path),
                        line_number=line_num,
                        ref_type=ReferenceType.COMMENT,
                        context=comment_match.group(1).strip(),
                        full_line=line,
                        confidence=0.3  # Low confidence - just discussion
                    ))

            # String literals (excluding comments)
            line_without_comment = line.split('#')[0]
            if term.lower() in line_without_comment.lower():
                string_matches = self.string_pattern.findall(line_without_comment)
                for match in string_matches:
                    if term.lower() in match.lower():
                        references.append(CodeReference(
                            file_path=str(file_path),
                            line_number=line_num,
                            ref_type=ReferenceType.STRING_LITERAL,
                            context=match,
                            full_line=line,
                            confidence=0.2  # Very low confidence - just mention
                        ))

        return references

    def classify_references(
        self,
        references: List[CodeReference]
    ) -> Dict[ReferenceType, List[CodeReference]]:
        """Group references by type."""
        classified = {}
        for ref in references:
            if ref.ref_type not in classified:
                classified[ref.ref_type] = []
            classified[ref.ref_type].append(ref)
        return classified

    def get_strong_evidence(
        self,
        references: List[CodeReference]
    ) -> List[CodeReference]:
        """
        Filter to strong evidence only (imports, class/function definitions).

        Strong evidence indicates actual code dependency or implementation.
        Weak evidence (comments, strings) indicates discussion only.
        """
        strong_types = {
            ReferenceType.IMPORT_STATEMENT,
            ReferenceType.CLASS_DEFINITION,
            ReferenceType.FUNCTION_DEFINITION,
            ReferenceType.ATTRIBUTE_ACCESS,
        }

        return [r for r in references if r.ref_type in strong_types]
