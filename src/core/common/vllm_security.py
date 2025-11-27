"""
vLLM Request Validation - CVE-2024-8939 Mitigation

Validates and sanitizes vLLM API requests to prevent DoS attacks
via the 'best_of' parameter vulnerability (CVE-2024-8939).

Usage:
    from src.core.common.vllm_security import VLLMRequestValidator

    # Validate before sending to vLLM
    safe_params = VLLMRequestValidator.validate_completion_params(request_params)
"""
from typing import Dict, Any


class VLLMRequestValidator:
    """
    Validate and sanitize vLLM requests to prevent DoS.

    Mitigates CVE-2024-8939: DoS via 'best_of' parameter.
    """

    MAX_BEST_OF = 5
    MAX_N = 10
    MAX_TOP_P = 1.0
    MIN_TOP_P = 0.0
    MAX_TEMPERATURE = 2.0
    MAX_MAX_TOKENS = 4096

    @classmethod
    def validate_completion_params(cls, params: Dict[str, Any]) -> Dict[str, Any]:
        """
        Validate and sanitize completion parameters.

        Args:
            params: Dictionary of completion parameters

        Returns:
            Sanitized parameters dictionary

        Raises:
            ValueError: If parameters are invalid or potentially malicious
        """
        if 'best_of' in params:
            best_of = params['best_of']
            if not isinstance(best_of, int):
                raise ValueError(f"best_of must be an integer, got {type(best_of)}")

            if best_of > cls.MAX_BEST_OF:
                raise ValueError(
                    f"best_of parameter exceeds maximum ({cls.MAX_BEST_OF}). "
                    f"Requested: {best_of}. This prevents DoS via CVE-2024-8939."
                )
            if best_of < 1:
                raise ValueError("best_of must be >= 1")

        if 'n' in params:
            n = params['n']
            if not isinstance(n, int):
                raise ValueError(f"n must be an integer, got {type(n)}")
            if n > cls.MAX_N:
                raise ValueError(f"n parameter exceeds maximum ({cls.MAX_N})")
            if n < 1:
                raise ValueError("n must be >= 1")

        if 'top_p' in params:
            top_p = params['top_p']
            if not isinstance(top_p, (int, float)):
                raise ValueError(f"top_p must be numeric, got {type(top_p)}")
            if not cls.MIN_TOP_P <= top_p <= cls.MAX_TOP_P:
                raise ValueError(
                    f"top_p must be between {cls.MIN_TOP_P} and {cls.MAX_TOP_P}"
                )

        if 'temperature' in params:
            temp = params['temperature']
            if not isinstance(temp, (int, float)):
                raise ValueError(f"temperature must be numeric, got {type(temp)}")
            if temp > cls.MAX_TEMPERATURE or temp < 0:
                raise ValueError(
                    f"temperature must be between 0 and {cls.MAX_TEMPERATURE}"
                )

        if 'max_tokens' in params:
            max_tokens = params['max_tokens']
            if not isinstance(max_tokens, int):
                raise ValueError(f"max_tokens must be an integer, got {type(max_tokens)}")
            if max_tokens > cls.MAX_MAX_TOKENS:
                raise ValueError(
                    f"max_tokens exceeds maximum ({cls.MAX_MAX_TOKENS})"
                )
            if max_tokens < 1:
                raise ValueError("max_tokens must be >= 1")

        return params

    @classmethod
    def get_safe_defaults(cls) -> Dict[str, Any]:
        """
        Get safe default parameters for vLLM completion.

        Returns:
            Dictionary with safe default values
        """
        return {
            'best_of': 1,
            'n': 1,
            'top_p': 0.95,
            'temperature': 0.7,
            'max_tokens': 2048
        }
