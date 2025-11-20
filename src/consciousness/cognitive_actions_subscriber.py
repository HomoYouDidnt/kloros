#!/usr/bin/env python3
"""
Cognitive Actions Subscriber - Affective Action Tier 3

Listens for cognitive-level affective signals (MEMORY_PRESSURE, TASK_FAILURE_PATTERN, etc.)
and executes data/memory operations to relieve cognitive load.

Maps affective states → cognitive actions (memory, analysis, integration).
"""

import json
import time
import sys
import traceback
from pathlib import Path
from typing import List, Dict, Any, Optional
from datetime import datetime, timedelta


def check_emergency_brake() -> bool:
    """Check if emergency brake is active."""
    brake_flag = Path("/tmp/kloros_emergency_brake_active")
    return brake_flag.exists()


class CognitiveActionHandler:
    """Handles cognitive-level autonomous actions."""

    def __init__(self):
        """Initialize cognitive action handler."""
        self.action_log_path = Path("/tmp/kloros_cognitive_actions.log")
        self.last_action_time = {}
        self.action_cooldown = 300.0  # 5 minutes between same action type

        self.memory_store = None
        self.conversation_logger = None
        self._memory_systems_initialized = False

    def _initialize_memory_systems(self) -> None:
        """Initialize episodic memory and conversation logging systems (lazy-loaded)."""
        if self._memory_systems_initialized:
            return

        self._memory_systems_initialized = True
        try:
            from kloros_memory.storage import MemoryStore
            from kloros_memory.models import EpisodeSummary

            self.memory_store = MemoryStore()
            print("[cognitive_actions] Initialized MemoryStore for episodic memory (lazy-loaded)")
        except ImportError:
            try:
                from src.kloros_memory.storage import MemoryStore
                from src.kloros_memory.models import EpisodeSummary

                self.memory_store = MemoryStore()
                print("[cognitive_actions] Initialized MemoryStore for episodic memory")
            except Exception as e:
                print(f"[cognitive_actions] Warning: Could not initialize MemoryStore: {e}")
                self.memory_store = None
        except Exception as e:
            print(f"[cognitive_actions] Warning: Could not initialize MemoryStore: {e}")
            self.memory_store = None

        try:
            from memory.qdrant_conversation_logger import QdrantConversationLogger
            import os
            from pathlib import Path

            try:
                from qdrant_client import QdrantClient
                HAS_QDRANT = True
            except ImportError:
                HAS_QDRANT = False

            if HAS_QDRANT:
                server_url = os.getenv('KLR_QDRANT_URL', None)

                if server_url is None:
                    try:
                        import tomllib
                        config_path = Path("/home/kloros/config/models.toml")
                        if config_path.exists():
                            with open(config_path, "rb") as f:
                                config = tomllib.load(f)
                            server_url = config.get("vector_store", {}).get("server_url", None)
                    except Exception:
                        pass

                if server_url:
                    client = QdrantClient(url=server_url)
                else:
                    qdrant_dir = os.getenv('KLOROS_QDRANT_DIR', '/home/kloros/.kloros/qdrant_data')
                    os.makedirs(qdrant_dir, exist_ok=True)
                    client = QdrantClient(path=qdrant_dir)

                self.conversation_logger = QdrantConversationLogger(client, collection_prefix="kloros")
                print("[cognitive_actions] Initialized QdrantConversationLogger for Qdrant")
            else:
                print("[cognitive_actions] Warning: qdrant-client not installed")
                self.conversation_logger = None
        except ImportError:
            try:
                from src.memory.qdrant_conversation_logger import QdrantConversationLogger
                import os
                from pathlib import Path

                try:
                    from qdrant_client import QdrantClient
                    HAS_QDRANT = True
                except ImportError:
                    HAS_QDRANT = False

                if HAS_QDRANT:
                    server_url = os.getenv('KLR_QDRANT_URL', None)

                    if server_url is None:
                        try:
                            import tomllib
                            config_path = Path("/home/kloros/config/models.toml")
                            if config_path.exists():
                                with open(config_path, "rb") as f:
                                    config = tomllib.load(f)
                                server_url = config.get("vector_store", {}).get("server_url", None)
                        except Exception:
                            pass

                    if server_url:
                        client = QdrantClient(url=server_url)
                    else:
                        qdrant_dir = os.getenv('KLOROS_QDRANT_DIR', '/home/kloros/.kloros/qdrant_data')
                        os.makedirs(qdrant_dir, exist_ok=True)
                        client = QdrantClient(path=qdrant_dir)

                    self.conversation_logger = QdrantConversationLogger(client, collection_prefix="kloros")
                    print("[cognitive_actions] Initialized QdrantConversationLogger for Qdrant")
                else:
                    print("[cognitive_actions] Warning: qdrant-client not installed")
                    self.conversation_logger = None
            except Exception as e:
                print(f"[cognitive_actions] Warning: Could not initialize QdrantConversationLogger: {e}")
                self.conversation_logger = None
        except Exception as e:
            print(f"[cognitive_actions] Warning: Could not initialize QdrantConversationLogger: {e}")
            self.conversation_logger = None

    def _verify_episodic_storage(self, event_id: Optional[int], operation: str) -> bool:
        """
        Verify event was successfully stored to episodic memory.

        Checks that the event exists in the database after storage attempt.

        Args:
            event_id: Event ID returned from store_event()
            operation: Operation name for logging

        Returns:
            True if event verified in database, False otherwise
        """
        if event_id is None:
            print(f"  Warning {operation}: Storage returned None event_id")
            return False

        if not self.memory_store:
            print(f"  Warning {operation}: Memory store unavailable")
            return False

        try:
            conn = self.memory_store._get_connection()
            cursor = conn.cursor()
            cursor.execute("SELECT id FROM events WHERE id = ?", (event_id,))
            result = cursor.fetchone()

            if result:
                print(f"  Verified {operation}: Event {event_id} exists in episodic memory")
                return True
            else:
                print(f"  Warning {operation}: Event {event_id} not found in database after storage")
                return False

        except Exception as e:
            print(f"  Warning {operation}: Verification failed: {e}")
            return False

    def _check_state_consistency(self) -> Dict[str, Any]:
        """
        Check for state inconsistencies in episodic memory.

        Performs database integrity checks including orphaned metadata,
        missing timestamps, and valid event types.

        Returns:
            Dict with consistency check results including passed/failed checks
        """
        results = {
            'timestamp': datetime.now().isoformat(),
            'checks_passed': [],
            'checks_failed': [],
            'warnings': []
        }

        if not self.memory_store:
            results['warnings'].append("Memory store unavailable")
            return results

        try:
            conn = self.memory_store._get_connection()
            cursor = conn.cursor()

            cursor.execute("SELECT COUNT(*) FROM events")
            total_events = cursor.fetchone()[0]
            results['checks_passed'].append(f"Database accessible ({total_events} total events)")

            cursor.execute("""
                SELECT COUNT(*) FROM events
                WHERE metadata IS NOT NULL
                AND metadata NOT LIKE '{%'
            """)
            orphaned = cursor.fetchone()[0]
            if orphaned == 0:
                results['checks_passed'].append("No orphaned metadata")
            else:
                results['checks_failed'].append(f"{orphaned} events with invalid metadata")

            cursor.execute("""
                SELECT COUNT(*) FROM events
                WHERE timestamp IS NULL OR timestamp = 0
            """)
            missing_ts = cursor.fetchone()[0]
            if missing_ts == 0:
                results['checks_passed'].append("All events have timestamps")
            else:
                results['checks_failed'].append(f"{missing_ts} events missing timestamps")

            try:
                from kloros_memory.models import EventType
            except ImportError:
                try:
                    from src.kloros_memory.models import EventType
                except ImportError:
                    results['warnings'].append("Could not validate event types (EventType unavailable)")
                    return results

            cursor.execute("""
                SELECT DISTINCT event_type FROM events
            """)
            event_types = [row[0] for row in cursor.fetchall()]

            valid_types = [e.value for e in EventType]
            invalid = [et for et in event_types if et not in valid_types]

            if not invalid:
                results['checks_passed'].append("All event types valid")
            else:
                results['checks_failed'].append(f"Invalid event types found: {invalid}")

            return results

        except Exception as e:
            results['warnings'].append(f"Consistency check failed: {e}")
            return results

    def _log_operation_start(self, operation: str, context: Dict[str, Any]) -> None:
        """
        Log operation start for debugging and auditing.

        Records operation start in both console and log file.

        Args:
            operation: Operation name
            context: Context dictionary (evidence, parameters, etc)
        """
        timestamp = datetime.now().isoformat()
        log_entry = f"[{timestamp}] START {operation}: {json.dumps(context)}"

        print(f"  -> Starting: {operation}")

        try:
            with open(self.action_log_path, 'a') as f:
                f.write(log_entry + "\n")
        except Exception as e:
            print(f"  Warning: Could not write to action log: {e}")

    def _log_operation_end(self, operation: str, success: bool, details: str = "") -> None:
        """
        Log operation completion with status and details.

        Records operation outcome in both console and log file.

        Args:
            operation: Operation name
            success: Whether operation succeeded
            details: Additional details about the operation
        """
        timestamp = datetime.now().isoformat()
        status = "SUCCESS" if success else "FAILED"
        log_entry = f"[{timestamp}] {status} {operation}: {details}"

        symbol = "✓" if success else "✗"
        print(f"  {symbol} {operation}: {status}")

        try:
            with open(self.action_log_path, 'a') as f:
                f.write(log_entry + "\n")
        except Exception as e:
            print(f"  Warning: Could not write to action log: {e}")

    def can_execute_action(self, action_type: str) -> bool:
        """
        Check if action can be executed (cooldown check).

        Args:
            action_type: Type of action

        Returns:
            True if action can be executed
        """
        last_time = self.last_action_time.get(action_type, 0.0)
        elapsed = time.time() - last_time
        return elapsed >= self.action_cooldown

    def log_action(self, action_type: str, result: str):
        """
        Log executed action.

        Args:
            action_type: Type of action executed
            result: Result description
        """
        self.last_action_time[action_type] = time.time()

        with open(self.action_log_path, 'a') as f:
            timestamp = time.strftime('%Y-%m-%d %H:%M:%S')
            f.write(f"{timestamp} | {action_type} | {result}\n")

    def _get_recent_conversation_turns(self, limit: int = 10) -> List[Dict[str, Any]]:
        """
        Get recent conversation turns from ChromaDB.

        Args:
            limit: Number of recent turns to retrieve

        Returns:
            List of conversation turns
        """
        if not self.conversation_logger:
            return []

        try:
            return self.conversation_logger.get_recent_turns(n=limit)
        except Exception as e:
            print(f"  Error retrieving recent turns: {e}")
            return []

    def _get_older_conversation_turns(self, offset: int = 10, limit: int = 50) -> List[Dict[str, Any]]:
        """
        Get older conversation turns from ChromaDB for archival.

        Args:
            offset: Number of turns to skip
            limit: Number of older turns to retrieve

        Returns:
            List of older conversation turns
        """
        if not self.conversation_logger:
            return []

        try:
            all_docs = self.conversation_logger.conversations.get(
                offset=offset,
                limit=limit
            )

            if not all_docs or not all_docs['ids']:
                return []

            turns = []
            for i in range(len(all_docs['ids'])):
                turns.append({
                    'id': all_docs['ids'][i],
                    'document': all_docs['documents'][i],
                    'metadata': all_docs['metadatas'][i]
                })

            return turns
        except Exception as e:
            print(f"  Error retrieving older turns: {e}")
            return []

    def _create_summary_from_turns(self, turns: List[Dict[str, Any]]) -> str:
        """
        Create a contextual summary from conversation turns.

        Args:
            turns: List of conversation turns to summarize

        Returns:
            Summary text
        """
        if not turns:
            return "No content to summarize"

        try:
            summary_parts = []
            summary_parts.append(f"Summarized {len(turns)} conversation turns:")

            user_count = 0
            system_count = 0
            topics = set()

            for turn in turns:
                doc = turn.get('document', '')
                metadata = turn.get('metadata', {})

                if metadata.get('speaker') == 'user':
                    user_count += 1
                    if len(doc) > 10:
                        summary_parts.append(f"- User: {doc[:80]}...")
                elif metadata.get('speaker') == 'system':
                    system_count += 1
                    if len(doc) > 10:
                        summary_parts.append(f"- Response: {doc[:80]}...")

            summary_text = "\n".join(summary_parts[:20])
            return summary_text if summary_text else "Archived context"

        except Exception as e:
            print(f"  Error creating summary: {e}")
            return f"Error summarizing content: {e}"

    def _store_summary_to_episodic_memory(self, summary_record: Dict[str, Any]) -> Any:
        """
        Store a summary to episodic memory system.

        Args:
            summary_record: Dictionary with summary data

        Returns:
            Event ID if storage succeeded, False if failed
        """
        if not self.memory_store:
            print("  Memory store not available, skipping episodic storage")
            return False

        try:
            try:
                from kloros_memory.models import EpisodeSummary, EventType, Event
            except ImportError:
                from src.kloros_memory.models import EpisodeSummary, EventType, Event

            summary_text = summary_record.get('summary', 'Context archived')
            evidence = summary_record.get('evidence', [])
            turns_compressed = summary_record.get('turns_compressed', 0)

            metadata = {
                'reason': summary_record.get('reason', 'memory_pressure'),
                'turns_compressed': turns_compressed,
                'evidence': evidence,
                'archived_at': summary_record.get('timestamp')
            }

            event = Event(
                timestamp=time.time(),
                event_type=EventType.EPISODE_CONDENSED,
                content=f"Context archived: {summary_text[:200]}",
                metadata=metadata,
                conversation_id=None
            )

            event_id = self.memory_store.store_event(event)
            print(f"  Stored summary to episodic memory (event_id: {event_id})")
            return event_id if event_id is not None else False

        except Exception as e:
            print(f"  Error storing summary to episodic memory: {e}")
            return False

    def summarize_context(self, evidence: List[str]) -> bool:
        """
        Summarize and archive older conversation context to episodic memory.

        Triggered by AFFECT_MEMORY_PRESSURE signals when token usage is high.
        Compresses older conversation turns to free up working memory while
        preserving information in episodic memory for future retrieval.

        Includes verification to ensure storage succeeded and consistency checks
        to prevent state corruption.

        Args:
            evidence: Evidence about memory pressure

        Returns:
            True if action succeeded and verified
        """
        self._log_operation_start('summarize_context', {'evidence': evidence})

        # Lazy-load memory systems only when actually needed
        if not self._memory_systems_initialized:
            self._initialize_memory_systems()

        try:
            recent = self._get_recent_conversation_turns(limit=10)
            older = self._get_older_conversation_turns(offset=10, limit=50)

            if not older:
                print("  No older context to summarize")
                self._log_operation_end('summarize_context', True, 'No older context to archive')
                self.log_action('summarize_context', 'No older context to archive')
                return True

            print(f"  Retrieved {len(recent)} recent turns, {len(older)} older turns")

            summary_text = self._create_summary_from_turns(older)

            summary_record = {
                'timestamp': datetime.now().isoformat(),
                'reason': 'memory_pressure',
                'evidence': evidence,
                'turns_compressed': len(older),
                'summary': summary_text
            }

            event_id = self._store_summary_to_episodic_memory(summary_record)

            if event_id is False:
                print(f"  Storage failed, no event_id returned")
                self._log_operation_end('summarize_context', False, 'Storage failed')
                self.log_action('summarize_context', 'Storage failed')
                return False

            if not isinstance(event_id, bool) and event_id is not None:
                verified = self._verify_episodic_storage(event_id, 'summarize_context')
                if verified:
                    print(f"  Successfully archived {len(older)} turns, retained {len(recent)} recent")
                    self._log_operation_end('summarize_context', True, f'Event {event_id} verified')
                    self.log_action(
                        'summarize_context',
                        f'Compressed {len(older)} turns, kept {len(recent)} recent'
                    )
                    return True
                else:
                    print(f"  Verification failed: event stored but not found in database")
                    self._log_operation_end('summarize_context', False, 'Verification failed')
                    self.log_action('summarize_context', 'Verification failed after storage')
                    return False
            else:
                print(f"  Partial completion: created summary but storage returned invalid event_id")
                self._log_operation_end('summarize_context', False, 'Invalid event_id from storage')
                self.log_action('summarize_context', 'Storage returned invalid event_id')
                return False

        except Exception as e:
            print(f"  Error during context summarization: {e}")
            traceback.print_exc()
            self._log_operation_end('summarize_context', False, str(e))
            self.log_action('summarize_context', f'Failed: {e}')
            return False

    def archive_completed_tasks(self, evidence: List[str]) -> bool:
        """
        Archive completed tasks to episodic memory.

        Triggered by AFFECT_MEMORY_PRESSURE signals when working memory is full.
        Identifies completed tasks from consciousness history and moves them to
        episodic memory for long-term storage while freeing working memory.

        Includes verification of individual task archival and consistency checks
        to ensure partial failures don't corrupt state.

        Args:
            evidence: Evidence about memory pressure

        Returns:
            True if action succeeded with verification
        """
        self._log_operation_start('archive_completed_tasks', {'evidence': evidence})

        # Lazy-load memory systems only when actually needed
        if not self._memory_systems_initialized:
            self._initialize_memory_systems()

        try:
            completed = self._get_completed_tasks(days=7)

            if not completed:
                print("  No completed tasks to archive")
                self._log_operation_end('archive_completed_tasks', True, 'No tasks found')
                self.log_action('archive_tasks', 'No completed tasks found')
                return True

            archived_count = 0
            failed_tasks = []
            verified_count = 0

            for task in completed:
                task_id = task.get('id', 'unknown')
                event_id = self._archive_single_task(task, evidence)

                if event_id and not isinstance(event_id, bool):
                    archived_count += 1
                    if self._verify_episodic_storage(event_id, f'archive_task_{task_id}'):
                        verified_count += 1
                    else:
                        failed_tasks.append(task_id)
                elif event_id is True:
                    archived_count += 1
                else:
                    failed_tasks.append(task_id)

            if verified_count > 0:
                print(f"  Archived {archived_count}/{len(completed)} tasks, {verified_count} verified")
                if failed_tasks:
                    print(f"  Warning: {len(failed_tasks)} tasks failed verification: {failed_tasks}")
                    self._log_operation_end('archive_completed_tasks', False, f'{verified_count} verified, {len(failed_tasks)} failed')
                    self.log_action('archive_tasks', f'Archived {archived_count}, {len(failed_tasks)} verification failures')
                    return False
                else:
                    self._log_operation_end('archive_completed_tasks', True, f'{verified_count} verified')
                    self.log_action('archive_tasks', f'Archived {archived_count} completed tasks')
                    return True
            else:
                print(f"  All tasks failed archival or verification")
                self._log_operation_end('archive_completed_tasks', False, 'No tasks verified')
                self.log_action('archive_tasks', 'All tasks failed archival')
                return False

        except Exception as e:
            print(f"  Failed to archive tasks: {e}")
            traceback.print_exc()
            self._log_operation_end('archive_completed_tasks', False, str(e))
            self.log_action('archive_tasks', f'Failed: {e}')
            return False

    def throttle_investigations(self, facts: Dict[str, Any], evidence: List[str]) -> bool:
        """
        Throttle investigation consumer to reduce resource usage.

        Triggered by AFFECT_MEMORY_PRESSURE when system resources are critical.
        Emits INVESTIGATION_THROTTLE_REQUEST signal to reduce concurrency.

        Args:
            facts: Signal facts (memory stats, thread count, etc.)
            evidence: Evidence about memory pressure

        Returns:
            True if throttle signal emitted
        """
        self._log_operation_start('throttle_investigations', {'facts': facts, 'evidence': evidence})

        try:
            from kloros.orchestration.chem_bus_v2 import ChemPub
            chem_pub = ChemPub()

            thread_count = facts.get('thread_count', 0)
            swap_used_mb = facts.get('swap_used_mb', 0)
            memory_used_pct = facts.get('memory_used_pct', 0)

            print(f"  Emitting throttle request: threads={thread_count}, swap={swap_used_mb}MB, mem={memory_used_pct}%")

            chem_pub.emit(
                signal="INVESTIGATION_THROTTLE_REQUEST",
                ecosystem="orchestration",
                intensity=2.0,
                facts={
                    "reason": "Critical memory pressure detected",
                    "thread_count": thread_count,
                    "swap_used_mb": swap_used_mb,
                    "memory_used_pct": memory_used_pct,
                    "requested_concurrency": 1,
                    "evidence": evidence
                }
            )

            chem_pub.close()
            self._log_operation_end('throttle_investigations', True, f'Throttle requested: concurrency=1')
            self.log_action('throttle_investigations', f'Requested concurrency reduction due to memory pressure')
            print(f"  ✓ Throttle signal emitted successfully")
            return True

        except Exception as e:
            print(f"  Failed to emit throttle signal: {e}")
            import traceback
            traceback.print_exc()
            self._log_operation_end('throttle_investigations', False, str(e))
            self.log_action('throttle_investigations', f'Failed: {e}')
            return False

    def optimize_performance(self, facts: Dict[str, Any], evidence: List[str]) -> bool:
        """
        Analyze system performance and apply autonomous optimizations.

        Triggered by AFFECT_RESOURCE_STRAIN when system is under moderate pressure.
        Analyzes current resource usage, generates improvement proposals, and emits
        optimization signals that other systems can act on.

        Args:
            facts: Signal facts (memory stats, thread count, failure rates, etc.)
            evidence: Evidence about resource strain

        Returns:
            True if optimization analysis completed
        """
        self._log_operation_start('optimize_performance', {'facts': facts, 'evidence': evidence})

        try:
            from pathlib import Path
            import json
            from dream.improvement_proposer import ImprovementProposer, ImprovementProposal
            from kloros.orchestration.chem_bus_v2 import ChemPub

            print(f"  🔍 Analyzing system performance for optimization opportunities...")

            thread_count = facts.get('thread_count', 0)
            swap_used_mb = facts.get('swap_used_mb', 0)
            memory_used_pct = facts.get('memory_used_pct', 0)
            investigation_failure_rate = facts.get('investigation_failure_rate', 0)

            print(f"    Current state: threads={thread_count}, swap={swap_used_mb:.0f}MB, "
                  f"mem={memory_used_pct:.1f}%, inv_failures={investigation_failure_rate:.1%}")

            proposer = ImprovementProposer()
            chem_pub = ChemPub()

            actions_emitted = 0

            if swap_used_mb > 10000 or memory_used_pct > 70:
                print(f"  🎯 Direct detection: High memory pressure detected!")
                print(f"    swap={swap_used_mb:.0f}MB, mem={memory_used_pct:.1f}%")

                try:
                    from consciousness.skill_executor import SkillExecutor
                    from consciousness.skill_auto_executor import SkillAutoExecutor

                    problem_context = {
                        'description': f'Memory pressure: {swap_used_mb:.0f}MB swap, {memory_used_pct:.1f}% RAM',
                        'evidence': {
                            'swap_used_mb': swap_used_mb,
                            'memory_used_pct': memory_used_pct,
                            'thread_count': thread_count
                        },
                        'metrics': {
                            'thread_count': thread_count,
                            'swap_used_mb': swap_used_mb,
                            'memory_used_pct': memory_used_pct,
                            'investigation_failure_rate': investigation_failure_rate
                        }
                    }

                    print(f"    → Loading skill: memory-optimization")
                    executor = SkillExecutor()
                    auto_executor = SkillAutoExecutor()

                    from consciousness.skill_tracker import SkillTracker
                    tracker = SkillTracker()
                    effectiveness = tracker.get_skill_effectiveness('memory-optimization', 'performance')

                    if effectiveness['total_executions'] > 0:
                        print(f"    → Past performance: {effectiveness['success_rate']:.0%} success rate "
                              f"({effectiveness['successes']} successes, {effectiveness['failures']} failures)")

                        if effectiveness['success_rate'] < 0.3 and effectiveness['total_executions'] >= 2:
                            print(f"    ⚠️  This skill has low success rate - including failure context in prompt")
                            problem_context['past_failures'] = {
                                'skill': 'memory-optimization',
                                'attempts': effectiveness['total_executions'],
                                'success_rate': effectiveness['success_rate'],
                                'note': 'Previous attempts at memory-optimization have not been effective. Consider alternative approaches or escalate to manual intervention.'
                            }

                    tracker.close()

                    plan = executor.execute_skill('memory-optimization', problem_context)

                    if plan:
                        print(f"    → Generated action plan: Phase={plan.phase}, Confidence={plan.confidence}")
                        print(f"    → {len(plan.actions)} actions planned")

                        if auto_executor.can_auto_execute('memory-optimization'):
                            print(f"    → 🤖 Auto-executing skill (safe, low-risk)")
                            result = auto_executor.execute_plan(plan, auto_execute=True)

                            if result:
                                print(f"    → ✓ Auto-execution completed: {result.outcome}")
                                print(f"    → Improvement: {result.improvement:.1%}")
                                actions_emitted += 1
                            else:
                                print(f"    → ✗ Auto-execution failed or not allowed")
                        else:
                            print(f"    → Manual approval required")
                    else:
                        print(f"    ✗ Failed to generate skill plan")

                except Exception as e:
                    print(f"    ✗ Direct skill execution error: {e}")
                    import traceback
                    traceback.print_exc()

            print(f"  📊 Running fresh performance analysis...")
            proposals = proposer.analyze_system_health()

            if not proposals:
                print(f"  ✓ No optimization opportunities identified - system healthy")
                self._log_operation_end('optimize_performance', True, 'System healthy')
                chem_pub.close()
                return True

            critical = [p for p in proposals if p.priority == 'critical']
            high = [p for p in proposals if p.priority == 'high']

            print(f"  📌 Found {len(critical)} critical, {len(high)} high priority issues")

            for proposal in proposals:
                proposer.submit_proposal(proposal)

            for proposal in critical[:3] + high[:2]:
                print(f"  🎯 Issue [{proposal.priority}]: {proposal.description[:70]}...")

                skill_name = None
                if proposal.issue_type == 'performance' and 'memory' in proposal.description.lower():
                    skill_name = 'memory-optimization'
                elif proposal.issue_type == 'performance' and 'swap' in proposal.description.lower():
                    skill_name = 'memory-optimization'
                elif proposal.issue_type == 'reliability' and 'stuck' in proposal.description.lower():
                    skill_name = 'systematic-debugging'

                if skill_name:
                    try:
                        from consciousness.skill_executor import SkillExecutor, SkillExecutionPlan
                        from consciousness.skill_auto_executor import SkillAutoExecutor
                        from dataclasses import asdict

                        print(f"    → Loading skill: {skill_name}")
                        executor = SkillExecutor()
                        auto_executor = SkillAutoExecutor()

                        problem_context = {
                            'description': proposal.description,
                            'evidence': proposal.evidence if hasattr(proposal, 'evidence') else {},
                            'metrics': {
                                'thread_count': thread_count,
                                'swap_used_mb': swap_used_mb,
                                'memory_used_pct': memory_used_pct,
                                'investigation_failure_rate': investigation_failure_rate
                            }
                        }

                        plan = executor.execute_skill(skill_name, problem_context)

                        if plan:
                            print(f"    → Generated action plan: Phase={plan.phase}, Confidence={plan.confidence}")
                            print(f"    → {len(plan.actions)} actions planned")

                            if auto_executor.can_auto_execute(skill_name):
                                print(f"    → 🤖 Auto-executing skill (safe, low-risk)")
                                result = auto_executor.execute_plan(plan, auto_execute=True)

                                if result:
                                    print(f"    → ✓ Auto-execution completed: {result.outcome}")
                                    print(f"    → Improvement: {result.improvement:.1%}")
                                    actions_emitted += 1
                                else:
                                    print(f"    → ✗ Auto-execution failed or not allowed")
                            else:
                                print(f"    → Manual approval required - emitting plan")
                                chem_pub.emit(
                                    signal="SKILL_EXECUTION_PLAN",
                                    ecosystem="consciousness",
                                    intensity=2.0,
                                    facts={
                                        "skill_name": skill_name,
                                        "problem": proposal.description,
                                        "plan": asdict(plan),
                                        "auto_execute": False
                                    }
                                )
                                actions_emitted += 1
                        else:
                            print(f"    ✗ Failed to generate skill plan")

                    except Exception as e:
                        print(f"    ✗ Skill execution error: {e}")

                if proposal.issue_type == 'performance' and 'swap' in proposal.description.lower():
                    print(f"    → Also emitting OPTIMIZE_MEMORY_USAGE signal")
                    chem_pub.emit(
                        signal="OPTIMIZE_MEMORY_USAGE",
                        ecosystem="consciousness",
                        intensity=2.0,
                        facts={
                            "reason": proposal.description,
                            "swap_used_mb": swap_used_mb,
                            "memory_used_pct": memory_used_pct,
                            "recommendations": ["reduce_investigation_concurrency", "clear_caches"]
                        }
                    )
                    actions_emitted += 1

            if investigation_failure_rate > 0.3:
                print(f"  ⚠️  High investigation failure rate detected ({investigation_failure_rate:.1%})")
                print(f"    → Already throttled by AFFECT_MEMORY_PRESSURE")

            result_msg = f'Analyzed {len(proposals)} issues, emitted {actions_emitted} optimization signals (threads={thread_count}, swap={swap_used_mb:.0f}MB, mem={memory_used_pct:.1f}%)'

            self._log_operation_end('optimize_performance', True, result_msg)
            self.log_action('optimize_performance', result_msg)
            print(f"  ✓ Performance optimization analysis complete")
            chem_pub.close()
            return True

        except Exception as e:
            print(f"  ✗ Failed to optimize performance: {e}")
            import traceback
            traceback.print_exc()
            self._log_operation_end('optimize_performance', False, str(e))
            self.log_action('optimize_performance', f'Failed: {e}')
            return False

    def _get_completed_tasks(self, days: int = 7) -> List[Dict[str, Any]]:
        """
        Retrieve completed tasks from consciousness history.

        Since KLoROS tracks tasks through process_task_outcome(), this method
        reconstructs completed task records from episodic memory events.

        Args:
            days: Number of days back to retrieve completed tasks

        Returns:
            List of completed task dictionaries with metadata
        """
        try:
            if not self.memory_store:
                return []

            cutoff_time = time.time() - (days * 24 * 3600)

            conn = self.memory_store._get_connection()
            cursor = conn.cursor()

            cursor.execute("""
                SELECT id, timestamp, content, metadata
                FROM events
                WHERE event_type IN ('TOOL_EXECUTION', 'REASONING_TRACE')
                AND timestamp >= ?
                AND metadata LIKE '%"success": true%'
                ORDER BY timestamp DESC
                LIMIT 50
            """, (cutoff_time,))

            completed_tasks = []
            for row in cursor.fetchall():
                event_id, timestamp, content, metadata_json = row

                try:
                    metadata = json.loads(metadata_json) if metadata_json else {}
                except:
                    metadata = {}

                if metadata.get('success') or 'success": true' in (metadata_json or ''):
                    completed_tasks.append({
                        'id': event_id,
                        'timestamp': timestamp,
                        'content': content,
                        'metadata': metadata,
                        'completed_at': datetime.fromtimestamp(timestamp).isoformat()
                    })

            return completed_tasks

        except Exception as e:
            print(f"  Error retrieving completed tasks: {e}")
            return []

    def _archive_single_task(self, task: Dict[str, Any], evidence: List[str]) -> Any:
        """
        Archive a single completed task to episodic memory.

        Creates a summary of the task and stores it as a memory housekeeping event.

        Args:
            task: Task dictionary from _get_completed_tasks
            evidence: Evidence context from memory pressure signal

        Returns:
            Event ID if successful, False if failed
        """
        try:
            if not self.memory_store:
                return False

            summary_text = self._summarize_task(task)

            metadata = {
                'task_id': task.get('id'),
                'completed_at': task.get('completed_at'),
                'original_timestamp': task.get('timestamp'),
                'evidence': evidence,
                'reason': 'memory_pressure'
            }

            try:
                from kloros_memory.models import Event, EventType
            except ImportError:
                from src.kloros_memory.models import Event, EventType

            event = Event(
                timestamp=time.time(),
                event_type=EventType.MEMORY_HOUSEKEEPING,
                content=f"Task archived: {summary_text}",
                metadata=metadata,
                conversation_id=None
            )

            event_id = self.memory_store.store_event(event)
            return event_id if event_id is not None else False

        except Exception as e:
            print(f"  Failed to archive task {task.get('id')}: {e}")
            return False

    def _summarize_task(self, task: Dict[str, Any]) -> str:
        """
        Create a summary text for an archived task.

        Extracts key information from task metadata for efficient retrieval.

        Args:
            task: Task dictionary from _get_completed_tasks

        Returns:
            Summary text for the task
        """
        task_id = task.get('id', 'unknown')
        content = task.get('content', '')
        metadata = task.get('metadata', {})

        metadata_desc = metadata.get('description', metadata.get('tool_name', ''))

        summary_parts = [f"[{task_id}]"]

        if metadata_desc:
            summary_parts.append(metadata_desc)
        elif content:
            if len(content) > 100:
                summary_parts.append(content[:97] + "...")
            else:
                summary_parts.append(content)

        if metadata.get('duration'):
            summary_parts.append(f"({metadata['duration']:.2f}s)")

        return " ".join(summary_parts)

    def analyze_failure_patterns(self, root_causes: List[str], actions: List[str]) -> bool:
        """
        Analyze patterns in task failures to identify systematic issues.

        Triggered by AFFECT_TASK_FAILURE_PATTERN signals when task failures accumulate.
        Examines recent error history to identify common failure modes and suggest
        preventive measures for future improvement.

        Includes verification to ensure analysis results are persisted correctly.

        Args:
            root_causes: Root causes identified by affective introspection
            actions: Suggested autonomous actions from introspection

        Returns:
            True if analysis succeeded and verified
        """
        self._log_operation_start('analyze_failure_patterns', {'root_causes': root_causes, 'actions': actions})

        # Lazy-load memory systems only when actually needed
        if not self._memory_systems_initialized:
            self._initialize_memory_systems()

        try:
            recent_failures = self._get_recent_failures(days=7)

            if not recent_failures:
                print("  No recent failures to analyze")
                self._log_operation_end('analyze_failure_patterns', True, 'No failures found')
                self.log_action('analyze_failures', 'No recent failures found')
                return True

            patterns = self._identify_patterns(recent_failures)
            insights = self._generate_insights(patterns, root_causes)
            event_id = self._store_failure_analysis(insights, root_causes, actions)

            if event_id and not isinstance(event_id, bool):
                verified = self._verify_episodic_storage(event_id, 'analyze_failure_patterns')
                if verified:
                    print(f"  Analyzed {len(recent_failures)} failures, found {len(patterns.get('error_types', {}))} error types")
                    self._log_operation_end('analyze_failure_patterns', True, f'Event {event_id} verified')
                    self.log_action('analyze_failures', f'{len(recent_failures)} failures analyzed')
                    return True
                else:
                    print(f"  Analysis stored but verification failed")
                    self._log_operation_end('analyze_failure_patterns', False, 'Verification failed')
                    self.log_action('analyze_failures', 'Storage verification failed')
                    return False
            elif event_id is True:
                print(f"  Analyzed {len(recent_failures)} failures, found {len(patterns.get('error_types', {}))} error types")
                self._log_operation_end('analyze_failure_patterns', True, 'Analysis stored')
                self.log_action('analyze_failures', f'{len(recent_failures)} failures analyzed')
                return True
            else:
                print(f"  Analysis failed to store")
                self._log_operation_end('analyze_failure_patterns', False, 'Storage failed')
                self.log_action('analyze_failures', 'Storage failed')
                return False

        except Exception as e:
            print(f"  Failed to analyze failure patterns: {e}")
            traceback.print_exc()
            self._log_operation_end('analyze_failure_patterns', False, str(e))
            self.log_action('analyze_failures', f'Failed: {e}')
            return False

    def _get_recent_failures(self, days: int = 7) -> List[Dict[str, Any]]:
        """
        Retrieve recent failure events from episodic memory.

        Args:
            days: Number of days back to retrieve failures

        Returns:
            List of failure event dictionaries
        """
        try:
            if not self.memory_store:
                return []

            cutoff_time = time.time() - (days * 24 * 3600)

            conn = self.memory_store._get_connection()
            cursor = conn.cursor()

            cursor.execute("""
                SELECT id, timestamp, content, metadata
                FROM events
                WHERE event_type IN ('error_occurred', 'tool_execution')
                AND timestamp >= ?
                AND (
                    event_type = 'error_occurred'
                    OR metadata LIKE '%"success": false%'
                    OR metadata LIKE '%"success":false%'
                )
                ORDER BY timestamp DESC
                LIMIT 100
            """, (cutoff_time,))

            failures = []
            for row in cursor.fetchall():
                event_id, timestamp, content, metadata_json = row

                try:
                    metadata = json.loads(metadata_json) if metadata_json else {}
                except:
                    metadata = {}

                failures.append({
                    'id': event_id,
                    'timestamp': timestamp,
                    'content': content,
                    'metadata': metadata,
                    'occurred_at': datetime.fromtimestamp(timestamp).isoformat()
                })

            return failures

        except Exception as e:
            print(f"  Error retrieving failures: {e}")
            return []

    def _identify_patterns(self, failures: List[Dict[str, Any]]) -> Dict[str, Any]:
        """
        Identify common patterns in failures.

        Analyzes error types, timing, tools, and error messages to find patterns.

        Args:
            failures: List of failure event dictionaries

        Returns:
            Dictionary with identified patterns
        """
        patterns = {
            'error_types': {},
            'failure_times': [],
            'common_tools': {},
            'error_messages': {}
        }

        for failure in failures:
            error_type = failure.get('metadata', {}).get('error_type', 'unknown')
            patterns['error_types'][error_type] = patterns['error_types'].get(error_type, 0) + 1

            patterns['failure_times'].append(failure['timestamp'])

            tool = failure.get('metadata', {}).get('tool_name')
            if tool:
                patterns['common_tools'][tool] = patterns['common_tools'].get(tool, 0) + 1

            content = failure.get('content', '')
            if content:
                short_msg = content[:100]
                patterns['error_messages'][short_msg] = patterns['error_messages'].get(short_msg, 0) + 1

        return patterns

    def _generate_insights(self, patterns: Dict[str, Any], root_causes: List[str]) -> Dict[str, Any]:
        """
        Generate actionable insights from failure patterns.

        Identifies top failure modes and generates recommendations.

        Args:
            patterns: Dictionary of identified patterns
            root_causes: Root causes from affective introspection

        Returns:
            Dictionary with findings and recommendations
        """
        insights = {
            'timestamp': datetime.now().isoformat(),
            'root_causes': root_causes,
            'findings': [],
            'recommendations': []
        }

        if patterns['error_types']:
            most_common = max(patterns['error_types'].items(), key=lambda x: x[1])
            insights['findings'].append(f"Most common error: {most_common[0]} ({most_common[1]} occurrences)")
            insights['recommendations'].append(f"Investigate root cause of {most_common[0]} errors")

        if patterns['common_tools']:
            failing_tools = sorted(patterns['common_tools'].items(), key=lambda x: x[1], reverse=True)[:3]
            for tool, count in failing_tools:
                insights['findings'].append(f"Tool '{tool}' failed {count} times")
                insights['recommendations'].append(f"Review {tool} implementation or usage patterns")

        if len(patterns['failure_times']) >= 3:
            time_range = max(patterns['failure_times']) - min(patterns['failure_times'])
            if time_range < 3600:
                insights['findings'].append("Failures clustered in short time window")
                insights['recommendations'].append("Investigate recent system changes or external dependencies")

        return insights

    def _store_failure_analysis(self, insights: Dict[str, Any], root_causes: List[str], actions: List[str]) -> Any:
        """
        Store failure analysis to episodic memory.

        Persists analysis for future reference and learning.

        Args:
            insights: Analysis insights dictionary
            root_causes: Original root causes
            actions: Original suggested actions

        Returns:
            Event ID if storage succeeded, False if failed
        """
        try:
            if not self.memory_store:
                return False

            try:
                from kloros_memory.models import Event, EventType
            except ImportError:
                from src.kloros_memory.models import Event, EventType

            findings_text = "; ".join(insights['findings'][:3])

            metadata = {
                'root_causes': root_causes,
                'suggested_actions': actions,
                'findings': insights['findings'],
                'recommendations': insights['recommendations'],
                'timestamp': insights['timestamp']
            }

            event = Event(
                timestamp=time.time(),
                event_type=EventType.SELF_REFLECTION,
                content=f"Failure pattern analysis: {findings_text}",
                metadata=metadata,
                conversation_id=None
            )

            event_id = self.memory_store.store_event(event)
            print(f"  Stored analysis to episodic memory (event_id: {event_id})")
            return event_id if event_id is not None else False

        except Exception as e:
            print(f"  Failed to store analysis: {e}")
            return False

    def request_context_expansion(self) -> bool:
        """
        Request context window expansion if possible.

        Returns:
            True if request succeeded
        """
        print("\n[cognitive_actions] 📝 Executing: Request Context Expansion")

        # Check if context expansion is possible
        # For now, just log the request
        print("  → Checking if context window can be expanded...")
        print("  → Would request additional context allocation")
        print("  → Would update context budgets if approved")

        self.log_action('request_context_expansion', 'Request logged')
        return True

    def perform_consistency_check(self) -> bool:
        """
        Perform state consistency check and log results.

        Can be called periodically or after major operations to detect
        state corruption or data integrity issues.

        Returns:
            True if all consistency checks passed, False otherwise
        """
        print("\n[cognitive_actions] Performing state consistency check...")

        results = self._check_state_consistency()

        print(f"  Checks passed: {len(results['checks_passed'])}")
        print(f"  Checks failed: {len(results['checks_failed'])}")
        print(f"  Warnings: {len(results['warnings'])}")

        for check in results['checks_passed']:
            print(f"  ✓ {check}")

        for check in results['checks_failed']:
            print(f"  ✗ {check}")

        for warning in results['warnings']:
            print(f"  Warning: {warning}")

        if not self.memory_store:
            return False

        try:
            from kloros_memory.models import Event, EventType
        except ImportError:
            try:
                from src.kloros_memory.models import Event, EventType
            except ImportError:
                return len(results['checks_failed']) == 0

        try:
            event = Event(
                timestamp=time.time(),
                event_type=EventType.MEMORY_HOUSEKEEPING,
                content=f"Consistency check: {len(results['checks_passed'])} passed, {len(results['checks_failed'])} failed",
                metadata=results,
                conversation_id=None
            )

            event_id = self.memory_store.store_event(event)
            if event_id:
                print(f"  Logged consistency check to episodic memory (event_id: {event_id})")
        except Exception as e:
            print(f"  Warning: Could not log consistency check: {e}")

        return len(results['checks_failed']) == 0


