"""
Architectural Reasoner - Orchestrates semantic analysis for gap hypothesis validation

High-level API that coordinates:
- ReferenceAnalyzer: Classifies code references
- PatternDetector: Identifies architectural patterns
- ConfidenceScorer: Rates gap hypothesis strength

Provides human-readable explanations of whether a capability gap is:
- Real gap: Code imports missing module
- Distributed pattern: Intentionally spread functionality
- Phantom: Name mentioned but not actually used
"""

from typing import Optional, List
from dataclasses import dataclass
from pathlib import Path

from .reference_analyzer import ReferenceAnalyzer, CodeReference, ReferenceType
from .pattern_detector import PatternDetector, PatternEvidence, ArchitecturalPattern
from .confidence_scorer import ConfidenceScorer, ConfidenceScore


@dataclass
class GapAnalysis:
    """Complete analysis of a potential capability gap."""
    term: str
    is_real_gap: bool
    confidence: float
    pattern: ArchitecturalPattern
    explanation: str
    evidence_summary: str
    references_found: int
    strong_references: int
    weak_references: int
    implementing_files: List[str]
    import_files: List[str]


class ArchitecturalReasoner:
    """
    Orchestrates semantic analysis to validate gap hypotheses.

    Example usage:
        >>> reasoner = ArchitecturalReasoner()
        >>> analysis = reasoner.analyze_gap_hypothesis("inference", "/home/kloros/src")
        >>> print(f"Real gap: {analysis.is_real_gap}")
        False
        >>> print(f"Pattern: {analysis.pattern}")
        DISTRIBUTED_PATTERN
        >>> print(f"Explanation: {analysis.explanation}")
        inference implemented across 4 modules (llm.ollama, rag, scanners, domains)
    """

    def __init__(self, base_path: str = "/home/kloros/src"):
        self.base_path = base_path
        self.reference_analyzer = ReferenceAnalyzer()
        self.pattern_detector = PatternDetector()
        self.confidence_scorer = ConfidenceScorer()

    def analyze_gap_hypothesis(
        self,
        term: str,
        max_files: int = 100
    ) -> GapAnalysis:
        """
        Analyze whether a term represents a real capability gap.

        Args:
            term: The term to analyze (e.g., "inference", "chroma_adapters")
            max_files: Maximum files to scan for performance

        Returns:
            GapAnalysis with complete assessment
        """
        # Step 1: Find and classify all references
        references = self.reference_analyzer.analyze_term_in_codebase(
            term=term,
            base_path=self.base_path,
            max_files=max_files
        )

        # Step 2: Detect architectural pattern
        pattern_evidence = self.pattern_detector.detect_pattern(term, references)

        # Step 3: Score confidence
        confidence_score = self.confidence_scorer.score_gap_hypothesis(
            term, references, pattern_evidence
        )

        # Step 4: Determine if real gap
        is_real_gap = self._determine_real_gap(pattern_evidence, confidence_score)

        # Step 5: Generate human-readable explanation
        explanation = self._generate_explanation(term, pattern_evidence, confidence_score)

        # Step 6: Summarize evidence
        evidence_summary = self._summarize_evidence(references, pattern_evidence)

        # Step 7: Extract file lists
        strong_refs = self.reference_analyzer.get_strong_evidence(references)
        implementing_files = self._extract_implementing_files(references)
        import_files = self._extract_import_files(references)

        return GapAnalysis(
            term=term,
            is_real_gap=is_real_gap,
            confidence=confidence_score.overall_confidence,
            pattern=pattern_evidence.pattern,
            explanation=explanation,
            evidence_summary=evidence_summary,
            references_found=len(references),
            strong_references=len(strong_refs),
            weak_references=len(references) - len(strong_refs),
            implementing_files=implementing_files,
            import_files=import_files
        )

    def _determine_real_gap(
        self,
        pattern: PatternEvidence,
        confidence: ConfidenceScore
    ) -> bool:
        """
        Determine if this is a real gap requiring attention.

        Real gap criteria:
        - Has imports but no implementation (missing dependency)
        - Confidence score >= 0.60
        - Not a distributed or unified pattern
        """
        # If imports exist but no implementation, it's a real gap
        if pattern.import_count > 0 and pattern.implementation_count == 0:
            return True

        # If implementation exists, it's not a gap (even if partial)
        if pattern.implementation_count > 0:
            return False

        # Only discussion/comments - phantom
        if pattern.import_count == 0 and pattern.implementation_count == 0:
            return False

        # Use confidence score for edge cases
        return confidence.overall_confidence >= 0.60

    def _generate_explanation(
        self,
        term: str,
        pattern: PatternEvidence,
        confidence: ConfidenceScore
    ) -> str:
        """Generate human-readable explanation."""
        if pattern.pattern == ArchitecturalPattern.DISTRIBUTED_PATTERN:
            return f"{term} is implemented as distributed functionality (not a gap): {pattern.reasoning}"

        if pattern.pattern == ArchitecturalPattern.UNIFIED_MODULE:
            return f"{term} is implemented as unified module (not a gap): {pattern.reasoning}"

        if pattern.pattern == ArchitecturalPattern.PHANTOM:
            if pattern.import_count > 0:
                return f"{term} appears to be a real gap: {pattern.reasoning}"
            else:
                return f"{term} is a phantom (not a gap): {pattern.reasoning}"

        if pattern.pattern == ArchitecturalPattern.PARTIAL_IMPLEMENTATION:
            return f"{term} has partial implementation: {pattern.reasoning}"

        return f"{term} analysis: {confidence.reasoning}"

    def _summarize_evidence(
        self,
        references: List[CodeReference],
        pattern: PatternEvidence
    ) -> str:
        """Summarize evidence quality and consistency."""
        if not references:
            return "No references found"

        parts = []
        parts.append(f"{pattern.import_count} imports")
        parts.append(f"{pattern.implementation_count} implementations")
        parts.append(f"{pattern.discussion_count} discussions")

        summary = ", ".join(parts)

        if pattern.pattern == ArchitecturalPattern.DISTRIBUTED_PATTERN:
            summary += f" - distributed across {len(pattern.supporting_files)} files"
        elif pattern.pattern == ArchitecturalPattern.UNIFIED_MODULE:
            summary += " - unified implementation"
        elif pattern.pattern == ArchitecturalPattern.PHANTOM:
            summary += " - phantom detection"

        return summary

    def _extract_implementing_files(self, references: List[CodeReference]) -> List[str]:
        """Extract files that implement the term."""
        impl_types = {
            ReferenceType.CLASS_DEFINITION,
            ReferenceType.FUNCTION_DEFINITION,
        }

        files = set()
        for ref in references:
            if ref.ref_type in impl_types:
                files.add(ref.file_path)

        return sorted(files)

    def _extract_import_files(self, references: List[CodeReference]) -> List[str]:
        """Extract files that import the term."""
        files = set()
        for ref in references:
            if ref.ref_type == ReferenceType.IMPORT_STATEMENT:
                files.add(ref.file_path)

        return sorted(files)

    def batch_analyze(self, terms: List[str], max_files: int = 100) -> List[GapAnalysis]:
        """
        Analyze multiple terms in batch.

        Args:
            terms: List of terms to analyze
            max_files: Max files per term

        Returns:
            List of GapAnalysis results
        """
        results = []
        for term in terms:
            analysis = self.analyze_gap_hypothesis(term, max_files)
            results.append(analysis)
        return results

    def get_phantoms_from_registry(
        self,
        registry_path: str = "/home/kloros/src/registry/capabilities_enhanced.yaml"
    ) -> List[str]:
        """
        Extract capability keys from registry to check for phantoms.

        Returns:
            List of capability keys to validate
        """
        import yaml

        try:
            with open(registry_path) as f:
                data = yaml.safe_load(f)

            capabilities = data.get('capabilities', [])
            keys = []

            for cap in capabilities:
                key = cap.get('key', '')
                # Focus on module.* capabilities (most likely to be phantoms)
                if key.startswith('module.'):
                    keys.append(key.replace('module.', ''))

            return keys

        except Exception as e:
            return []

    def validate_registry(
        self,
        registry_path: str = "/home/kloros/src/registry/capabilities_enhanced.yaml"
    ) -> List[GapAnalysis]:
        """
        Validate all module capabilities in registry for phantoms.

        Returns:
            List of analyses, sorted by phantom likelihood (highest first)
        """
        terms = self.get_phantoms_from_registry(registry_path)
        analyses = self.batch_analyze(terms)

        # Sort by phantom likelihood (low is_real_gap confidence = high phantom likelihood)
        analyses.sort(key=lambda a: (not a.is_real_gap, a.confidence))

        return analyses
