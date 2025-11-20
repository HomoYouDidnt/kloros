#!/usr/bin/env python3
"""Simple ChemBus Signal Test - Emit affective signals"""

import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))

from kloros.orchestration.chem_bus_v2 import ChemPub


chem_pub = ChemPub()

print("\n[test] Emitting AFFECT_MEMORY_PRESSURE...")
chem_pub.emit("AFFECT_MEMORY_PRESSURE", ecosystem="consciousness", intensity=0.75, 
              facts={'root_causes': ['high_token_usage'], 'evidence': ['Test signal']})
print("✅ AFFECT_MEMORY_PRESSURE emitted\n")

print("[test] Emitting AFFECT_HIGH_RAGE...")
chem_pub.emit("AFFECT_HIGH_RAGE", ecosystem="consciousness", intensity=0.85,
              facts={'root_causes': ['task_failures'], 'evidence': ['Test signal']})
print("✅ AFFECT_HIGH_RAGE emitted\n")

print("Check subscriber outputs for responses!")
