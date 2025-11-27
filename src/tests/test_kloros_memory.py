#!/usr/bin/env python3
"""
Comprehensive test suite for KLoROS episodic-semantic memory system.

Tests all major components including storage, logging, condensation,
retrieval, and integration functionality.
"""

import os
import sys
import tempfile
import time
import uuid
from pathlib import Path

# Add the source directory to the path
repo_root = Path(__file__).resolve().parent.parent
if str(repo_root) not in sys.path:
    sys.path.insert(0, str(repo_root))

# Test imports
try:
    from src.memory import (
        Event,
        Episode,
        EpisodeSummary,
        EventType,
        MemoryStore,
        MemoryLogger,
        EpisodeCondenser,
        ContextRetriever,
        ContextRetrievalRequest
    )
    from src.memory.housekeeping import MemoryHousekeeper
    print("✅ All memory modules imported successfully")
except ImportError as e:
    print(f"❌ Import error: {e}")
    sys.exit(1)


class MemorySystemTester:
    """Comprehensive tester for KLoROS memory system."""

    def __init__(self):
        """Initialize test environment."""
        # Create temporary database for testing
        self.temp_dir = tempfile.mkdtemp(prefix="kloros_memory_test_")
        self.db_path = os.path.join(self.temp_dir, "test_memory.db")

        # Initialize components
        self.store = MemoryStore(self.db_path)
        self.logger = MemoryLogger(self.store)
        self.condenser = EpisodeCondenser(self.store)
        self.retriever = ContextRetriever(self.store)
        self.housekeeper = MemoryHousekeeper(self.store, self.logger)

        # Test data
        self.test_conversation_id = str(uuid.uuid4())
        self.test_events = []
        self.test_episodes = []
        self.test_summaries = []

        print(f"✅ Test environment initialized (DB: {self.db_path})")

    def test_storage_layer(self) -> bool:
        """Test SQLite storage functionality."""
        print("\n🧪 Testing storage layer...")

        try:
            # Test event storage
            event = Event(
                timestamp=time.time(),
                event_type=EventType.USER_INPUT,
                content="Hello, can you help me?",
                metadata={"test": True},
                conversation_id=self.test_conversation_id,
                confidence=0.95,
                token_count=6
            )

            event_id = self.store.store_event(event)
            assert event_id is not None, "Event ID should not be None"
            print(f"  ✅ Event stored with ID: {event_id}")

            # Test event retrieval
            retrieved_events = self.store.get_events(limit=1)
            assert len(retrieved_events) == 1, "Should retrieve one event"
            assert retrieved_events[0].content == event.content, "Content should match"
            print("  ✅ Event retrieval successful")

            # Test episode storage
            episode = Episode(
                start_time=time.time() - 100,
                end_time=time.time(),
                conversation_id=self.test_conversation_id,
                event_count=1,
                token_count=6
            )

            episode_id = self.store.store_episode(episode)
            assert episode_id is not None, "Episode ID should not be None"
            print(f"  ✅ Episode stored with ID: {episode_id}")

            # Test summary storage
            summary = EpisodeSummary(
                episode_id=episode_id,
                summary_text="User asked for help",
                key_topics=["help", "assistance"],
                importance_score=0.7
            )

            summary_id = self.store.store_summary(summary)
            assert summary_id is not None, "Summary ID should not be None"
            print(f"  ✅ Summary stored with ID: {summary_id}")

            # Store references for later tests
            event.id = event_id
            episode.id = episode_id
            summary.id = summary_id

            self.test_events.append(event)
            self.test_episodes.append(episode)
            self.test_summaries.append(summary)

            return True

        except Exception as e:
            print(f"  ❌ Storage test failed: {e}")
            return False

    def test_logging_system(self) -> bool:
        """Test memory logging functionality."""
        print("\n🧪 Testing logging system...")

        try:
            # Start conversation
            conversation_id = self.logger.start_conversation()
            assert conversation_id is not None, "Conversation ID should not be None"
            print(f"  ✅ Conversation started: {conversation_id}")

            # Log various event types
            wake_event = self.logger.log_wake_detection(
                transcript="kloros",
                confidence=0.85,
                wake_phrase="kloros",
                audio_energy=450.0
            )
            print("  ✅ Wake detection logged")

            user_event = self.logger.log_user_input(
                transcript="What's the weather like?",
                confidence=0.92,
                audio_duration=2.5
            )
            print("  ✅ User input logged")

            llm_event = self.logger.log_llm_response(
                response="I don't have access to current weather data.",
                model="qwen2.5:14b-instruct-q4_0",
                response_tokens=12
            )
            print("  ✅ LLM response logged")

            tts_event = self.logger.log_tts_output(
                text="I don't have access to current weather data.",
                voice_model="piper"
            )
            print("  ✅ TTS output logged")

            # Test error logging
            error_event = self.logger.log_error(
                error_message="Test error message",
                error_type="TestError",
                component="memory_test"
            )
            print("  ✅ Error logged")

            # End conversation
            ended_id = self.logger.end_conversation()
            assert ended_id == conversation_id, "Ended conversation ID should match"
            print("  ✅ Conversation ended")

            # Verify events were logged
            conversation_events = self.logger.get_conversation_events(conversation_id)
            assert len(conversation_events) >= 6, f"Should have at least 6 events, got {len(conversation_events)}"
            print(f"  ✅ {len(conversation_events)} events logged in conversation")

            return True

        except Exception as e:
            print(f"  ❌ Logging test failed: {e}")
            return False

    def test_episode_condensation(self) -> bool:
        """Test episode grouping and condensation."""
        print("\n🧪 Testing episode condensation...")

        try:
            # Create test conversation with multiple events
            test_conv_id = str(uuid.uuid4())
            self.logger.start_conversation(test_conv_id)

            # Log a sequence of events
            events_data = [
                ("What is machine learning?", "Machine learning is a subset of AI..."),
                ("Can you explain neural networks?", "Neural networks are computing systems..."),
                ("How do I start learning ML?", "Start with Python and basic statistics...")
            ]

            for user_text, assistant_text in events_data:
                self.logger.log_user_input(user_text, confidence=0.9)
                time.sleep(0.1)  # Small delay between events
                self.logger.log_llm_response(assistant_text, model="qwen2.5:14b-instruct-q4_0")
                time.sleep(0.1)

            self.logger.end_conversation()
            print("  ✅ Test conversation created")

            # Group events into episodes
            episodes = self.condenser.group_events_into_episodes(test_conv_id)
            assert len(episodes) > 0, "Should create at least one episode"
            print(f"  ✅ Created {len(episodes)} episodes")

            # Test episode condensation (mock Ollama)
            for episode in episodes:
                # Mock condensation since we might not have Ollama running
                summary = EpisodeSummary(
                    episode_id=episode.id,
                    summary_text="Discussion about machine learning fundamentals and getting started",
                    key_topics=["machine learning", "neural networks", "education"],
                    importance_score=0.8
                )

                # Store the mock summary
                summary.id = self.store.store_summary(summary)
                self.store.mark_episode_condensed(episode.id)
                print(f"  ✅ Episode {episode.id} condensed (mocked)")

            return True

        except Exception as e:
            print(f"  ❌ Condensation test failed: {e}")
            return False

    def test_context_retrieval(self) -> bool:
        """Test context retrieval functionality."""
        print("\n🧪 Testing context retrieval...")

        try:
            # Create retrieval request
            request = ContextRetrievalRequest(
                query="machine learning",
                max_events=5,
                max_summaries=3,
                time_window_hours=24.0,
                min_importance=0.0
            )

            # Retrieve context
            result = self.retriever.retrieve_context(request)

            print(f"  ✅ Retrieved {len(result.events)} events and {len(result.summaries)} summaries")
            print(f"  ✅ Total tokens: {result.total_tokens}")
            print(f"  ✅ Retrieval time: {result.retrieval_time:.3f}s")

            # Test search functionality
            search_results = self.retriever.search_memory("learning", max_events=3, max_summaries=2)
            print(f"  ✅ Search returned {len(search_results.events)} events, {len(search_results.summaries)} summaries")

            # Test recent context
            recent_context = self.retriever.get_recent_context(hours=1.0)
            print(f"  ✅ Recent context: {len(recent_context.events)} events")

            return True

        except Exception as e:
            print(f"  ❌ Context retrieval test failed: {e}")
            return False

    def test_housekeeping(self) -> bool:
        """Test housekeeping and maintenance functionality."""
        print("\n🧪 Testing housekeeping...")

        try:
            # Get initial stats
            stats = self.housekeeper.get_comprehensive_stats()
            print(f"  ✅ Initial stats: {stats['total_events']} events, {stats['total_episodes']} episodes")

            # Test integrity validation
            integrity_issues = self.housekeeper.validate_data_integrity()
            print(f"  ✅ Found {len(integrity_issues)} integrity issues")

            # Test health report
            health_report = self.housekeeper.get_health_report()
            print(f"  ✅ Health score: {health_report['health_score']:.1f} ({health_report['status']})")

            # Test export summary
            summary = self.housekeeper.export_memory_summary(days=1)
            print(f"  ✅ Memory summary: {len(summary['conversations'])} conversations")

            return True

        except Exception as e:
            print(f"  ❌ Housekeeping test failed: {e}")
            return False

    def test_integration_scenario(self) -> bool:
        """Test complete integration scenario."""
        print("\n🧪 Testing integration scenario...")

        try:
            # Simulate a complete voice interaction session
            conversation_id = str(uuid.uuid4())

            # 1. Start conversation
            self.logger.start_conversation(conversation_id)

            # 2. Wake word detection
            self.logger.log_wake_detection("kloros", 0.87, "kloros")

            # 3. User asks a question
            user_question = "How does KLoROS work?"
            self.logger.log_user_input(user_question, confidence=0.93)

            # 4. Context retrieval (simulate)
            context_request = ContextRetrievalRequest(
                query=user_question,
                max_events=5,
                max_summaries=2,
                conversation_id=conversation_id
            )
            context = self.retriever.retrieve_context(context_request)

            self.logger.log_context_retrieval(
                query=user_question,
                retrieved_events=len(context.events),
                retrieved_summaries=len(context.summaries),
                total_tokens=context.total_tokens,
                retrieval_time=context.retrieval_time
            )

            # 5. LLM response
            response = "KLoROS is an AI voice assistant that uses speech recognition, language models, and text-to-speech."
            self.logger.log_llm_response(response, model="qwen2.5:14b-instruct-q4_0")

            # 6. TTS output
            self.logger.log_tts_output(response, voice_model="piper")

            # 7. End conversation
            self.logger.end_conversation()

            print("  ✅ Complete interaction logged")

            # 8. Auto-condense episode
            episodes = self.condenser.group_events_into_episodes(conversation_id)
            if episodes:
                episode = episodes[0]
                # Mock condensation
                summary = EpisodeSummary(
                    episode_id=episode.id,
                    summary_text="User asked about how KLoROS works, received explanation",
                    key_topics=["kloros", "functionality", "explanation"],
                    importance_score=0.6
                )
                summary.id = self.store.store_summary(summary)
                self.store.mark_episode_condensed(episode.id)
                print("  ✅ Episode condensed")

            # 9. Verify data integrity
            final_stats = self.store.get_stats()
            print(f"  ✅ Final stats: {final_stats['total_events']} events, {final_stats['total_episodes']} episodes")

            return True

        except Exception as e:
            print(f"  ❌ Integration test failed: {e}")
            return False

    def run_all_tests(self) -> bool:
        """Run all test suites."""
        print("🚀 Starting KLoROS Memory System Tests")
        print("=" * 50)

        tests = [
            ("Storage Layer", self.test_storage_layer),
            ("Logging System", self.test_logging_system),
            ("Episode Condensation", self.test_episode_condensation),
            ("Context Retrieval", self.test_context_retrieval),
            ("Housekeeping", self.test_housekeeping),
            ("Integration Scenario", self.test_integration_scenario)
        ]

        passed = 0
        failed = 0

        for test_name, test_func in tests:
            print(f"\n📋 Running {test_name} tests...")
            try:
                if test_func():
                    print(f"✅ {test_name} tests PASSED")
                    passed += 1
                else:
                    print(f"❌ {test_name} tests FAILED")
                    failed += 1
            except Exception as e:
                print(f"❌ {test_name} tests FAILED with exception: {e}")
                failed += 1

        print("\n" + "=" * 50)
        print(f"📊 Test Results: {passed} passed, {failed} failed")

        if failed == 0:
            print("🎉 All tests passed! KLoROS memory system is working correctly.")
        else:
            print("⚠️  Some tests failed. Check the output above for details.")

        return failed == 0

    def cleanup(self):
        """Clean up test environment."""
        try:
            self.logger.close()
            self.store.close()

            # Remove temporary files
            import shutil
            shutil.rmtree(self.temp_dir, ignore_errors=True)
            print(f"✅ Test environment cleaned up")
        except Exception as e:
            print(f"⚠️  Cleanup warning: {e}")


def main():
    """Main test function."""
    tester = MemorySystemTester()

    try:
        success = tester.run_all_tests()
        sys.exit(0 if success else 1)
    finally:
        tester.cleanup()


if __name__ == "__main__":
    main()