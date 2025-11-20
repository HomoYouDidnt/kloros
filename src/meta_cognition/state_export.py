"""
Export meta-cognitive state for dashboard visualization.
"""
import json
import threading
import time
from pathlib import Path
from datetime import datetime

STATE_FILE = Path("/tmp/kloros_meta_state.json")
EXPORT_INTERVAL = 1.0

def export_meta_state(kloros_instance) -> dict:
    if not hasattr(kloros_instance, 'meta_bridge') or kloros_instance.meta_bridge is None:
        return _get_empty_state()
    
    try:
        bridge = kloros_instance.meta_bridge
        state = bridge.current_state
        
        affect_data = {
            "valence": 0.0,
            "arousal": 0.0,
            "uncertainty": state.uncertainty,
            "fatigue": state.fatigue,
            "curiosity": state.curiosity
        }
        
        if hasattr(kloros_instance, 'consciousness') and kloros_instance.consciousness:
            affect = kloros_instance.consciousness.current_affect
            affect_data.update({
                "valence": affect.valence,
                "arousal": affect.arousal
            })
        
        session_data = {
            "turn_count": state.turn_count,
            "duration_seconds": 0,
            "topics": [],
            "entities": []
        }
        
        if hasattr(kloros_instance, 'conversation_flow') and kloros_instance.conversation_flow:
            flow_state = kloros_instance.conversation_flow.current
            session_data.update({
                "topics": list(flow_state.recent_topics) if hasattr(flow_state, 'recent_topics') else [],
                "entities": [str(e) for e in flow_state.entities.keys()] if hasattr(flow_state, 'entities') else []
            })
        
        return {
            "timestamp": datetime.now().isoformat(),
            "conversation_health": state.conversation_health,
            "quality_scores": {
                "progress": state.progress_score,
                "clarity": state.clarity_score,
                "engagement": 1.0
            },
            "issues": {
                "repetition": state.repetition_detected,
                "stuck": state.needs_approach_change,
                "confusion": state.user_confused
            },
            "interventions": {
                "clarify": state.needs_clarification,
                "change_approach": state.needs_approach_change,
                "summarize": state.needs_summary,
                "confirm": state.needs_confirmation,
                "break_suggested": state.needs_break
            },
            "affect": affect_data,
            "session": session_data,
            "meta_confidence": state.meta_confidence
        }
    except Exception as e:
        print(f"[state-export] Error: {e}")
        return _get_empty_state()

def _get_empty_state() -> dict:
    return {
        "timestamp": datetime.now().isoformat(),
        "conversation_health": 0.0,
        "quality_scores": {"progress": 0.0, "clarity": 0.0, "engagement": 0.0},
        "issues": {"repetition": False, "stuck": False, "confusion": False},
        "interventions": {"clarify": False, "change_approach": False, "summarize": False, "confirm": False, "break_suggested": False},
        "affect": {"valence": 0.0, "arousal": 0.0, "uncertainty": 1.0, "fatigue": 0.0, "curiosity": 0.0},
        "session": {"turn_count": 0, "duration_seconds": 0, "topics": [], "entities": []},
        "meta_confidence": 0.0
    }

def write_state_file(kloros_instance):
    state = export_meta_state(kloros_instance)
    try:
        with open(STATE_FILE, 'w') as f:
            json.dump(state, f, indent=2)
    except Exception as e:
        print(f"[state-export] Failed to write: {e}")

def start_state_export_daemon(kloros_instance):
    def export_loop():
        print("[state-export] 📊 State export daemon started")
        while True:
            try:
                write_state_file(kloros_instance)
                time.sleep(EXPORT_INTERVAL)
            except Exception as e:
                print(f"[state-export] Error in loop: {e}")
                time.sleep(EXPORT_INTERVAL)
    
    thread = threading.Thread(target=export_loop, daemon=True, name="MetaStateExport")
    thread.start()
    print(f"[state-export] Exporting to {STATE_FILE} every {EXPORT_INTERVAL}s")
