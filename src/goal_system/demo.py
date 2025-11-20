#!/usr/bin/env python3
"""
Goal System Demo

Demonstrates goal tracking with consciousness integration.
"""

import sys
import logging
from pathlib import Path

# Use kloros home explicitly
sys.path.insert(0, '/home/kloros/src')

from goal_system import (
    GoalManager,
    Goal,
    GoalState,
    GoalProperties,
    integrate_goals_with_consciousness
)
from consciousness.integrated import IntegratedConsciousness

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)

logger = logging.getLogger(__name__)


def demo_basic_goal_system():
    """Demo: Basic goal CRUD operations."""
    print("\n=== DEMO 1: Basic Goal System ===\n")

    manager = GoalManager(persistence_path=Path("/tmp/demo_goals.json"))

    # Create a goal
    goal = manager.create_goal(
        goal_id="implement_feature_x",
        description="Implement feature X with tests",
        properties=GoalProperties(
            alignment_with_purpose=0.8,
            novelty=0.6,
            difficulty=0.7,
            impact=0.9,
            urgency=0.5
        ),
        auto_activate=True
    )

    print(f"Created goal: {goal.description}")
    print(f"  State: {goal.state.value}")
    print(f"  Progress: {goal.progress:.2f}")
    print(f"  Homeostatic pressure: {goal.homeostatic_pressure:.2f}")

    # Update progress
    print("\n--- Making progress... ---")
    manager.update_progress("implement_feature_x", 0.3)
    print(f"  Progress: {goal.progress:.2f}")
    print(f"  Progress delta: {goal.progress_delta:.2f}")

    # Block the goal
    print("\n--- Encountering obstacle... ---")
    manager.block_goal("implement_feature_x", reason="Dependency issue")
    print(f"  State: {goal.state.value}")

    # Unblock and continue
    print("\n--- Resolving obstacle... ---")
    manager.unblock_goal("implement_feature_x")
    manager.update_progress("implement_feature_x", 0.7)
    print(f"  State: {goal.state.value}")
    print(f"  Progress: {goal.progress:.2f}")

    # Complete
    print("\n--- Completing goal... ---")
    manager.update_progress("implement_feature_x", 1.0)
    print(f"  State: {goal.state.value}")
    print(f"  Completed at: {goal.completed_at}")

    # Summary
    print("\n--- Goal Manager Summary ---")
    summary = manager.get_status_summary()
    for key, value in summary.items():
        print(f"  {key}: {value}")


def demo_consciousness_integration():
    """Demo: Goals integrated with consciousness."""
    print("\n\n=== DEMO 2: Consciousness Integration ===\n")

    # Initialize consciousness (Phase 1 + Phase 2)
    consciousness = IntegratedConsciousness(
        enable_phase1=True,
        enable_phase2=True
    )

    # Initialize goal manager
    manager = GoalManager(persistence_path=Path("/tmp/demo_goals_consciousness.json"))

    # Integrate
    integrator = integrate_goals_with_consciousness(consciousness, manager)

    print("✅ Goal system integrated with consciousness\n")

    # Create goal - should trigger affective response
    print("--- Setting new goal ---")
    goal = manager.create_goal(
        goal_id="optimize_performance",
        description="Optimize system performance by 50%",
        properties=GoalProperties(
            alignment_with_purpose=0.9,
            impact=0.8,
            difficulty=0.6
        ),
        auto_activate=True
    )

    # Check affective state
    if consciousness.affective_core:
        mood = consciousness.affective_core.get_mood_description()
        print(f"  Mood after goal set: {mood}")

        dominant, intensity = consciousness.affective_core.emotions.get_dominant_emotion()
        print(f"  Dominant emotion: {dominant} ({intensity:.2f})")

    # Make progress - should generate positive affect
    print("\n--- Making significant progress ---")
    manager.update_progress("optimize_performance", 0.6)

    if consciousness.affective_core:
        mood = consciousness.affective_core.get_mood_description()
        print(f"  Mood after progress: {mood}")

    # Block goal - should generate frustration
    print("\n--- Goal blocked by external dependency ---")
    manager.block_goal("optimize_performance", reason="Waiting on library update")

    if consciousness.affective_core:
        mood = consciousness.affective_core.get_mood_description()
        print(f"  Mood after blocking: {mood}")

        dominant, intensity = consciousness.affective_core.emotions.get_dominant_emotion()
        print(f"  Dominant emotion: {dominant} ({intensity:.2f})")

    # Check homeostatic pressure
    print("\n--- Homeostatic State ---")
    homeostasis = consciousness.affective_core.homeostasis
    for name, var in homeostasis.items():
        if not var.satisfied:
            print(f"  ⚠️  {name}: {var.current:.2f} / {var.target:.2f} (pressure: {var.pressure:.2f})")
        else:
            print(f"  ✅ {name}: {var.current:.2f} / {var.target:.2f}")

    # Get goal-affect mapping
    print("\n--- Goal → Affect Mapping ---")
    mapping = integrator.get_goal_affect_mapping()
    for goal_id, affect_data in mapping.items():
        print(f"  Goal: {affect_data['goal_description']}")
        print(f"    Progress: {affect_data['progress']:.2f}")
        print(f"    Pressure: {affect_data['pressure']:.2f}")
        print(f"    State: {affect_data['state']}")


def demo_hierarchical_goals():
    """Demo: Hierarchical goal structures."""
    print("\n\n=== DEMO 3: Hierarchical Goals ===\n")

    manager = GoalManager(persistence_path=Path("/tmp/demo_goals_hierarchy.json"))

    # Create parent goal
    parent = manager.create_goal(
        goal_id="build_feature",
        description="Build complete feature",
        auto_activate=True
    )

    # Create subgoals
    subgoals = [
        ("design", "Design architecture"),
        ("implement", "Implement core logic"),
        ("test", "Write tests"),
        ("document", "Write documentation")
    ]

    for sid, desc in subgoals:
        manager.create_goal(
            goal_id=sid,
            description=desc,
            parent_id="build_feature"
        )

    print(f"Parent goal: {parent.description}")
    print(f"  Subgoals: {len(parent.subgoal_ids)}")

    # Show hierarchy
    print("\nGoal Hierarchy:")
    print(f"  ├─ {parent.description}")
    for subgoal_id in parent.subgoal_ids:
        subgoal = manager.get_goal(subgoal_id)
        print(f"     ├─ {subgoal.description} ({subgoal.state.value})")

    # Complete subgoals
    print("\n--- Completing subgoals ---")
    for subgoal_id in parent.subgoal_ids:
        manager.get_goal(subgoal_id).activate()
        manager.update_progress(subgoal_id, 1.0)
        print(f"  ✅ {subgoal_id} completed")

    # Update parent based on subgoal completion
    completed_subgoals = [
        manager.get_goal(sid) for sid in parent.subgoal_ids
        if manager.get_goal(sid).state == GoalState.COMPLETED
    ]
    parent_progress = len(completed_subgoals) / len(parent.subgoal_ids)
    manager.update_progress("build_feature", parent_progress)

    print(f"\nParent goal progress: {parent.progress:.0%}")


if __name__ == "__main__":
    print("=" * 60)
    print("  KLoROS Goal System Demo")
    print("=" * 60)

    try:
        demo_basic_goal_system()
        demo_consciousness_integration()
        demo_hierarchical_goals()

        print("\n" + "=" * 60)
        print("  All demos completed successfully!")
        print("=" * 60 + "\n")

    except Exception as e:
        logger.error(f"Demo failed: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)
