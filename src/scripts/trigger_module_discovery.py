#!/usr/bin/env python3
"""
Trigger fresh module discovery investigations by emitting chemical signals.

This bypasses the evidence hash filter by directly emitting Q_CURIOSITY_INVESTIGATE
signals for all undiscovered modules.
"""

import sys
sys.path.insert(0, '/home/kloros/src')

from src.orchestration.core.chem_bus_v2 import ChemPub
from registry.curiosity_core import ModuleDiscoveryMonitor
import time

def main():
    print("=" * 60)
    print("Triggering Module Discovery Investigations")
    print("=" * 60)

    # Get module discovery questions
    monitor = ModuleDiscoveryMonitor()
    questions = monitor.generate_discovery_questions()

    print(f"\nFound {len(questions)} module discovery questions")

    # Initialize chemical signal publisher
    pub = ChemPub()

    # Emit signal for each discovery question
    for i, question in enumerate(questions, 1):
        print(f"\n{i}. Emitting signal for: {question.id}")
        print(f"   Question: {question.question[:80]}...")

        # Create facts payload matching what investigation_consumer expects
        facts = {
            "question_id": question.id,
            "question": question.question,
            "hypothesis": question.hypothesis,
            "evidence": question.evidence,
            "action_class": question.action_class.value if hasattr(question.action_class, 'value') else str(question.action_class),
            "autonomy": question.autonomy,
            "value_estimate": question.value_estimate,
            "cost": question.cost
        }

        # Emit Q_CURIOSITY_INVESTIGATE signal
        pub.emit(
            signal="Q_CURIOSITY_INVESTIGATE",
            ecosystem="curiosity",
            intensity=1.0,
            facts=facts,
            incident_id=f"manual_trigger_{question.id}_{int(time.time())}"
        )

        print(f"   ✓ Signal emitted")

        # Small delay to avoid overwhelming the consumer
        time.sleep(0.5)

    print(f"\n{'=' * 60}")
    print(f"✅ Emitted {len(questions)} investigation signals")
    print(f"{'=' * 60}")
    print("\nInvestigation consumer should start processing these within seconds.")
    print("Check logs: journalctl --user -u kloros-investigation-consumer@1.service -f")

if __name__ == '__main__':
    main()
