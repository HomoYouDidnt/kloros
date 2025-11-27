#!/usr/bin/env python3
"""
List All Available Skills in JSON format.

Extracts skill metadata from all installed Claude Code plugins and outputs
as JSON. The JSON-to-TOON hook will automatically compress this for viewing.
"""

import json
import re
from pathlib import Path
from typing import List, Dict, Any

def extract_skill_metadata(skill_file: Path) -> Dict[str, str]:
    """Extract name and description from skill YAML frontmatter."""
    try:
        content = skill_file.read_text()
    except:
        return None

    # Extract YAML frontmatter
    match = re.search(r'^---\s*\n(.*?)\n---', content, re.MULTILINE | re.DOTALL)
    if not match:
        return None

    frontmatter = match.group(1)

    # Extract name and description
    name_match = re.search(r'^name:\s*(.+)$', frontmatter, re.MULTILINE)
    desc_match = re.search(r'^description:\s*(.+)$', frontmatter, re.MULTILINE)

    if not name_match or not desc_match:
        return None

    return {
        'name': name_match.group(1).strip(),
        'description': desc_match.group(1).strip(),
        'path': str(skill_file)
    }

def main():
    """Find and list all skills."""
    claude_home = Path.home() / ".claude"

    # Find ALL SKILL.md files anywhere under .claude
    skill_files = list(claude_home.rglob("SKILL.md"))

    skills = []
    for skill_file in sorted(skill_files):
        metadata = extract_skill_metadata(skill_file)
        if metadata:
            skills.append(metadata)

    # Output as JSON (will be auto-compressed by JSON-to-TOON hook)
    print(json.dumps(skills, indent=2))

    # Stats to stderr
    import sys
    print(f"\n# Found {len(skills)} skills", file=sys.stderr)

if __name__ == '__main__':
    main()
