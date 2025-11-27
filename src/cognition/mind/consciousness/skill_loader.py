#!/usr/bin/env python3
"""
Skill Loader - Parse and load Superpowers-style markdown skills.

Enables KLoROS to autonomously follow process documentation skills
for systematic problem-solving and self-healing.
"""

import re
import logging
from pathlib import Path
from typing import Dict, List, Optional, Any
from dataclasses import dataclass

logger = logging.getLogger(__name__)


@dataclass
class Skill:
    """Represents a loaded skill."""
    name: str
    description: str
    content: str
    checklist: Optional[List[str]] = None
    examples: Optional[List[Dict[str, str]]] = None
    metadata: Optional[Dict[str, Any]] = None


class SkillLoader:
    """
    Loads and parses Superpowers-style markdown skills.

    Skills are markdown documents that provide systematic workflows
    for solving specific types of problems.
    """

    def __init__(self, skills_dir: Optional[Path] = None):
        """
        Initialize skill loader.

        Args:
            skills_dir: Directory containing skill markdown files
        """
        if skills_dir is None:
            skills_dir = Path("/home/kloros/src/consciousness/skills")

        self.skills_dir = Path(skills_dir)
        self.skills_dir.mkdir(parents=True, exist_ok=True)

        self.loaded_skills: Dict[str, Skill] = {}

    def load_skill(self, skill_name: str) -> Optional[Skill]:
        """
        Load a skill from markdown file.

        Args:
            skill_name: Name of skill (e.g., "systematic-debugging")

        Returns:
            Parsed Skill object or None if not found
        """
        if skill_name in self.loaded_skills:
            logger.info(f"[skill_loader] Using cached skill: {skill_name}")
            return self.loaded_skills[skill_name]

        skill_file = self.skills_dir / f"{skill_name}.md"

        if not skill_file.exists():
            logger.warning(f"[skill_loader] Skill not found: {skill_file}")
            return None

        try:
            content = skill_file.read_text()
            skill = self._parse_skill(skill_name, content)
            self.loaded_skills[skill_name] = skill
            logger.info(f"[skill_loader] Loaded skill: {skill_name}")
            return skill

        except Exception as e:
            logger.error(f"[skill_loader] Failed to load skill {skill_name}: {e}", exc_info=True)
            return None

    def _parse_skill(self, name: str, content: str) -> Skill:
        """
        Parse skill markdown into structured format.

        Args:
            name: Skill name
            content: Raw markdown content

        Returns:
            Parsed Skill object
        """
        lines = content.split('\n')

        description = ""
        checklist = []
        examples = []
        metadata = {}

        in_frontmatter = False
        in_checklist = False
        in_example = False
        current_example = {}

        for i, line in enumerate(lines):
            stripped = line.strip()

            if i == 0 and stripped == '---':
                in_frontmatter = True
                continue

            if in_frontmatter:
                if stripped == '---':
                    in_frontmatter = False
                    continue
                if ':' in stripped:
                    key, value = stripped.split(':', 1)
                    metadata[key.strip()] = value.strip()
                continue

            if stripped.startswith('# ') and not description:
                description = stripped[2:].strip()
                continue

            if re.match(r'^[\d\.\-\*]\s+', stripped):
                checklist.append(stripped)
                in_checklist = True
                continue

            if stripped.startswith('```') and in_example:
                in_example = False
                if current_example:
                    examples.append(current_example)
                    current_example = {}
                continue

            if stripped.startswith('```'):
                in_example = True
                continue

            if stripped.startswith('<example>'):
                in_example = True
                current_example = {'type': 'example', 'content': ''}
                continue

            if stripped.startswith('</example>'):
                in_example = False
                if current_example:
                    examples.append(current_example)
                    current_example = {}
                continue

            if in_example and current_example:
                current_example['content'] = current_example.get('content', '') + line + '\n'

        return Skill(
            name=name,
            description=description or metadata.get('description', ''),
            content=content,
            checklist=checklist if checklist else None,
            examples=examples if examples else None,
            metadata=metadata
        )

    def list_available_skills(self) -> List[str]:
        """
        List all available skills.

        Returns:
            List of skill names
        """
        if not self.skills_dir.exists():
            return []

        skills = []
        for skill_file in self.skills_dir.glob("*.md"):
            skills.append(skill_file.stem)

        return sorted(skills)

    def get_skill_for_problem(self, problem_type: str, problem_description: str) -> Optional[str]:
        """
        Suggest best skill for a given problem.

        Args:
            problem_type: Type of problem (e.g., "performance", "reliability")
            problem_description: Description of the issue

        Returns:
            Recommended skill name or None
        """
        problem_skill_map = {
            "performance": ["systematic-debugging", "root-cause-tracing"],
            "reliability": ["systematic-debugging", "error-debugging"],
            "memory": ["systematic-debugging", "root-cause-tracing"],
            "test_failure": ["test-driven-development", "debugging-toolkit:debugger"],
            "code_quality": ["code-refactoring:code-reviewer"],
            "stuck_process": ["systematic-debugging", "incident-response:devops-troubleshooter"],
        }

        desc_lower = problem_description.lower()

        if "swap" in desc_lower or "memory" in desc_lower:
            return "systematic-debugging"
        elif "stuck" in desc_lower or "deadlock" in desc_lower:
            return "systematic-debugging"
        elif "test" in desc_lower and "fail" in desc_lower:
            return "test-driven-development"
        elif problem_type in problem_skill_map:
            skills = problem_skill_map[problem_type]
            return skills[0] if skills else None

        return "systematic-debugging"


def main():
    """Test skill loader."""
    logging.basicConfig(level=logging.INFO)

    loader = SkillLoader()

    print("Available skills:")
    for skill_name in loader.list_available_skills():
        print(f"  - {skill_name}")

    print("\nTesting skill suggestion:")
    problem_types = [
        ("performance", "Swap usage at 99.6% (12.25GB used)"),
        ("reliability", "Found 4 processes stuck in D state"),
        ("test_failure", "pytest failed with 15 errors"),
    ]

    for prob_type, prob_desc in problem_types:
        recommended = loader.get_skill_for_problem(prob_type, prob_desc)
        print(f"  {prob_type}: {prob_desc[:50]}...")
        print(f"    → Recommended skill: {recommended}")


if __name__ == "__main__":
    main()
