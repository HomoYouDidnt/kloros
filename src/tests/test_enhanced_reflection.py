#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Test script for KLoROS Enhanced Reflection System

Tests the integration and basic functionality of the enhanced reflection system.
"""

import sys
import os
import time
import json
from pathlib import Path

# Add the src directory to the Python path
sys.path.insert(0, '/home/kloros/src')

def test_enhanced_reflection_import():
    """Test that enhanced reflection system can be imported."""
    print("Testing enhanced reflection imports...")

    try:
        from src.cognition.mind.reflection import EnhancedIdleReflectionManager, get_config
        print(" Enhanced reflection system imports successful")
        return True
    except ImportError as e:
        print(f" Enhanced reflection import failed: {e}")
        return False

def test_configuration_system():
    """Test configuration system."""
    print("\nTesting configuration system...")

    try:
        from src.cognition.mind.reflection.config import get_config, ReflectionConfig

        config = get_config()
        print(f" Configuration loaded successfully")
        print(f"  - Reflection depth: {config.reflection_depth}")
        print(f"  - Semantic analysis: {config.enable_semantic_analysis}")
        print(f"  - Meta-cognition: {config.enable_meta_cognition}")
        print(f"  - Insight synthesis: {config.enable_insight_synthesis}")
        print(f"  - Adaptive optimization: {config.enable_adaptive_optimization}")
        return True
    except Exception as e:
        print(f" Configuration test failed: {e}")
        return False

def test_reflection_models():
    """Test reflection data models."""
    print("\nTesting reflection data models...")

    try:
        from src.cognition.mind.reflection.models import ReflectionInsight, InsightType, ConfidenceLevel

        # Create a test insight
        insight = ReflectionInsight.create_from_analysis(
            cycle=1,
            phase=1,
            insight_type=InsightType.TOPIC_EXTRACTION,
            title="Test Insight",
            content="This is a test insight for validation.",
            confidence=0.8
        )

        print(f" Reflection models working correctly")
        print(f"  - Created insight: {insight.title}")
        print(f"  - Confidence level: {insight.confidence_level}")
        return True
    except Exception as e:
        print(f" Models test failed: {e}")
        return False

def test_analyzers():
    """Test analyzer initialization."""
    print("\nTesting analyzer initialization...")

    try:
        from src.cognition.mind.reflection.config import get_config
        from src.cognition.mind.reflection.analyzers import (
            SemanticAnalyzer, MetaCognitiveAnalyzer,
            InsightSynthesizer, AdaptiveOptimizer
        )

        config = get_config()

        # Test analyzer initialization (without KLoROS instance)
        semantic = SemanticAnalyzer(config, None)
        meta_cog = MetaCognitiveAnalyzer(config, None)
        synthesizer = InsightSynthesizer(config, None)
        optimizer = AdaptiveOptimizer(config, None)

        print(" All analyzers initialized successfully")
        print(f"  - Semantic analyzer: Phase {semantic.phase_config.get('enabled', False)}")
        print(f"  - Meta-cognitive analyzer: Phase {meta_cog.phase_config.get('enabled', False)}")
        print(f"  - Insight synthesizer: Phase {synthesizer.phase_config.get('enabled', False)}")
        print(f"  - Adaptive optimizer: Phase {optimizer.phase_config.get('enabled', False)}")
        return True
    except Exception as e:
        print(f" Analyzers test failed: {e}")
        return False

def test_enhanced_manager():
    """Test enhanced reflection manager."""
    print("\nTesting enhanced reflection manager...")

    try:
        from src.cognition.mind.reflection import EnhancedIdleReflectionManager

        # Create manager without KLoROS instance
        manager = EnhancedIdleReflectionManager(None)

        # Test basic functionality
        stats = manager.get_reflection_statistics()
        print(" Enhanced reflection manager created successfully")
        print(f"  - Total cycles: {stats['total_cycles']}")
        print(f"  - System health: {stats['system_health']}")
        return True
    except Exception as e:
        print(f" Enhanced manager test failed: {e}")
        return False

def test_integration_with_main_reflection():
    """Test integration with main idle_reflection.py."""
    print("\nTesting integration with main reflection system...")

    try:
        # Import the main idle reflection system
        sys.path.insert(0, '/home/kloros/src')
        import importlib.util
        spec = importlib.util.spec_from_file_location("idle_reflection_main", "/home/kloros/src/idle_reflection.py")
        idle_reflection_main = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(idle_reflection_main)
        IdleReflectionManager = idle_reflection_main.IdleReflectionManager

        # Create manager without KLoROS instance
        manager = IdleReflectionManager(None)

        # Check if enhanced system is being used
        is_enhanced = manager.is_enhanced()
        info = manager.get_system_info()

        print(f" Main reflection system integration successful")
        print(f"  - Using enhanced system: {is_enhanced}")
        print(f"  - Enhanced available: {info['enhanced_available']}")

        if is_enhanced:
            print(f"  - Analysis depth: {info.get('analysis_depth', 'N/A')}")

        return True
    except Exception as e:
        print(f" Integration test failed: {e}")
        return False

def test_memory_database_access():
    """Test memory database access (if available)."""
    print("\nTesting memory database access...")

    memory_db_path = "/home/kloros/.kloros/memory.db"

    if not os.path.exists(memory_db_path):
        print("� Memory database not found - skipping database test")
        return True

    try:
        import sqlite3

        conn = sqlite3.connect(memory_db_path)
        cursor = conn.cursor()

        # Check if events table exists
        cursor.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='events';")
        result = cursor.fetchone()

        if result:
            # Get event count
            cursor.execute("SELECT COUNT(*) FROM events")
            event_count = cursor.fetchone()[0]
            print(f" Memory database accessible")
            print(f"  - Total events: {event_count}")
        else:
            print("� Events table not found in memory database")

        conn.close()
        return True
    except Exception as e:
        print(f" Memory database test failed: {e}")
        return False

def run_all_tests():
    """Run all tests and provide summary."""
    print("=" * 60)
    print("KLoROS Enhanced Reflection System - Integration Tests")
    print("=" * 60)

    tests = [
        test_enhanced_reflection_import,
        test_configuration_system,
        test_reflection_models,
        test_analyzers,
        test_enhanced_manager,
        test_integration_with_main_reflection,
        test_memory_database_access
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
    print("\n" + "=" * 60)
    print("TEST SUMMARY")
    print("=" * 60)

    passed = sum(results)
    total = len(results)

    print(f"Tests passed: {passed}/{total}")

    if passed == total:
        print("<� ALL TESTS PASSED - Enhanced Reflection System Ready!")
    elif passed >= total * 0.8:
        print(" Most tests passed - System mostly functional")
    else:
        print("L Multiple test failures - System needs attention")

    return passed == total

if __name__ == "__main__":
    success = run_all_tests()
    sys.exit(0 if success else 1)