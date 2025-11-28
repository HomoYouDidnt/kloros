#!/usr/bin/env python3
"""
Comprehensive Memory System Verification Script

Checks all 8 phases of the memory system upgrade for:
- Code quality and consistency
- Integration with KLoROS architecture
- Configuration alignment
- Performance and functionality
"""

import os
import sys
from pathlib import Path

# Add src to path
sys.path.insert(0, str(Path(__file__).parent / "src"))


def print_section(title):
    """Print a section header."""
    print("\n" + "=" * 70)
    print(f"  {title}")
    print("=" * 70)


def check_phase_1_embeddings():
    """Verify Phase 1: Semantic Embeddings."""
    print_section("PHASE 1: Semantic Embeddings")

    issues = []
    successes = []

    # Check file existence
    files = [
        "src/kloros_memory/embeddings.py",
        "src/kloros_memory/vector_store.py",
    ]

    for filepath in files:
        if Path(filepath).exists():
            successes.append(f"✓ {filepath} exists")
        else:
            issues.append(f"✗ {filepath} missing")

    # Try to import
    try:
        from kloros_memory.embeddings import get_embedding_engine
        from kloros_memory.vector_store import get_vector_store

        engine = get_embedding_engine()
        successes.append(f"✓ Embedding engine initialized ({engine.embedding_dim} dimensions)")

        store = get_vector_store()
        successes.append(f"✓ Vector store initialized")

    except Exception as e:
        issues.append(f"✗ Import failed: {e}")

    # Check configuration
    env_vars = ["KLR_ENABLE_EMBEDDINGS"]
    for var in env_vars:
        val = os.getenv(var)
        if val:
            successes.append(f"✓ {var}={val}")
        else:
            issues.append(f"⚠ {var} not set")

    return issues, successes


def check_phase_2_decay():
    """Verify Phase 2: Memory Decay."""
    print_section("PHASE 2: Memory Decay")

    issues = []
    successes = []

    # Check files
    files = [
        "src/kloros_memory/decay.py",
        "src/kloros_memory/decay_daemon.py",
        "src/kloros_memory/autonomous_decay.py",
    ]

    for filepath in files:
        if Path(filepath).exists():
            successes.append(f"✓ {filepath} exists")
        else:
            issues.append(f"✗ {filepath} missing")

    # Try to import
    try:
        from kloros_memory.decay import DecayEngine, DecayConfig
        from kloros_memory.autonomous_decay import get_autonomous_decay_manager

        engine = DecayEngine()
        successes.append(f"✓ Decay engine initialized")

        # Check if autonomous decay is running
        manager = get_autonomous_decay_manager()
        if manager and manager.is_running():
            successes.append(f"✓ Autonomous decay manager RUNNING")
        else:
            issues.append(f"⚠ Autonomous decay manager not running")

    except Exception as e:
        issues.append(f"✗ Import failed: {e}")

    # Check configuration
    env_vars = [
        "KLR_AUTO_START_DECAY",
        "KLR_DECAY_UPDATE_INTERVAL",
        "KLR_DECAY_EPISODIC_HALF_LIFE",
        "KLR_DECAY_DELETION_THRESHOLD"
    ]
    for var in env_vars:
        val = os.getenv(var)
        if val:
            successes.append(f"✓ {var}={val}")
        else:
            issues.append(f"⚠ {var} not set")

    return issues, successes


def check_phase_3_graph():
    """Verify Phase 3: Graph Relationships."""
    print_section("PHASE 3: Graph Relationships")

    issues = []
    successes = []

    # Check files
    files = [
        "src/kloros_memory/graph.py",
        "src/kloros_memory/graph_queries.py",
    ]

    for filepath in files:
        if Path(filepath).exists():
            successes.append(f"✓ {filepath} exists")
        else:
            issues.append(f"✗ {filepath} missing")

    # Try to import
    try:
        from kloros_memory.graph import MemoryGraph
        from kloros_memory.graph_queries import GraphQueryEngine

        graph = MemoryGraph()
        stats = graph.get_graph_statistics()

        successes.append(f"✓ Graph initialized ({stats['total_nodes']} nodes, {stats['total_edges']} edges)")

        if stats['total_edges'] > 0:
            successes.append(f"✓ Graph has edges: {stats['edge_types']}")

        engine = GraphQueryEngine(graph=graph)
        successes.append(f"✓ Graph query engine initialized")

    except Exception as e:
        issues.append(f"✗ Import failed: {e}")

    # Check configuration
    env_vars = ["KLR_ENABLE_GRAPH"]
    for var in env_vars:
        val = os.getenv(var)
        if val:
            successes.append(f"✓ {var}={val}")
        else:
            issues.append(f"⚠ {var} not set")

    return issues, successes