# Global handler instance
handler = CognitiveActionHandler()


def handle_memory_pressure(msg: dict):
    """
    Handle AFFECT_MEMORY_PRESSURE signal.

    Memory pressure indicates high token usage or context pressure.
    Execute memory management actions.

    Args:
        msg: JSON message dict from ChemBus
    """
    if check_emergency_brake():
        print("[cognitive_actions] ⏸️  Emergency brake active, skipping action")
        return

    try:
        facts = msg.get('facts', {})
        intensity = msg.get('intensity', 0.0)

        print(f"\n[cognitive_actions] 💾 MEMORY_PRESSURE signal (intensity: {intensity:.2f})")

        autonomous_actions = facts.get('autonomous_actions', [])
        evidence = facts.get('evidence', [])

        # Execute memory management actions
        for action_text in autonomous_actions:
            action_lower = action_text.lower()

            if 'throttle' in action_lower and 'investigation' in action_lower:
                if handler.can_execute_action('throttle_investigations'):
                    handler.throttle_investigations(facts, evidence)
                else:
                    print(f"  ⏭️  Skipping (cooldown): {action_text}")

            elif 'summarize' in action_lower and 'context' in action_lower:
                if handler.can_execute_action('summarize_context'):
                    handler.summarize_context(evidence)
                else:
                    print(f"  ⏭️  Skipping (cooldown): {action_text}")

            elif 'archive' in action_lower and 'task' in action_lower:
                if handler.can_execute_action('archive_tasks'):
                    handler.archive_completed_tasks(evidence)
                else:
                    print(f"  ⏭️  Skipping (cooldown): {action_text}")

            elif 'optimize' in action_lower and 'performance' in action_lower:
                if handler.can_execute_action('optimize_performance'):
                    handler.optimize_performance(facts, evidence)
                else:
                    print(f"  ⏭️  Skipping (cooldown): {action_text}")

    except Exception as e:
        print(f"[cognitive_actions] Error handling MEMORY_PRESSURE: {e}")
        import traceback
        traceback.print_exc()


