#!/home/kloros/.venv/bin/python3
"""
List All Available Skills in TOON format.

Outputs compressed skill list using TOON format for maximum readability.
"""

import json
import re
from pathlib import Path
from toon_format import encode as to_toon

def extract_skill_metadata(skill_file: Path):
    """Extract name and description from skill YAML frontmatter."""
    try:
        content = skill_file.read_text()
    except:
        return None

    match = re.search(r'^---\s*\n(.*?)\n---', content, re.MULTILINE | re.DOTALL)
    if not match:
        return None

    frontmatter = match.group(1)
    name_match = re.search(r'^name:\s*(.+)$', frontmatter, re.MULTILINE)
    desc_match = re.search(r'^description:\s*(.+)$', frontmatter, re.MULTILINE)

    if not name_match or not desc_match:
        return None

    return {
        'name': name_match.group(1).strip(),
        'description': desc_match.group(1).strip()
    }

def main():
    """Find and list all skills in TOON format."""
    claude_home = Path.home() / ".claude"
    skill_files = list(claude_home.rglob("SKILL.md"))

    skills = []
    for skill_file in sorted(skill_files):
        metadata = extract_skill_metadata(skill_file)
        if metadata:
            skills.append(metadata)

    # Output in TOON format
    toon_output = to_toon(skills)
    print(toon_output)

    # Comparison stats
    json_output = json.dumps(skills, separators=(',', ':'))
    json_size = len(json_output)
    toon_size = len(toon_output)
    savings = int(100 * (1 - toon_size / json_size))

    import sys
    print(f"\n# {len(skills)} skills | JSON: {json_size:,} bytes | TOON: {toon_size:,} bytes | {savings}% smaller", file=sys.stderr)

if __name__ == '__main__':
    main()