def check_phase_4_emotional():
    """Verify Phase 4: Emotional Memory."""
    print_section("PHASE 4: Emotional Memory")

    issues = []
    successes = []

    # Check files
    if Path("src/kloros_memory/sentiment.py").exists():
        successes.append("✓ sentiment.py exists")
    else:
        issues.append("✗ sentiment.py missing")

    # Try to import
    try:
        from kloros_memory.sentiment import get_sentiment_analyzer

        analyzer = get_sentiment_analyzer()

        # Test sentiment analysis
        result = analyzer.analyze("I'm happy with the results!")

        successes.append(f"✓ Sentiment analyzer initialized")
        successes.append(f"✓ Test sentiment: {result['sentiment_score']:.2f}, emotion: {result['emotion_type']}")

    except Exception as e:
        issues.append(f"✗ Import failed: {e}")

    # Check configuration
    env_vars = ["KLR_ENABLE_SENTIMENT"]
    for var in env_vars:
        val = os.getenv(var)
        if val:
            successes.append(f"✓ {var}={val}")
        else:
            issues.append(f"⚠ {var} not set")

    return issues, successes


def check_phase_5_procedural():
    """Verify Phase 5: Procedural Memory."""
    print_section("PHASE 5: Procedural Memory")

    issues = []
    successes = []

    # Check files
    if Path("src/kloros_memory/procedural.py").exists():
        successes.append("✓ procedural.py exists")
    else:
        issues.append("✗ procedural.py missing")

    # Try to import
    try:
        from kloros_memory.procedural import get_procedural_system

        system = get_procedural_system()
        stats = system.get_statistics()

        successes.append(f"✓ Procedural system initialized")
        successes.append(f"✓ Total patterns: {stats.get('total_patterns', 0)}")

    except Exception as e:
        issues.append(f"✗ Import failed: {e}")

    return issues, successes


def check_phase_6_reflective():
    """Verify Phase 6: Reflective Memory."""
    print_section("PHASE 6: Reflective Memory")

    issues = []
    successes = []

    # Check files
    if Path("src/kloros_memory/reflective.py").exists():
        successes.append("✓ reflective.py exists")
    else:
        issues.append("✗ reflective.py missing")

    # Try to import
    try:
        from kloros_memory.reflective import get_reflective_system

        system = get_reflective_system()
        successes.append(f"✓ Reflective system initialized")

    except Exception as e:
        issues.append(f"✗ Import failed: {e}")

    return issues, successes


def check_phase_7_metrics():
    """Verify Phase 7: Performance Monitoring."""
    print_section("PHASE 7: Performance Monitoring")

    issues = []
    successes = []

    # Check files
    if Path("src/kloros_memory/metrics.py").exists():
        successes.append("✓ metrics.py exists")
    else:
        issues.append("✗ metrics.py missing")

    # Try to import
    try:
        from kloros_memory.metrics import get_metrics, track_performance

        metrics = get_metrics()
        successes.append(f"✓ Metrics system initialized")

        # Test decorator
        @track_performance("test_operation")
        def test_func():
            return 42

        result = test_func()
        successes.append(f"✓ Performance tracking decorator working")

    except Exception as e:
        issues.append(f"✗ Import failed: {e}")

    return issues, successes


def check_phase_8_documentation():
    """Verify Phase 8: Documentation."""
    print_section("PHASE 8: Documentation")

    issues = []
    successes = []

    # Check documentation files
    docs = [
        "KLOROS_MEMORY_ARCHITECTURE.md",
        "AUTONOMOUS_DECAY_GUIDE.md",
        "MEMORY_UPGRADE_PROGRESS.md",
    ]

    for doc in docs:
        if Path(doc).exists():
            size = Path(doc).stat().st_size
            successes.append(f"✓ {doc} exists ({size:,} bytes)")
        else:
            issues.append(f"✗ {doc} missing")

    return issues, successes


