"""
Pattern Detector - Identifies architectural patterns from code references

Analyzes classified references to determine:
- DISTRIBUTED_PATTERN: Functionality intentionally spread across modules
- UNIFIED_MODULE: Functionality concentrated in single module
- PARTIAL_IMPLEMENTATION: Some but not all expected pieces present
- PHANTOM: Name mentioned but not actually used as dependency
"""

from enum import Enum
from typing import List, Dict, Set
from dataclasses import dataclass
from collections import defaultdict

from .reference_analyzer import CodeReference, ReferenceType


class ArchitecturalPattern(Enum):
    """Detected architectural patterns."""
    DISTRIBUTED_PATTERN = "distributed"    # Intentionally spread across modules
    UNIFIED_MODULE = "unified"            # Concentrated in single module
    PARTIAL_IMPLEMENTATION = "partial"     # Some but not all expected pieces
    PHANTOM = "phantom"                    # Mentioned but not actually used


@dataclass
class PatternEvidence:
    """Evidence supporting a pattern classification."""
    pattern: ArchitecturalPattern
    confidence: float
    reasoning: str
    supporting_files: List[str]
    import_count: int
    implementation_count: int
    discussion_count: int


class PatternDetector:
    """
    Identifies architectural patterns from classified references.

    Example:
        For "inference" term:
        - 0 import statements (not used as dependency)
        - 15 class definitions across 4 modules (llm, rag, scanners, domains)
        - 8 function definitions implementing inference
        - 23 comments/strings discussing inference

        Pattern: DISTRIBUTED_PATTERN
        Confidence: 0.95
        Reasoning: "inference implemented across 4 modules (llm.ollama, rag, scanners, domains)"
    """

    def __init__(self):
        self.strong_types = {
            ReferenceType.IMPORT_STATEMENT,
            ReferenceType.CLASS_DEFINITION,
            ReferenceType.FUNCTION_DEFINITION,
            ReferenceType.ATTRIBUTE_ACCESS,
        }

        self.weak_types = {
            ReferenceType.COMMENT,
            ReferenceType.DOCSTRING,
            ReferenceType.STRING_LITERAL,
        }

    def detect_pattern(
        self,
        term: str,
        references: List[CodeReference]
    ) -> PatternEvidence:
        """
        Analyze references to determine architectural pattern.

        Args:
            term: The term being analyzed (e.g., "inference")
            references: All classified references to the term

        Returns:
            PatternEvidence with classification and reasoning
        """
        # Classify references by type
        by_type = self._group_by_type(references)

        # Count different types of evidence
        import_refs = by_type.get(ReferenceType.IMPORT_STATEMENT, [])
        class_refs = by_type.get(ReferenceType.CLASS_DEFINITION, [])
        func_refs = by_type.get(ReferenceType.FUNCTION_DEFINITION, [])
        comment_refs = by_type.get(ReferenceType.COMMENT, [])
        string_refs = by_type.get(ReferenceType.STRING_LITERAL, [])

        import_count = len(import_refs)
        implementation_count = len(class_refs) + len(func_refs)
        discussion_count = len(comment_refs) + len(string_refs)

        # Get unique modules implementing functionality
        implementing_modules = self._get_implementing_modules(class_refs + func_refs)

        # Determine pattern based on evidence
        if import_count == 0 and implementation_count == 0 and discussion_count > 0:
            # Only comments/strings mentioning it - PHANTOM
            return PatternEvidence(
                pattern=ArchitecturalPattern.PHANTOM,
                confidence=0.95,
                reasoning=f"{term} only appears in comments/strings ({discussion_count} mentions), no actual code usage or implementation",
                supporting_files=self._get_unique_files(comment_refs + string_refs),
                import_count=0,
                implementation_count=0,
                discussion_count=discussion_count
            )

        if import_count > 0 and implementation_count == 0:
            # Code tries to import it but no implementation exists - REAL GAP
            return PatternEvidence(
                pattern=ArchitecturalPattern.PHANTOM,
                confidence=0.98,
                reasoning=f"{term} has {import_count} import statements but no implementation (missing dependency)",
                supporting_files=self._get_unique_files(import_refs),
                import_count=import_count,
                implementation_count=0,
                discussion_count=discussion_count
            )

        if implementation_count > 0 and len(implementing_modules) >= 3:
            # Implemented across multiple modules - DISTRIBUTED
            module_list = ", ".join(sorted(implementing_modules)[:4])
            if len(implementing_modules) > 4:
                module_list += f", +{len(implementing_modules) - 4} more"

            return PatternEvidence(
                pattern=ArchitecturalPattern.DISTRIBUTED_PATTERN,
                confidence=0.90,
                reasoning=f"{term} implemented as distributed functionality across {len(implementing_modules)} modules ({module_list})",
                supporting_files=self._get_unique_files(class_refs + func_refs),
                import_count=import_count,
                implementation_count=implementation_count,
                discussion_count=discussion_count
            )

        if implementation_count > 0 and len(implementing_modules) == 1:
            # All implementation in single module - UNIFIED
            module_name = list(implementing_modules)[0]
            return PatternEvidence(
                pattern=ArchitecturalPattern.UNIFIED_MODULE,
                confidence=0.95,
                reasoning=f"{term} implemented as unified module in {module_name} ({implementation_count} definitions)",
                supporting_files=self._get_unique_files(class_refs + func_refs),
                import_count=import_count,
                implementation_count=implementation_count,
                discussion_count=discussion_count
            )

        if implementation_count > 0 and len(implementing_modules) == 2:
            # Spread across 2 modules - could be intentional or partial
            module_list = ", ".join(sorted(implementing_modules))
            return PatternEvidence(
                pattern=ArchitecturalPattern.PARTIAL_IMPLEMENTATION,
                confidence=0.70,
                reasoning=f"{term} partially implemented across 2 modules ({module_list}), may be distributed or incomplete",
                supporting_files=self._get_unique_files(class_refs + func_refs),
                import_count=import_count,
                implementation_count=implementation_count,
                discussion_count=discussion_count
            )

        # Default: uncertain
        return PatternEvidence(
            pattern=ArchitecturalPattern.PHANTOM,
            confidence=0.50,
            reasoning=f"{term} has ambiguous references (imports={import_count}, impl={implementation_count}, discussion={discussion_count})",
            supporting_files=self._get_unique_files(references),
            import_count=import_count,
            implementation_count=implementation_count,
            discussion_count=discussion_count
        )

    def _group_by_type(
        self,
        references: List[CodeReference]
    ) -> Dict[ReferenceType, List[CodeReference]]:
        """Group references by their type."""
        grouped = defaultdict(list)
        for ref in references:
            grouped[ref.ref_type].append(ref)
        return dict(grouped)

    def _get_implementing_modules(
        self,
        implementation_refs: List[CodeReference]
    ) -> Set[str]:
        """
        Extract unique module names from implementation references.

        Example: /home/kloros/src/llm/ollama/engine.py -> llm.ollama
        """
        modules = set()
        for ref in implementation_refs:
            module = self._extract_module_name(ref.file_path)
            if module:
                modules.add(module)
        return modules

    def _extract_module_name(self, file_path: str) -> str:
        """
        Extract module name from file path.

        /home/kloros/src/llm/ollama/engine.py -> llm.ollama
        /home/kloros/src/rag/retrieval.py -> rag
        """
        try:
            # Normalize path
            if '/src/' in file_path:
                rel_path = file_path.split('/src/')[-1]
            else:
                return ""

            # Remove file name
            parts = rel_path.split('/')[:-1]

            # Return module path
            return '.'.join(parts) if parts else ""
        except Exception:
            return ""

    def _get_unique_files(self, references: List[CodeReference]) -> List[str]:
        """Get unique file paths from references."""
        files = set(ref.file_path for ref in references)
        return sorted(files)

    def get_gap_likelihood(self, evidence: PatternEvidence) -> float:
        """
        Calculate likelihood this represents a real gap vs phantom.

        Returns:
            0.0 = definitely not a gap (distributed pattern or phantom)
            1.0 = definitely a gap (imports missing module)
        """
        pattern_scores = {
            ArchitecturalPattern.PHANTOM: 0.05,           # Very unlikely to be real gap
            ArchitecturalPattern.DISTRIBUTED_PATTERN: 0.10,  # Intentional distribution
            ArchitecturalPattern.UNIFIED_MODULE: 0.05,    # Already implemented
            ArchitecturalPattern.PARTIAL_IMPLEMENTATION: 0.60,  # Might need completion
        }

        base_score = pattern_scores.get(evidence.pattern, 0.50)

        # Adjust based on imports
        if evidence.import_count > 0 and evidence.implementation_count == 0:
            # Code imports it but it doesn't exist - HIGH gap likelihood
            return 0.95

        if evidence.import_count > 0 and evidence.implementation_count > 0:
            # Code imports it AND it exists - NOT a gap
            return 0.05

        return base_score
