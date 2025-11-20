"""
Confidence Scorer - Rates gap hypothesis strength based on evidence

Evaluates the quality and consistency of evidence to determine:
- How confident we should be this is a real gap
- Whether evidence is strong (imports, definitions) or weak (comments)
- Whether evidence is consistent or contradictory
"""

from typing import List, Dict
from dataclasses import dataclass

from .reference_analyzer import CodeReference, ReferenceType
from .pattern_detector import PatternEvidence, ArchitecturalPattern


@dataclass
class ConfidenceScore:
    """Confidence assessment for a gap hypothesis."""
    overall_confidence: float  # 0.0-1.0
    evidence_quality: str      # "strong", "weak", "mixed"
    consistency: str           # "consistent", "contradictory"
    reasoning: str
    factors: Dict[str, float]  # Individual scoring factors


class ConfidenceScorer:
    """
    Rates the strength of gap hypotheses based on evidence quality.

    Example:
        For "inference" phantom:
        - 0 imports (no dependency evidence)
        - 15 implementations (contradicts gap hypothesis)
        - 23 comments (weak evidence)

        Overall confidence in gap: 0.05 (very low - contradictory evidence)
        Quality: "contradictory"
        Reasoning: "Implementation found but no imports suggests distributed pattern, not gap"
    """

    def score_gap_hypothesis(
        self,
        term: str,
        references: List[CodeReference],
        pattern_evidence: PatternEvidence
    ) -> ConfidenceScore:
        """
        Score confidence that term represents a real gap.

        Args:
            term: The term being analyzed
            references: All code references
            pattern_evidence: Pattern detection results

        Returns:
            ConfidenceScore with overall assessment
        """
        factors = {}

        # Factor 1: Import evidence (strongest signal)
        import_score = self._score_import_evidence(pattern_evidence)
        factors['import_evidence'] = import_score

        # Factor 2: Implementation evidence (contradicts gap if present)
        impl_score = self._score_implementation_evidence(pattern_evidence)
        factors['implementation_evidence'] = impl_score

        # Factor 3: Reference quality (strong vs weak)
        quality_score = self._score_reference_quality(references)
        factors['reference_quality'] = quality_score

        # Factor 4: Pattern consistency
        pattern_score = self._score_pattern_consistency(pattern_evidence)
        factors['pattern_consistency'] = pattern_score

        # Calculate overall confidence
        overall = self._calculate_overall_confidence(factors, pattern_evidence)

        # Assess evidence quality
        evidence_quality = self._assess_evidence_quality(pattern_evidence)

        # Check consistency
        consistency = self._check_consistency(pattern_evidence, factors)

        # Generate reasoning
        reasoning = self._generate_reasoning(term, pattern_evidence, factors)

        return ConfidenceScore(
            overall_confidence=overall,
            evidence_quality=evidence_quality,
            consistency=consistency,
            reasoning=reasoning,
            factors=factors
        )

    def _score_import_evidence(self, evidence: PatternEvidence) -> float:
        """
        Score import evidence strength.

        High score = many imports (strong dependency signal)
        Low score = no imports (weak gap evidence)
        """
        if evidence.import_count == 0:
            return 0.0  # No import evidence for gap

        if evidence.implementation_count == 0:
            return 1.0  # Imports but no implementation = real gap

        # Imports and implementation = not a gap
        return 0.1

    def _score_implementation_evidence(self, evidence: PatternEvidence) -> float:
        """
        Score implementation evidence.

        High score = no implementation (supports gap hypothesis)
        Low score = implementation found (contradicts gap)
        """
        if evidence.implementation_count == 0:
            return 0.8  # No implementation supports gap hypothesis

        # Implementation exists - contradicts gap
        if evidence.pattern == ArchitecturalPattern.DISTRIBUTED_PATTERN:
            return 0.05  # Intentionally distributed - not a gap

        if evidence.pattern == ArchitecturalPattern.UNIFIED_MODULE:
            return 0.05  # Already implemented - not a gap

        return 0.3  # Partial implementation - uncertain

    def _score_reference_quality(self, references: List[CodeReference]) -> float:
        """
        Score overall reference quality.

        High score = mostly strong references (imports, definitions)
        Low score = mostly weak references (comments, strings)
        """
        if not references:
            return 0.0

        strong_types = {
            ReferenceType.IMPORT_STATEMENT,
            ReferenceType.CLASS_DEFINITION,
            ReferenceType.FUNCTION_DEFINITION,
        }

        strong_count = sum(1 for r in references if r.ref_type in strong_types)
        quality_ratio = strong_count / len(references)

        return quality_ratio

    def _score_pattern_consistency(self, evidence: PatternEvidence) -> float:
        """
        Score pattern consistency.

        High score = pattern clearly identified
        Low score = ambiguous or contradictory
        """
        if evidence.pattern == ArchitecturalPattern.DISTRIBUTED_PATTERN:
            return 0.95 if evidence.confidence > 0.85 else 0.70

        if evidence.pattern == ArchitecturalPattern.UNIFIED_MODULE:
            return 0.95 if evidence.confidence > 0.85 else 0.70

        if evidence.pattern == ArchitecturalPattern.PHANTOM:
            return evidence.confidence

        # Partial or uncertain
        return 0.50

    def _calculate_overall_confidence(
        self,
        factors: Dict[str, float],
        evidence: PatternEvidence
    ) -> float:
        """
        Calculate overall confidence in gap hypothesis.

        Weights:
        - Import evidence: 40% (strongest signal)
        - Implementation evidence: 30% (contradicts if present)
        - Reference quality: 15%
        - Pattern consistency: 15%
        """
        weights = {
            'import_evidence': 0.40,
            'implementation_evidence': 0.30,
            'reference_quality': 0.15,
            'pattern_consistency': 0.15,
        }

        # Weighted sum
        weighted_sum = sum(
            factors.get(key, 0.0) * weight
            for key, weight in weights.items()
        )

        # If implementation found, cap confidence at 0.15
        if evidence.implementation_count > 0 and evidence.import_count == 0:
            weighted_sum = min(weighted_sum, 0.15)

        # If only discussion (no strong refs), cap at 0.10
        if evidence.implementation_count == 0 and evidence.import_count == 0:
            weighted_sum = min(weighted_sum, 0.10)

        return round(weighted_sum, 2)

    def _assess_evidence_quality(self, evidence: PatternEvidence) -> str:
        """Assess overall evidence quality."""
        total = evidence.import_count + evidence.implementation_count + evidence.discussion_count

        if total == 0:
            return "none"

        strong_count = evidence.import_count + evidence.implementation_count
        strong_ratio = strong_count / total

        if strong_ratio >= 0.70:
            return "strong"
        elif strong_ratio >= 0.30:
            return "mixed"
        else:
            return "weak"

    def _check_consistency(
        self,
        evidence: PatternEvidence,
        factors: Dict[str, float]
    ) -> str:
        """Check if evidence is consistent or contradictory."""
        # Contradictory: imports suggest gap, but implementation found
        if evidence.import_count > 0 and evidence.implementation_count > 0:
            return "consistent"  # Both exist - not a gap

        # Contradictory: implementation exists, suggesting gap is phantom
        if evidence.import_count == 0 and evidence.implementation_count > 0:
            return "contradictory"

        # Consistent: imports but no implementation
        if evidence.import_count > 0 and evidence.implementation_count == 0:
            return "consistent"

        # Consistent: only discussion (phantom)
        if evidence.import_count == 0 and evidence.implementation_count == 0:
            return "consistent"

        return "ambiguous"

    def _generate_reasoning(
        self,
        term: str,
        evidence: PatternEvidence,
        factors: Dict[str, float]
    ) -> str:
        """Generate human-readable reasoning."""
        parts = []

        # Import evidence
        if evidence.import_count > 0:
            if evidence.implementation_count == 0:
                parts.append(f"{evidence.import_count} import(s) but no implementation (real gap)")
            else:
                parts.append(f"{evidence.import_count} import(s) with implementation present (not a gap)")
        else:
            parts.append("No imports (not used as dependency)")

        # Implementation evidence
        if evidence.implementation_count > 0:
            parts.append(f"{evidence.implementation_count} implementation(s) found")

        # Discussion evidence
        if evidence.discussion_count > 0:
            parts.append(f"{evidence.discussion_count} comment/string mention(s)")

        # Pattern conclusion
        if evidence.pattern == ArchitecturalPattern.DISTRIBUTED_PATTERN:
            parts.append("Distributed pattern detected - not a gap")
        elif evidence.pattern == ArchitecturalPattern.UNIFIED_MODULE:
            parts.append("Unified implementation found - not a gap")
        elif evidence.pattern == ArchitecturalPattern.PHANTOM:
            parts.append("Phantom detection - likely not a real gap")

        return "; ".join(parts)
