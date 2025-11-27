#!/usr/bin/env python3
"""
Test script to trigger component self-study and verify end-to-end flow.
"""

import sys
import time
import logging
from pathlib import Path

sys.path.insert(0, str(Path.home() / "src"))

from component_self_study import ComponentSelfStudy

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)

def main():
    """Trigger a component study to test the bridge."""

    print("\n=== Testing Component Self-Study Flow ===\n")

    study_system = ComponentSelfStudy()

    test_component = "/home/kloros/src/kloros/orchestration/chem_bus_v2.py"

    print(f"Triggering study of: {test_component}")
    print("This should emit LEARNING_COMPLETED signal on ChemBus")
    print("Which should be captured by klr-study-memory-bridge service\n")

    study_system.study_component(
        component_path=test_component,
        component_type="module",
        target_depth=2
    )

    print("\nStudy completed. Check:")
    print("1. Service logs: sudo journalctl -u klr-study-memory-bridge -f")
    print("2. Memory events: python3 -c \"import sqlite3; conn = sqlite3.connect('/home/kloros/.kloros/memory.db'); cursor = conn.cursor(); cursor.execute('SELECT event_type, content FROM events ORDER BY timestamp DESC LIMIT 5'); [print(row) for row in cursor.fetchall()]\"")
    print("3. Qdrant collection: curl -s http://localhost:6333/collections/kloros_memory | python3 -m json.tool | grep points_count\n")

if __name__ == "__main__":
    main()
