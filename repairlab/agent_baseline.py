"""
Baseline No-Op Repair Agent

This baseline agent makes no changes to the code.
Useful for establishing baseline fitness scores before applying
real repair strategies.

Agent Contract:
    repair(bundle_dir: str) -> None
"""

def repair(bundle_dir: str) -> None:
    """No-op baseline: makes no changes to code."""
    # Baseline does nothing - used to establish floor fitness
    pass
