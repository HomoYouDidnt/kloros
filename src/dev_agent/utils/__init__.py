"""Utility modules for Dev Agent."""
from .diff_apply import apply_unified_diff, PatchError

__all__ = ["apply_unified_diff", "PatchError"]