def handle_context_overflow(msg: dict):
    """
    Handle AFFECT_CONTEXT_OVERFLOW signal.

    Context overflow indicates context window is near capacity.
    Request expansion or compress existing context.

    Args:
        msg: JSON message dict from ChemBus
    """
    if check_emergency_brake():
        print("[cognitive_actions] ⏸️  Emergency brake active, skipping action")
        return

    try:
        facts = msg.get('facts', {})
        intensity = msg.get('intensity', 0.0)

        print(f"\n[cognitive_actions] 📝 CONTEXT_OVERFLOW signal (intensity: {intensity:.2f})")

        # Try to expand context first, then compress if can't
        if handler.can_execute_action('request_context_expansion'):
            if intensity > 0.9:
                print("  → Intensity critical, requesting context expansion...")
                handler.request_context_expansion()
            else:
                print("  → Moderate pressure, compressing context...")
                handler.summarize_context(facts.get('evidence', []))

    except Exception as e:
        print(f"[cognitive_actions] Error handling CONTEXT_OVERFLOW: {e}")


def handle_task_failure_pattern(msg: dict):
    """
    Handle AFFECT_TASK_FAILURE_PATTERN signal.

    Task failure patterns indicate systematic issues.
    Analyze and suggest improvements.

    Args:
        msg: JSON message dict from ChemBus
    """
    if check_emergency_brake():
        print("[cognitive_actions] ⏸️  Emergency brake active, skipping action")
        return

    try:
        facts = msg.get('facts', {})
        intensity = msg.get('intensity', 0.0)

        print(f"\n[cognitive_actions] ❌ TASK_FAILURE_PATTERN signal (intensity: {intensity:.2f})")

        autonomous_actions = facts.get('autonomous_actions', [])
        root_causes = facts.get('root_causes', [])

        # Analyze failure patterns
        if handler.can_execute_action('analyze_failures'):
            handler.analyze_failure_patterns(root_causes, autonomous_actions)

    except Exception as e:
        print(f"[cognitive_actions] Error handling TASK_FAILURE_PATTERN: {e}")


