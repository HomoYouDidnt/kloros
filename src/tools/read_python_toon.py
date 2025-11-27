#!/home/kloros/.venv/bin/python3
"""
Read Python files with TOON compression applied to data structures.

Parses Python AST to find dict/list literals and displays them in TOON format.
Read-only - never modifies the source file.

Usage:
    read_python_toon.py <file_path> [--lines START:END]
"""

import ast
import sys
import re
from pathlib import Path
from typing import Dict, List, Tuple

# Use kloros venv which has working toon_format
from toon_format import encode as to_toon


class ToonVisitor(ast.NodeVisitor):
    """AST visitor that finds dict/list literals and their locations."""

    def __init__(self, source_lines: List[str]):
        self.source_lines = source_lines
        self.replacements: List[Tuple[int, int, int, int, str]] = []
        # (start_line, start_col, end_line, end_col, toon_str)

    def visit_Dict(self, node: ast.Dict):
        """Visit dictionary literals."""
        self._try_convert_node(node)
        self.generic_visit(node)

    def visit_List(self, node: ast.List):
        """Visit list literals."""
        self._try_convert_node(node)
        self.generic_visit(node)

    def _try_convert_node(self, node):
        """Try to convert AST node to TOON."""
        # Skip if node doesn't have position info
        if not hasattr(node, 'lineno'):
            return

        try:
            # Evaluate the literal safely
            data = ast.literal_eval(ast.unparse(node))

            # Only convert substantial data structures
            if not isinstance(data, (dict, list)):
                return

            # Skip small structures (< 30 chars when serialized)
            import json
            if len(json.dumps(data)) < 30:
                return

            # Convert to TOON
            toon_str = to_toon(data)

            # Store replacement info
            self.replacements.append((
                node.lineno - 1,      # 0-indexed start line
                node.col_offset,       # start column
                node.end_lineno - 1,   # 0-indexed end line
                node.end_col_offset,   # end column
                toon_str
            ))
        except (ValueError, SyntaxError, Exception):
            # Can't convert - skip
            pass


def read_python_with_toon(file_path: str, start_line: int = None, end_line: int = None) -> str:
    """
    Read Python file and display with TOON-compressed data structures.

    Args:
        file_path: Path to Python file
        start_line: Optional starting line (1-indexed)
        end_line: Optional ending line (1-indexed)

    Returns:
        File content with TOON compression applied
    """
    path = Path(file_path)
    if not path.exists():
        return f"Error: File not found: {file_path}"

    # Read source
    source = path.read_text()
    source_lines = source.splitlines()

    # Parse AST
    try:
        tree = ast.parse(source)
    except SyntaxError as e:
        return f"Error: Invalid Python syntax: {e}"

    # Find data structures
    visitor = ToonVisitor(source_lines)
    visitor.visit(tree)

    # Apply replacements (in reverse order to maintain indices)
    replacements = sorted(visitor.replacements, reverse=True)

    modified_lines = source_lines.copy()

    for start_line_idx, start_col, end_line_idx, end_col, toon_str in replacements:
        # Extract original indentation
        original_line = modified_lines[start_line_idx]
        indent = original_line[:start_col]

        # Apply TOON with proper indentation
        if '\n' in toon_str:
            # Multi-line TOON - indent each line
            toon_lines = toon_str.split('\n')
            toon_indented = '\n'.join(indent + line if line else '' for line in toon_lines)
        else:
            # Single-line TOON
            toon_indented = indent + toon_str

        # Replace in source
        if start_line_idx == end_line_idx:
            # Single line replacement
            line = modified_lines[start_line_idx]
            modified_lines[start_line_idx] = (
                line[:start_col] + toon_str + line[end_col:]
            )
        else:
            # Multi-line replacement
            first_line = modified_lines[start_line_idx]
            last_line = modified_lines[end_line_idx]

            new_content = first_line[:start_col] + toon_indented + last_line[end_col:]

            # Replace the range with single line
            modified_lines[start_line_idx:end_line_idx + 1] = [new_content]

    # Apply line range if specified
    if start_line is not None or end_line is not None:
        start_idx = (start_line - 1) if start_line else 0
        end_idx = end_line if end_line else len(modified_lines)
        modified_lines = modified_lines[start_idx:end_idx]

        # Add line numbers
        output_lines = []
        for i, line in enumerate(modified_lines, start=start_idx + 1):
            output_lines.append(f"{i:5d}→{line}")
        return '\n'.join(output_lines)
    else:
        return '\n'.join(modified_lines)


def main():
    """CLI entry point."""
    if len(sys.argv) < 2:
        print("Usage: read_python_toon.py <file_path> [--lines START:END]")
        sys.exit(1)

    file_path = sys.argv[1]
    start_line = None
    end_line = None

    # Parse --lines argument
    if len(sys.argv) > 2 and sys.argv[2] == '--lines':
        if len(sys.argv) < 4:
            print("Error: --lines requires START:END argument")
            sys.exit(1)

        line_range = sys.argv[3]
        if ':' in line_range:
            parts = line_range.split(':')
            start_line = int(parts[0]) if parts[0] else None
            end_line = int(parts[1]) if parts[1] else None
        else:
            start_line = int(line_range)
            end_line = start_line + 100  # Default to 100 lines

    # Read and display
    result = read_python_with_toon(file_path, start_line, end_line)
    print(result)

    # Print stats
    if len(sys.argv) > 2:
        original_size = len(Path(file_path).read_text())
        compressed_size = len(result)
        savings_pct = int(100 * (1 - compressed_size / original_size))
        print(f"\n# TOON Compression: {savings_pct}% smaller", file=sys.stderr)


if __name__ == '__main__':
    main()