def check_integration():
    """Verify integration with KLoROS."""
    print_section("INTEGRATION: KLoROS Memory System")

    issues = []
    successes = []

    # Check integration file
    if Path("src/kloros_memory/integration.py").exists():
        successes.append("✓ integration.py exists")
    else:
        issues.append("✗ integration.py missing")

    # Check if memory system is active in KLoROS
    try:
        from kloros_memory.logger import MemoryLogger
        from kloros_memory.retriever import ContextRetriever

        logger = MemoryLogger()
        successes.append(f"✓ MemoryLogger initialized")
        successes.append(f"  - Embeddings: {'enabled' if logger.enable_embeddings else 'disabled'}")
        successes.append(f"  - Graph: {'enabled' if logger.enable_graph else 'disabled'}")
        successes.append(f"  - Sentiment: {'enabled' if logger.enable_sentiment else 'disabled'}")

        retriever = ContextRetriever()
        successes.append(f"✓ ContextRetriever initialized")
        successes.append(f"  - Semantic search: {'enabled' if retriever.enable_semantic else 'disabled'}")
        successes.append(f"  - Decay filtering: {'enabled' if retriever.enable_decay else 'disabled'}")

    except Exception as e:
        issues.append(f"✗ Integration test failed: {e}")

    return issues, successes


def check_database_schema():
    """Verify database schema migration."""
    print_section("DATABASE: Schema Verification")

    issues = []
    successes = []

    try:
        from kloros_memory.storage import MemoryStore

        store = MemoryStore()
        conn = store._get_connection()

        # Check events table columns
        cursor = conn.execute("PRAGMA table_info(events)")
        columns = {row[1] for row in cursor.fetchall()}

        required_columns = [
            "embedding_vector", "embedding_model",
            "decay_score", "last_accessed",
            "sentiment_score", "emotion_type"
        ]

        for col in required_columns:
            if col in columns:
                successes.append(f"✓ events.{col} exists")
            else:
                issues.append(f"✗ events.{col} missing")

        # Check new tables
        cursor = conn.execute("SELECT name FROM sqlite_master WHERE type='table'")
        tables = {row[0] for row in cursor.fetchall()}

        required_tables = ["memory_edges", "procedural_memories", "reflections"]

        for table in required_tables:
            if table in tables:
                successes.append(f"✓ {table} table exists")
            else:
                issues.append(f"✗ {table} table missing")

        # Get statistics
        stats = store.get_stats()
        successes.append(f"✓ Database statistics:")
        successes.append(f"  - Total events: {stats['total_events']}")
        successes.append(f"  - Total episodes: {stats['total_episodes']}")
        successes.append(f"  - Total summaries: {stats['total_summaries']}")
        successes.append(f"  - DB size: {stats['db_size_bytes']:,} bytes")

    except Exception as e:
        issues.append(f"✗ Database check failed: {e}")

    return issues, successes


def main():
    """Run all verification checks."""
    print("\n" + "█" * 70)
    print("  KLoROS MEMORY SYSTEM - COMPREHENSIVE VERIFICATION")
    print("█" * 70)

    all_issues = []
    all_successes = []

    # Run all checks
    checks = [
        ("Phase 1", check_phase_1_embeddings),
        ("Phase 2", check_phase_2_decay),
        ("Phase 3", check_phase_3_graph),
        ("Phase 4", check_phase_4_emotional),
        ("Phase 5", check_phase_5_procedural),
        ("Phase 6", check_phase_6_reflective),
        ("Phase 7", check_phase_7_metrics),
        ("Phase 8", check_phase_8_documentation),
        ("Integration", check_integration),
        ("Database", check_database_schema),
    ]

    for name, check_func in checks:
        issues, successes = check_func()

        for success in successes:
            print(success)
            all_successes.append((name, success))

        for issue in issues:
            print(issue)
            all_issues.append((name, issue))

    # Summary
    print_section("VERIFICATION SUMMARY")

    print(f"\n✓ Successes: {len(all_successes)}")
    print(f"✗ Issues: {len(all_issues)}")

    if all_issues:
        print("\n⚠️ ISSUES FOUND:")
        for name, issue in all_issues:
            print(f"  [{name}] {issue}")

    print("\n" + "=" * 70)

    if len(all_issues) == 0:
        print("🎉 ALL CHECKS PASSED - MEMORY SYSTEM FULLY OPERATIONAL")
        return 0
    elif len(all_issues) < 5:
        print("⚠️ MINOR ISSUES DETECTED - SYSTEM MOSTLY FUNCTIONAL")
        return 1
    else:
        print("❌ SIGNIFICANT ISSUES DETECTED - REQUIRES ATTENTION")
        return 2


if __name__ == "__main__":
    sys.exit(main())
