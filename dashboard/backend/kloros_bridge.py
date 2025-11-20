"""
Bridge to KLoROS instance for reading meta-cognitive state.

Reads state from KLoROS via shared state file updated by KLoROS.
"""
import json
import sys
from pathlib import Path
from datetime import datetime, timedelta
from typing import Optional
from models import (
    EnhancedMetaState, QualityScores, Issues, Interventions,
    Affect, SessionInfo, SystemResources, ConversationTurn,
    ConsciousnessDetails, MemoryInsights, InterventionHistoryEntry,
    QualityHistorySample, EmotionalTrajectoryPoint,
    CuriosityState, CuriosityQuestion, InternalDialogue, XAITrace
)

# Path to KLoROS shared state file (written by KLoROS every second)
STATE_FILE = Path("/tmp/kloros_meta_state.json")

# Fallback: Try to import KLoROS directly if running in same process
KLoROS_PATH = Path("/home/kloros/src")
if KLoROS_PATH.exists():
    sys.path.insert(0, str(KLoROS_PATH.parent))


class KLoROSBridge:
    """
    Bridge to read meta-cognitive state from KLoROS.

    Supports two modes:
    1. File-based: Read from /tmp/kloros_meta_state.json (updated by KLoROS)
    2. Direct: Import KLoROS module and read state directly (future)
    """

    def __init__(self, mode: str = "file"):
        """
        Initialize bridge.

        Args:
            mode: "file" (read from state file) or "direct" (import KLoROS)
        """
        self.mode = mode
        self.last_update = None
        self._cached_state = None

    def get_meta_state(self) -> Optional[EnhancedMetaState]:
        """
        Get current meta-cognitive state.

        Returns:
            MetaState object or None if unavailable
        """
        if self.mode == "file":
            return self._get_state_from_file()
        else:
            return self._get_state_direct()

    def _get_state_from_file(self) -> Optional[EnhancedMetaState]:
        """Read state from shared file."""
        if not STATE_FILE.exists():
            return self._get_fallback_state()

        try:
            with open(STATE_FILE) as f:
                data = json.load(f)

            # Check if state is stale (>5 seconds old)
            timestamp = datetime.fromisoformat(data.get("timestamp", datetime.now().isoformat()))
            if datetime.now() - timestamp > timedelta(seconds=5):
                print(f"[bridge] Warning: State is stale ({(datetime.now() - timestamp).seconds}s old)")

            self.last_update = timestamp

            # Build EnhancedMetaState from JSON (using model_validate to handle nested dicts)
            state = EnhancedMetaState.model_validate(data)

            # Only cache non-empty states to prevent oscillation between empty and cached data
            # If we successfully read data, always return it (even if empty)
            # But only update cache if it has meaningful content
            if state.recent_turns and len(state.recent_turns) > 0:
                self._cached_state = state

            return state

        except Exception as e:
            print(f"[bridge] Error reading state file: {e}")
            # On error, return cached state if available, otherwise fallback
            return self._cached_state or self._get_fallback_state()

    def _get_state_direct(self) -> Optional[EnhancedMetaState]:
        """
        Read state by importing KLoROS directly.

        NOT IMPLEMENTED - KLoROS runs as separate process.
        Use file-based mode instead.
        """
        # TODO: Implement direct access via shared memory or RPC
        return self._get_fallback_state()

    def _get_fallback_state(self) -> EnhancedMetaState:
        """Return a safe fallback state when KLoROS is unavailable."""
        # Use model_validate with empty state structure
        return EnhancedMetaState.model_validate({
            'timestamp': datetime.now().isoformat(),
            'conversation_health': 0.0,
            'quality_scores': {
                'progress': 0.0,
                'clarity': 0.0,
                'engagement': 0.0
            },
            'issues': {
                'repetition': False,
                'stuck': False,
                'confusion': False
            },
            'interventions': {
                'clarify': False,
                'change_approach': False,
                'summarize': False,
                'confirm': False,
                'break_suggested': False
            },
            'affect': {
                'valence': 0.0,
                'arousal': 0.0,
                'uncertainty': 1.0,
                'fatigue': 0.0,
                'curiosity': 0.0
            },
            'session': {
                'turn_count': 0,
                'duration_seconds': 0,
                'topics': [],
                'entities': []
            },
            'meta_confidence': 0.0,
            'recent_turns': [],
            'consciousness_details': {},
            'memory_insights': {},
            'system_resources': {
                'timestamp': datetime.now().isoformat(),
                'cpu_percent': 0.0,
                'memory_percent': 0.0,
                'memory_used_gb': 0.0,
                'memory_total_gb': 0.0,
                'process_cpu': 0.0,
                'process_memory_mb': 0.0,
                'gpus': []
            },
            'intervention_history': [],
            'quality_history': [],
            'emotional_trajectory': [],
            'resource_history': []
        })

    def is_kloros_running(self) -> bool:
        """Check if KLoROS is actively updating state."""
        if not STATE_FILE.exists():
            return False

        try:
            with open(STATE_FILE) as f:
                data = json.load(f)

            timestamp = datetime.fromisoformat(data.get("timestamp", "2000-01-01T00:00:00"))
            return (datetime.now() - timestamp).seconds < 5
        except:
            return False

    def get_curiosity_state(self) -> Optional[CuriosityState]:
        """
        Get current curiosity and introspection state from KLoROS.

        Returns:
            CuriosityState with active questions and internal dialogue,
            or None if not available
        """
        try:
            # Try to read from curiosity state file
            curiosity_file = Path("/tmp/kloros_curiosity.json")
            if not curiosity_file.exists():
                return None

            with open(curiosity_file) as f:
                data = json.load(f)

            # Convert to CuriosityState model
            return CuriosityState(**data)
        except Exception as e:
            print(f"[bridge] Error reading curiosity state: {e}")
            return None

    def get_internal_dialogue(self, limit: int = 10):
        """
        Get recent internal dialogue/thoughts from KLoROS.

        Args:
            limit: Maximum number of thoughts to return

        Returns:
            List of InternalDialogue objects, or empty list
        """
        try:
            # Try to read from internal dialogue log
            dialogue_file = Path("/tmp/kloros_internal_dialogue.jsonl")
            if not dialogue_file.exists():
                return []

            # Read last N lines
            dialogue_entries = []
            with open(dialogue_file) as f:
                lines = f.readlines()
                for line in lines[-limit:]:
                    try:
                        entry_data = json.loads(line)
                        dialogue_entries.append(InternalDialogue(**entry_data))
                    except:
                        continue

            return dialogue_entries
        except Exception as e:
            print(f"[bridge] Error reading internal dialogue: {e}")
            return []

    def get_xai_traces(self, limit: int = 5, decision_type: Optional[str] = None):
        """
        Get recent XAI reasoning traces from KLoROS.

        Args:
            limit: Maximum number of traces to return
            decision_type: Optional filter by decision type

        Returns:
            List of XAITrace objects, or empty list
        """
        try:
            # Try to read from XAI traces directory
            xai_dir = Path("/tmp/kloros_xai_traces")
            if not xai_dir.exists():
                return []

            # Get recent trace files
            trace_files = sorted(xai_dir.glob("*.json"), key=lambda p: p.stat().st_mtime, reverse=True)

            traces = []
            for trace_file in trace_files[:limit * 2]:  # Read more than limit in case filtering
                try:
                    with open(trace_file) as f:
                        trace_data = json.loads(f.read())

                    # Filter by decision type if specified
                    if decision_type and trace_data.get("decision_type") != decision_type:
                        continue

                    traces.append(XAITrace(**trace_data))

                    if len(traces) >= limit:
                        break
                except:
                    continue

            return traces
        except Exception as e:
            print(f"[bridge] Error reading XAI traces: {e}")
            return []

    def get_xai_trace_by_id(self, decision_id: str) -> Optional[XAITrace]:
        """
        Get a specific XAI trace by decision ID.

        Args:
            decision_id: The unique decision ID

        Returns:
            XAITrace object, or None if not found
        """
        try:
            xai_dir = Path("/tmp/kloros_xai_traces")
            trace_file = xai_dir / f"{decision_id}.json"

            if not trace_file.exists():
                return None

            with open(trace_file) as f:
                trace_data = json.load(f)

            return XAITrace(**trace_data)
        except Exception as e:
            print(f"[bridge] Error reading XAI trace {decision_id}: {e}")
            return None


# Global bridge instance
bridge = KLoROSBridge(mode="file")
