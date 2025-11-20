#!/usr/bin/env python3
"""Test memory context retrieval system - AUTOMATED"""
import sys
import time
sys.path.insert(0, '/home/kloros')

print("=" * 60)
print("KLoROS Context Retrieval Test")
print("=" * 60)
print()

# Test queries
test_queries = [
    "What did we discuss about D-REAM?",
    "Check recent errors",
    "What's my audio configuration?",
    "Show memory status",
    "What models am I using?"
]

try:
    from src.kloros_memory.integration import MemoryEnhancedKLoROS
    from src.kloros_memory.storage import MemoryStore
    from src.kloros_memory.retriever import ContextRetriever
    from src.kloros_memory.models import ContextRetrievalRequest

    print("✅ Memory modules loaded successfully")
    print()

    # Initialize components
    store = MemoryStore()
    retriever = ContextRetriever(store)

    # Get database stats
    stats = store.get_stats()
    print(f"📊 Memory Database Stats:")
    print(f"   - Total events: {stats.get('total_events', 0)}")
    print(f"   - Total episodes: {stats.get('total_episodes', 0)}")
    print(f"   - Episode summaries: {stats.get('episode_summaries', 0)}")
    print()

    # Test each query
    print("🔍 Testing Context Retrieval:")
    print()

    for i, query in enumerate(test_queries, 1):
        print(f"Test {i}: {query}")

        request = ContextRetrievalRequest(
            query=query,
            max_events=10,
            max_summaries=3,
            time_window_hours=24.0
        )

        start_time = time.time()
        result = retriever.retrieve_context(request)
        elapsed = (time.time() - start_time) * 1000

        print(f"   ⏱️  Retrieval time: {elapsed:.1f}ms")
        print(f"   📄 Events retrieved: {len(result.events)}")
        print(f"   📋 Summaries retrieved: {len(result.summaries)}")
        print(f"   💬 Total tokens: {result.total_tokens}")

        if result.events:
            print(f"   ✅ Context available")
        else:
            print(f"   ❌ No events retrieved (likely NULL conversation_id issue)")
        print()

    # Check for NULL conversation_ids
    print("🔍 Checking conversation_id integrity:")
    conn = store._get_connection()
    cursor = conn.execute("SELECT COUNT(*) FROM events WHERE conversation_id IS NULL")
    null_count = cursor.fetchone()[0]
    cursor = conn.execute("SELECT COUNT(*) FROM events")
    total_count = cursor.fetchone()[0]

    if null_count > 0:
        pct = (null_count / total_count * 100)
        print(f"   ❌ ISSUE: {null_count}/{total_count} events ({pct:.1f}%) have NULL conversation_id")
        print(f"   This explains why context retrieval returns empty results!")
    else:
        print(f"   ✅ All events have conversation_id")
    print()

    print("=" * 60)
    print("Test Complete")
    print("=" * 60)

except ImportError as e:
    print(f"❌ Import error: {e}")
    print()
    print("Make sure you're running in the KLoROS venv:")
    print("  source /home/kloros/venv/bin/activate")
except Exception as e:
    print(f"❌ Test failed: {e}")
    import traceback
    traceback.print_exc()
