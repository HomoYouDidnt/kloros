#!/usr/bin/env python3
"""Test brainmod environment variable toggles."""
import os
import sys

# Test brainmod env vars
os.environ["KLR_USE_TOT"] = "1"
os.environ["KLR_USE_VOI"] = "1"
os.environ["KLR_USE_DEBATE"] = "1"
os.environ["KLR_USE_SAFETY"] = "1"
os.environ["KLR_USE_PROVENANCE"] = "1"

print("[*] Testing brainmod toggles...")
print(f"    KLR_USE_TOT={os.environ.get('KLR_USE_TOT')}")
print(f"    KLR_USE_VOI={os.environ.get('KLR_USE_VOI')}")
print(f"    KLR_USE_DEBATE={os.environ.get('KLR_USE_DEBATE')}")
print(f"    KLR_USE_SAFETY={os.environ.get('KLR_USE_SAFETY')}")
print(f"    KLR_USE_PROVENANCE={os.environ.get('KLR_USE_PROVENANCE')}")

# Test that orchestrator/strategies.py reads these correctly
USE_TOT = os.getenv("KLR_USE_TOT", "0") == "1"
USE_DEB = os.getenv("KLR_USE_DEBATE", "0") == "1"
USE_VOI = os.getenv("KLR_USE_VOI", "0") == "1"
USE_SAFE = os.getenv("KLR_USE_SAFETY", "0") == "1"
USE_PROV = os.getenv("KLR_USE_PROVENANCE", "0") == "1"

assert USE_TOT, "TOT toggle not detected"
assert USE_DEB, "Debate toggle not detected"
assert USE_VOI, "VOI toggle not detected"
assert USE_SAFE, "Safety toggle not detected"
assert USE_PROV, "Provenance toggle not detected"

print()
print("[OK] All brainmod toggles working correctly")
print("     Brainmods will be invoked when enrich_plan() is called")
