#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Test script for KLoROS Hybrid Introspection System

Tests the real-time introspection capabilities integrated with the enhanced reflection system.
"""

import sys
import os
import time
import uuid
from pathlib import Path

# Add the src directory to the Python path
sys.path.insert(0, '/home/kloros/src')

def test_hybrid_introspection_import():
    """Test that hybrid introspection system can be imported."""
    print("Testing hybrid introspection imports...")

    try:
        from src.cognition.mind.reflection.hybrid_introspection import HybridIntrospectionManager, IntrospectionTrigger, ConversationQuality
        print(" Hybrid introspection system imports successful")
        return True
    except ImportError as e:
        print(f" Hybrid introspection import failed: {e}")
        return False

def test_real_time_conversation_analysis():
    """Test real-time conversation analysis."""
    print("\nTesting real-time conversation analysis...")

    try:
        from src.cognition.mind.reflection.hybrid_introspection import HybridIntrospectionManager

        # Create hybrid introspection manager
        manager = HybridIntrospectionManager(None)

        # Start conversation
        conversation_id = str(uuid.uuid4())
        manager.start_conversation_introspection(conversation_id)

        print(" Conversation introspection started")
        print(f"  - Conversation ID: {conversation_id[:8]}...")

        # Test user input analysis
        test_inputs = [
            "Hello, can you help me with machine learning?",
            "I don't understand what you mean by neural networks",
            "Can you clarify what a neural network is?",  # Repeated question
            "What's the difference between supervised and unsupervised learning?"
        ]

        total_insights = 0
        for i, user_input in enumerate(test_inputs):
            insights = manager.analyze_user_input(user_input)
            total_insights += len(insights)
            print(f"  - Input {i+1}: {len(insights)} insights generated")

            # Test adaptive parameters
            adaptive_params = manager.get_adaptive_parameters()
            complexity = adaptive_params.get('complexity_level', 0)
            style = adaptive_params.get('response_style', 'unknown')
            print(f"    • Complexity: {complexity:.2f}, Style: {style}")

        # Test response analysis
        test_response = "Machine learning is a fascinating field that involves algorithms learning patterns from data to make predictions or decisions."
        response_time = 1500  # 1.5 seconds

        response_insights = manager.analyze_response_quality(test_response, response_time)
        total_insights += len(response_insights)
        print(f"  - Response analysis: {len(response_insights)} insights")

        # End conversation
        summary = manager.end_conversation_introspection()
        print(" Conversation introspection completed")
        print(f"  - Duration: {summary.get('duration_seconds', 0):.1f}s")
        print(f"  - Total insights: {summary.get('total_insights', 0)}")
        print(f"  - User inputs: {summary.get('user_inputs', 0)}")

        return True
    except Exception as e:
        print(f" Real-time conversation analysis test failed: {e}")
        return False

def test_enhanced_reflection_with_hybrid():
    """Test enhanced reflection system with hybrid integration."""
    print("\nTesting enhanced reflection with hybrid integration...")

    try:
        from src.cognition.mind.reflection import EnhancedIdleReflectionManager

        # Create enhanced manager (includes hybrid)
        manager = EnhancedIdleReflectionManager(None)

        print(" Enhanced reflection manager with hybrid created")

        # Test hybrid interface methods
        conversation_id = str(uuid.uuid4())
        manager.start_conversation_introspection(conversation_id)

        # Test input analysis
        insights = manager.analyze_user_input("How does the reflection system work?")
        print(f"  - User input analysis: {len(insights)} insights")

        # Test response analysis
        response_insights = manager.analyze_response_quality(
            "The reflection system uses multiple phases for self-analysis.",
            2000
        )
        print(f"  - Response analysis: {len(response_insights)} insights")

        # Test adaptive parameters
        adaptive_params = manager.get_adaptive_parameters()
        print(f"  - Adaptive parameters: {len(adaptive_params)} parameters")

        # Test hybrid statistics
        hybrid_stats = manager.get_hybrid_statistics()
        print(" Hybrid statistics retrieved")
        print(f"  - Real-time enabled: {hybrid_stats.get('hybrid_introspection', {}).get('real_time_enabled', False)}")

        # End conversation
        summary = manager.end_conversation_introspection()
        print(f"  - Conversation summary: {summary.get('total_insights', 0)} insights")

        return True
    except Exception as e:
        print(f" Enhanced reflection with hybrid test failed: {e}")
        return False

def test_main_interface_integration():
    """Test main idle reflection interface with hybrid methods."""
    print("\nTesting main interface hybrid integration...")

    try:
        import importlib.util
        spec = importlib.util.spec_from_file_location("idle_reflection_main", "/home/kloros/src/idle_reflection.py")
        idle_reflection_main = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(idle_reflection_main)
        IdleReflectionManager = idle_reflection_main.IdleReflectionManager

        # Create manager
        manager = IdleReflectionManager(None)

        print(" Main idle reflection manager created")

        if manager.is_enhanced():
            print("  - Enhanced mode active")

            # Test hybrid methods
            conversation_id = str(uuid.uuid4())
            manager.start_conversation_introspection(conversation_id)

            # Test user input analysis
            result = manager.analyze_user_input("Test input for analysis")
            insights = result.get('insights', [])
            adaptive_params = result.get('adaptive_parameters', {})

            print(f"  - User analysis: {len(insights)} insights, {len(adaptive_params)} parameters")

            # Test response analysis
            result = manager.analyze_response_quality("Test response", 1000)
            print(f"  - Response analysis: {len(result.get('insights', []))} insights")

            # Test hybrid statistics
            hybrid_stats = manager.get_hybrid_statistics()
            print(f"  - Hybrid statistics available: {'hybrid_introspection' in hybrid_stats}")

            # End conversation
            summary = manager.end_conversation_introspection()
            print(f"  - Conversation ended: {summary.get('total_insights', 0)} total insights")

        else:
            print("  - Basic mode (hybrid features not available)")

        return True
    except Exception as e:
        print(f" Main interface integration test failed: {e}")
        return False

def test_adaptive_parameter_scenarios():
    """Test adaptive parameter generation in different scenarios."""
    print("\nTesting adaptive parameter scenarios...")

    try:
        from src.cognition.mind.reflection.hybrid_introspection import HybridIntrospectionManager

        manager = HybridIntrospectionManager(None)
        conversation_id = str(uuid.uuid4())
        manager.start_conversation_introspection(conversation_id)

        scenarios = [
            {
                "name": "Technical User",
                "inputs": [
                    "Can you explain the computational complexity of neural network training?",
                    "What are the implications of gradient descent optimization?"
                ],
                "expected_complexity": "high"
            },
            {
                "name": "Confused User",
                "inputs": [
                    "I don't understand",
                    "Can you clarify what you mean?",
                    "I'm confused about this"
                ],
                "expected_style": "simple_friendly"
            },
            {
                "name": "Casual User",
                "inputs": [
                    "Hello",
                    "How are you?",
                    "Thanks for your help"
                ],
                "expected_complexity": "low"
            }
        ]

        for scenario in scenarios:
            print(f"  - Testing {scenario['name']} scenario:")

            for user_input in scenario['inputs']:
                manager.analyze_user_input(user_input)

            adaptive_params = manager.get_adaptive_parameters()
            complexity = adaptive_params.get('complexity_level', 0)
            style = adaptive_params.get('response_style', 'unknown')
            urgency = adaptive_params.get('urgency_level', 0)

            print(f"    • Complexity: {complexity:.2f}")
            print(f"    • Style: {style}")
            print(f"    • Urgency: {urgency:.2f}")

        manager.end_conversation_introspection()
        print("✓ Adaptive parameter scenarios completed")

        return True
    except Exception as e:
        print(f" Adaptive parameter scenarios test failed: {e}")
        return False

def run_all_tests():
    """Run all hybrid introspection tests."""
    print("=" * 70)
    print("KLoROS Hybrid Introspection System - Integration Tests")
    print("=" * 70)

    tests = [
        test_hybrid_introspection_import,
        test_real_time_conversation_analysis,
        test_enhanced_reflection_with_hybrid,
        test_main_interface_integration,
        test_adaptive_parameter_scenarios
    ]

    results = []
    for test in tests:
        try:
            result = test()
            results.append(result)
        except Exception as e:
            print(f" Test {test.__name__} crashed: {e}")
            results.append(False)

    # Summary
    print("\n" + "=" * 70)
    print("TEST SUMMARY")
    print("=" * 70)

    passed = sum(results)
    total = len(results)

    print(f"Tests passed: {passed}/{total}")

    if passed == total:
        print("<� ALL TESTS PASSED - Hybrid Introspection System Ready!")
    elif passed >= total * 0.8:
        print("� Most tests passed - System mostly functional")
    else:
        print("L Multiple test failures - System needs attention")

    return passed == total

if __name__ == "__main__":
    success = run_all_tests()
    sys.exit(0 if success else 1)