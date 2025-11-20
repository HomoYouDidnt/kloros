"""Dashboard Card Validator for D-REAM Admission Gates

Ensures all candidates have complete metadata cards before admission.
Prevents "sparse cards" (missing metrics, costs, or lineage).

Required Fields for Complete Dashboard Card:
- judge_version: Frozen judge version hash
- kl_delta: KL divergence from anchor distribution
- synthetic_pct: % of training data that is synthetic
- diversity: Candidate diversity metric (cosine distance from cluster centroids)
- latency_ms: Inference latency
- cost_usd: Estimated cost per invocation
- wins: Number of A/B test wins
- losses: Number of A/B test losses
"""

import logging
from typing import Dict, List, Tuple, Optional
from dataclasses import dataclass

logger = logging.getLogger(__name__)

# Required fields for complete dashboard card
REQUIRED_CARD_FIELDS = [
    "judge_version",
    "kl_delta",
    "synthetic_pct",
    "diversity",
    "latency_ms",
    "cost_usd",
    "wins",
    "losses"
]

# Optional fields (warnings if missing, but not blockers)
OPTIONAL_CARD_FIELDS = [
    "token_count",
    "tool_calls_count",
    "error_rate",
    "robustness_score"
]


@dataclass
class CardValidationResult:
    """Result of dashboard card validation."""
    is_valid: bool
    missing_fields: List[str]
    warnings: List[str]
    candidate_id: str


class DashboardCardValidator:
    """Validates that candidates have complete dashboard cards.

    Prevents admission of candidates with incomplete metadata.
    This ensures the dashboard can display meaningful comparisons
    and prevents "dark launches" where candidates lack tracking.

    Example:
        >>> validator = DashboardCardValidator()
        >>> result = validator.validate_card(candidate_metrics, candidate_id)
        >>> if result.is_valid:
        ...     print("Card is complete, admit candidate")
        ... else:
        ...     print(f"Missing fields: {result.missing_fields}")
    """

    def __init__(self, strict_mode: bool = True):
        """Initialize validator.

        Args:
            strict_mode: If True, reject candidates with any missing required fields.
                        If False, log warnings but allow admission.
        """
        self.strict_mode = strict_mode

    def validate_card(
        self,
        metrics: Dict,
        candidate_id: str
    ) -> CardValidationResult:
        """Validate a candidate's dashboard card.

        Args:
            metrics: Candidate metrics dictionary
            candidate_id: Candidate identifier

        Returns:
            CardValidationResult with validation status
        """
        missing_fields = []
        warnings = []

        # Check required fields
        for field in REQUIRED_CARD_FIELDS:
            if field not in metrics:
                missing_fields.append(field)
            elif metrics[field] is None:
                missing_fields.append(f"{field} (null)")

        # Check optional fields (warnings only)
        for field in OPTIONAL_CARD_FIELDS:
            if field not in metrics:
                warnings.append(f"Optional field '{field}' missing")

        # Validate field values (basic sanity checks)
        if "kl_delta" in metrics:
            if metrics["kl_delta"] < 0:
                warnings.append("kl_delta is negative (expected >= 0)")

        if "synthetic_pct" in metrics:
            if not 0 <= metrics["synthetic_pct"] <= 100:
                warnings.append("synthetic_pct out of range [0, 100]")

        if "diversity" in metrics:
            if metrics["diversity"] < 0:
                warnings.append("diversity is negative (expected >= 0)")

        if "latency_ms" in metrics:
            if metrics["latency_ms"] < 0:
                warnings.append("latency_ms is negative")

        if "cost_usd" in metrics:
            if metrics["cost_usd"] < 0:
                warnings.append("cost_usd is negative")

        # Determine validity
        is_valid = len(missing_fields) == 0 if self.strict_mode else True

        if missing_fields:
            logger.warning(
                "[dashboard_card] Candidate '%s' has incomplete card: missing %s",
                candidate_id,
                missing_fields
            )

        if warnings:
            logger.debug(
                "[dashboard_card] Candidate '%s' card warnings: %s",
                candidate_id,
                warnings
            )

        return CardValidationResult(
            is_valid=is_valid,
            missing_fields=missing_fields,
            warnings=warnings,
            candidate_id=candidate_id
        )

    def validate_batch(
        self,
        candidates: List[Dict],
        candidate_ids: List[str]
    ) -> Tuple[List[int], List[int]]:
        """Validate a batch of candidates.

        Args:
            candidates: List of candidate metrics dictionaries
            candidate_ids: List of candidate identifiers

        Returns:
            Tuple of (valid_indices, invalid_indices)
        """
        valid_indices = []
        invalid_indices = []

        for i, (metrics, cid) in enumerate(zip(candidates, candidate_ids)):
            result = self.validate_card(metrics, cid)

            if result.is_valid:
                valid_indices.append(i)
            else:
                invalid_indices.append(i)

        logger.info(
            "[dashboard_card] Batch validation: %d valid, %d invalid (strict=%s)",
            len(valid_indices),
            len(invalid_indices),
            self.strict_mode
        )

        return valid_indices, invalid_indices


def validate_candidate_card(
    metrics: Dict,
    candidate_id: str,
    strict: bool = True
) -> bool:
    """Convenience function to validate a single candidate card.

    Args:
        metrics: Candidate metrics
        candidate_id: Candidate ID
        strict: Strict validation mode

    Returns:
        True if card is valid, False otherwise
    """
    validator = DashboardCardValidator(strict_mode=strict)
    result = validator.validate_card(metrics, candidate_id)
    return result.is_valid


def get_missing_fields(metrics: Dict) -> List[str]:
    """Get list of missing required fields from metrics.

    Args:
        metrics: Candidate metrics

    Returns:
        List of missing field names
    """
    missing = []
    for field in REQUIRED_CARD_FIELDS:
        if field not in metrics or metrics[field] is None:
            missing.append(field)
    return missing