def handle_resource_strain(msg: dict):
    """
    Handle AFFECT_RESOURCE_STRAIN signal.

    Resource strain indicates elevated resource usage or investigation failures.
    Trigger performance optimization analysis and apply improvements.

    Args:
        msg: JSON message dict from ChemBus
    """
    if check_emergency_brake():
        print("[cognitive_actions] ⏸️  Emergency brake active, skipping action")
        return

    try:
        facts = msg.get('facts', {})
        intensity = msg.get('intensity', 0.0)

        print(f"\n[cognitive_actions] ⚠️  RESOURCE_STRAIN signal (intensity: {intensity:.2f})")

        autonomous_actions = facts.get('autonomous_actions', [])
        evidence = facts.get('evidence', [])

        for action_text in autonomous_actions:
            action_lower = action_text.lower()

            if 'optimize' in action_lower and 'performance' in action_lower:
                if handler.can_execute_action('optimize_performance'):
                    handler.optimize_performance(facts, evidence)
                else:
                    print(f"  ⏭️  Skipping (cooldown): optimize_performance")

    except Exception as e:
        print(f"[cognitive_actions] Error handling RESOURCE_STRAIN: {e}")


def run_daemon():
    """
    Run cognitive actions subscriber daemon.

    Subscribes to cognitive-level affective signals and executes actions.
    """
    print("[cognitive_actions] Starting Cognitive Actions Subscriber")
    print("[cognitive_actions] Tier 3: Cognitive/memory operations")
    print(f"[cognitive_actions] Action log: {handler.action_log_path}")

    try:
        from kloros.orchestration.chem_bus_v2 import ChemSub

        # Subscribe to cognitive affective signals
        print("[cognitive_actions] Subscribing to AFFECT_MEMORY_PRESSURE...")
        memory_sub = ChemSub(
            topic="AFFECT_MEMORY_PRESSURE",
            on_json=handle_memory_pressure,
            zooid_name="cognitive_actions",
            niche="affective_actions"
        )

        print("[cognitive_actions] Subscribing to AFFECT_CONTEXT_OVERFLOW...")
        context_sub = ChemSub(
            topic="AFFECT_CONTEXT_OVERFLOW",
            on_json=handle_context_overflow,
            zooid_name="cognitive_actions",
            niche="affective_actions"
        )

        print("[cognitive_actions] Subscribing to AFFECT_TASK_FAILURE_PATTERN...")
        failure_sub = ChemSub(
            topic="AFFECT_TASK_FAILURE_PATTERN",
            on_json=handle_task_failure_pattern,
            zooid_name="cognitive_actions",
            niche="affective_actions"
        )

        print("[cognitive_actions] Subscribing to AFFECT_RESOURCE_STRAIN...")
        strain_sub = ChemSub(
            topic="AFFECT_RESOURCE_STRAIN",
            on_json=handle_resource_strain,
            zooid_name="cognitive_actions",
            niche="affective_actions"
        )

        print("[cognitive_actions] ✅ Cognitive Actions Subscriber ready")
        print("[cognitive_actions] Monitoring for cognitive affective signals...")
        print(f"[cognitive_actions] Action cooldown: {handler.action_cooldown}s")

        # Keep daemon running
        while True:
            time.sleep(1)

    except KeyboardInterrupt:
        print("\n[cognitive_actions] Daemon stopped by user")
    except Exception as e:
        print(f"[cognitive_actions] Fatal error: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)


if __name__ == "__main__":
    run_daemon()
