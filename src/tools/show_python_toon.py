#!/home/kloros/.venv/bin/python3
"""
Show Python data structures in TOON format for analysis.

Extracts dict/list literals from Python files and displays them in TOON format
alongside their original locations. Read-only - never modifies files.

Usage:
    show_python_toon.py <file_path> [--lines START:END]
"""

import ast
import sys
from pathlib import Path
from typing import List, Tuple

from toon_format import encode as to_toon


def extract_data_structures(file_path: str) -> List[Tuple[int, str, str]]:
    """
    Extract data structures from Python file.

    Returns list of (line_number, original_code, toon_format).
    """
    path = Path(file_path)
    source = path.read_text()

    try:
        tree = ast.parse(source)
    except SyntaxError as e:
        print(f"Error: Invalid Python syntax: {e}")
        return []

    results = []

    for node in ast.walk(tree):
        if isinstance(node, (ast.Dict, ast.List)) and hasattr(node, 'lineno'):
            try:
                # Get original code
                lines = source.splitlines()
                start_line = node.lineno - 1
                end_line = node.end_lineno - 1 if hasattr(node, 'end_lineno') else start_line

                original_code = '\n'.join(lines[start_line:end_line + 1])

                # Skip if too small
                if len(original_code) < 30:
                    continue

                # Convert to Python object
                data = ast.literal_eval(ast.unparse(node))

                # Convert to TOON
                toon_str = to_toon(data)

                results.append((node.lineno, original_code.strip(), toon_str))

            except (ValueError, SyntaxError, Exception):
                # Can't convert - skip
                continue

    return results


def main():
    """CLI entry point."""
    if len(sys.argv) < 2:
        print("Usage: show_python_toon.py <file_path>")
        sys.exit(1)

    file_path = sys.argv[1]

    # Extract data structures
    structures = extract_data_structures(file_path)

    if not structures:
        print("No data structures found (or all < 30 chars)")
        return

    print(f"=== Python Data Structures in TOON Format ===")
    print(f"File: {file_path}\n")

    for line_num, original, toon in structures:
        print(f"Line {line_num}:")
        print(f"  Original ({len(original)} chars):")
        for line in original.split('\n')[:3]:  # Show first 3 lines
            print(f"    {line}")
        if len(original.split('\n')) > 3:
            print(f"    ... ({len(original.split('\n'))} lines total)")

        print(f"  TOON ({len(toon)} chars):")
        for line in toon.split('\n'):
            print(f"    {line}")

        savings = int(100 * (1 - len(toon) / len(original)))
        print(f"  Compression: {savings}% smaller\n")


if __name__ == '__main__':
    main()
