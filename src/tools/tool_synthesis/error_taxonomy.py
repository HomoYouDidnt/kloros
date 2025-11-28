"""
Error taxonomy for intelligent fallback routing.

Maps exception types to error codes for targeted remediation.
"""

from enum import Enum
from typing import Optional, Type
import re


class ErrorCode(Enum):
    """Standardized error codes for taxonomy."""
    RATE_LIMIT = "RATE_LIMIT"
    UPSTREAM = "UPSTREAM"
    TIMEOUT = "TIMEOUT"
    AUTH = "AUTH"
    NOT_FOUND = "NOT_FOUND"
    VALIDATION = "VALIDATION"
    UNKNOWN = "UNKNOWN"


class ErrorTaxonomy:
    """Classifies exceptions into error codes for fallback routing."""

    # Exception patterns for classification
    PATTERNS = {
        ErrorCode.RATE_LIMIT: [
            r"rate.?limit",
            r"429",
            r"too.?many.?requests",
            r"quota.?exceeded",
        ],
        ErrorCode.UPSTREAM: [
            r"upstream",
            r"503",
            r"502",
            r"bad.?gateway",
            r"service.?unavailable",
        ],
        ErrorCode.TIMEOUT: [
            r"timeout",
            r"timed.?out",
            r"504",
            r"gateway.?timeout",
        ],
        ErrorCode.AUTH: [
            r"auth",
            r"401",
            r"403",
            r"unauthorized",
            r"forbidden",
            r"permission.?denied",
        ],
        ErrorCode.NOT_FOUND: [
            r"not.?found",
            r"404",
            r"no.?such",
        ],
        ErrorCode.VALIDATION: [
            r"validation",
            r"invalid",
            r"400",
            r"bad.?request",
        ],
    }

    @classmethod
    def classify(cls, exception: Exception) -> ErrorCode:
        """
        Classify an exception into an error code.

        Args:
            exception: The exception to classify

        Returns:
            ErrorCode representing the error category
        """
        # Check exception type first
        exc_type = type(exception).__name__.lower()
        exc_msg = str(exception).lower()

        # Check for specific exception types
        if "ratelimit" in exc_type:
            return ErrorCode.RATE_LIMIT
        if "timeout" in exc_type:
            return ErrorCode.TIMEOUT
        if "auth" in exc_type or "permission" in exc_type:
            return ErrorCode.AUTH
        if "notfound" in exc_type or "doesnotexist" in exc_type:
            return ErrorCode.NOT_FOUND
        if "validation" in exc_type:
            return ErrorCode.VALIDATION

        # Pattern matching on message
        combined_text = f"{exc_type} {exc_msg}"

        for error_code, patterns in cls.PATTERNS.items():
            for pattern in patterns:
                if re.search(pattern, combined_text, re.IGNORECASE):
                    return error_code

        return ErrorCode.UNKNOWN

    @classmethod
    def get_remediation(cls, error_code: ErrorCode, manifest: dict) -> Optional[dict]:
        """
        Get remediation strategy from manifest for an error code.

        Args:
            error_code: The error code
            manifest: Skill manifest

        Returns:
            Remediation dict with strategy and fallback info
        """
        taxonomy = manifest.get("error_taxonomy", [])

        for entry in taxonomy:
            if entry.get("code") == error_code.value:
                remediation = entry.get("remediation", "")

                # Parse remediation string
                if remediation.startswith("fallback:"):
                    skill = remediation.split(":", 1)[1]
                    return {
                        "strategy": "fallback",
                        "skill": skill,
                        "retry": False
                    }
                elif remediation.startswith("retry_then_fallback:"):
                    skill = remediation.split(":", 1)[1]
                    return {
                        "strategy": "retry_then_fallback",
                        "skill": skill,
                        "retry": True
                    }
                elif remediation == "retry":
                    return {
                        "strategy": "retry",
                        "retry": True
                    }

        return None

    @classmethod
    def find_fallback_for_error(cls, error_code: ErrorCode, manifest: dict) -> Optional[str]:
        """
        Find the appropriate fallback skill for an error code.

        Args:
            error_code: The error code
            manifest: Skill manifest

        Returns:
            Fallback skill name or None
        """
        remediation = cls.get_remediation(error_code, manifest)
        if remediation:
            return remediation.get("skill")

        # Default: use first fallback if error_taxonomy doesn't specify
        fallbacks = manifest.get("fallbacks", [])
        if fallbacks:
            return fallbacks[0].get("skill")

        return None
