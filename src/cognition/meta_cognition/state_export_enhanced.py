"""
Enhanced state export for comprehensive dashboard visualization.

Exports:
- Core meta-cognitive state
- Recent conversation turns
- Intervention history
- System performance metrics (CPU, RAM, GPU via NVML)
- Memory insights
- Consciousness details
- Historical data
"""
import json
import threading
import time
import psutil
import os
from pathlib import Path
from datetime import datetime
from collections import deque
from typing import Dict, List, Any

# Import curiosity system for dynamic curiosity calculation
try:
    from src.cognition.mind.cognition.curiosity_core import CuriosityCore
    CURIOSITY_AVAILABLE = True
except ImportError:
    CURIOSITY_AVAILABLE = False

# Use user-specific file paths to avoid permission conflicts
import getpass
_USER = getpass.getuser()
STATE_FILE = Path(f"/tmp/kloros_meta_state_{_USER}.json")
HISTORY_FILE = Path(f"/tmp/kloros_state_history_{_USER}.json")
EXPORT_INTERVAL = 1.0

# Keep historical data in memory
intervention_history = deque(maxlen=1000)  # Last 1000 interventions
quality_history = deque(maxlen=900)  # Last 15 minutes at 1Hz
emotional_trajectory = deque(maxlen=900)  # 15 minutes of valence/arousal
resource_history = deque(maxlen=300)  # 5 minutes of resource usage


def calculate_dynamic_curiosity() -> float:
    """
    Calculate dynamic curiosity from KLoROS's actual curiosity question feed.

    Returns:
        Curiosity level (0.0 to 1.0) based on:
        - Number of active curiosity questions
        - Value estimates of top questions
        - Evidence richness
    """
    if not CURIOSITY_AVAILABLE:
        return 0.5  # Fallback to static value

    try:
        curiosity_core = CuriosityCore()
        feed = curiosity_core.feed

        if not feed or not feed.questions:
            return 0.0  # No questions = no curiosity

        # Calculate curiosity from multiple factors
        question_count = len(feed.questions)
        top_questions = feed.questions[:10]  # Top 10 by value

        # Factor 1: Question volume (more questions = more curious)
        volume_factor = min(question_count / 15.0, 1.0)

        # Factor 2: Average value of top questions
        if top_questions:
            avg_value = sum(q.value_estimate for q in top_questions) / len(top_questions)
        else:
            avg_value = 0.0

        # Factor 3: Evidence richness (questions with more evidence are higher quality)
        if top_questions:
            avg_evidence = sum(len(q.evidence) for q in top_questions) / len(top_questions)
            evidence_factor = min(avg_evidence / 3.0, 0.5)  # Cap at 0.5
        else:
            evidence_factor = 0.0

        # Combined curiosity score
        curiosity = min(
            0.4 * volume_factor +
            0.4 * avg_value +
            0.2 * evidence_factor,
            1.0
        )

        return curiosity

    except Exception as e:
        # Log error but don't crash dashboard export
        print(f"[curiosity] Error calculating dynamic curiosity: {e}")
        return 0.5  # Fallback


def export_curiosity_state():
    """
    Export KLoROS's curiosity questions to /tmp/kloros_curiosity.json
    for dashboard consumption.
    """
    if not CURIOSITY_AVAILABLE:
        return

    try:
        curiosity_core = CuriosityCore()
        # Load existing feed from disk
        curiosity_core.load_feed_from_disk()
        feed = curiosity_core.feed

        if not feed:
            # No feed yet, export empty state
            curiosity_state = {
                'curiosity_level': 0.0,
                'active_questions': [],
                'recent_investigations': [],
                'internal_dialogue': [],
                'total_questions_generated': 0,
                'total_questions_answered': 0
            }
        else:
            # Get top active questions
            active_questions = []
            for q in feed.questions[:10]:  # Top 10
                active_questions.append({
                    'id': q.id,
                    'hypothesis': q.hypothesis,
                    'question': q.question,
                    'evidence': q.evidence,
                    'action_class': q.action_class.value if hasattr(q.action_class, 'value') else str(q.action_class),
                    'autonomy': getattr(q, 'autonomy_level', 2),
                    'value_estimate': q.value_estimate,
                    'cost': q.cost,
                    'status': 'active',
                    'created_at': getattr(q, 'created_at', datetime.now().isoformat()),
                    'capability_key': getattr(q, 'capability_key', None)
                })

            curiosity_state = {
                'curiosity_level': calculate_dynamic_curiosity(),
                'active_questions': active_questions,
                'recent_investigations': [],  # TODO: Track answered questions
                'internal_dialogue': [],  # Will be populated by MetaCognitiveBridge
                'total_questions_generated': len(feed.questions),
                'total_questions_answered': 0  # TODO: Track completions
            }

        # Write to file using atomic write (temp + rename)
        # Use user-specific paths to avoid permission conflicts
        # Use PID+timestamp to make temp file unique PER INVOCATION and prevent race conditions
        import os
        import threading
        pid = os.getpid()
        tid = threading.get_ident()
        ts = int(time.time() * 1000000)  # microsecond timestamp
        temp_path = f'/tmp/kloros_curiosity_{_USER}.json.{pid}.{tid}.{ts}.tmp'
        final_path = f'/tmp/kloros_curiosity_{_USER}.json'

        try:
            with open(temp_path, 'w') as f:
                json.dump(curiosity_state, f, indent=2)
        except Exception as write_err:
            print(f"[curiosity] Failed to write temp file {temp_path}: {write_err}")
            return

        try:
            # Atomic rename (os.replace works across filesystems)
            os.replace(temp_path, final_path)
        except Exception as rename_err:
            print(f"[curiosity] Failed to rename {temp_path} -> {final_path}: {rename_err}")
            # Clean up temp file if it exists
            if os.path.exists(temp_path):
                try:
                    os.remove(temp_path)
                except Exception:
                    pass  # Best effort cleanup
            return

    except Exception as e:
        print(f"[curiosity] Error exporting curiosity state (outer): {e}")


def get_gpu_info_nvml():
    """Get GPU info using NVML (modern alternative to deprecated nvidia-smi)."""
    gpu_info = []
    try:
        import pynvml
        pynvml.nvmlInit()
        
        device_count = pynvml.nvmlDeviceGetCount()
        for i in range(device_count):
            handle = pynvml.nvmlDeviceGetHandleByIndex(i)
            
            # Get GPU name
            name = pynvml.nvmlDeviceGetName(handle)
            if isinstance(name, bytes):
                name = name.decode('utf-8')
            
            # Get utilization
            util = pynvml.nvmlDeviceGetUtilizationRates(handle)
            
            # Get memory info
            mem_info = pynvml.nvmlDeviceGetMemoryInfo(handle)
            
            # Get temperature
            try:
                temp = pynvml.nvmlDeviceGetTemperature(handle, pynvml.NVML_TEMPERATURE_GPU)
            except:
                temp = 0
            
            gpu_info.append({
                'index': i,
                'name': name,
                'utilization_gpu': float(util.gpu),
                'utilization_memory': float(util.memory),
                'memory_used_mb': float(mem_info.used / (1024**2)),
                'memory_total_mb': float(mem_info.total / (1024**2)),
                'temperature_c': float(temp)
            })
        
        pynvml.nvmlShutdown()
    except Exception as e:
        pass
        # Silently fail if NVML not available or no GPUs
        pass
    
    return gpu_info


def get_system_resources() -> Dict[str, Any]:
    """Get current system resource usage."""
    try:
        process = psutil.Process(os.getpid())
        
        # GPU info using NVML
        gpu_info = get_gpu_info_nvml()
        
        return {
            'timestamp': datetime.now().isoformat(),
            'cpu_percent': psutil.cpu_percent(interval=0.1),
            'memory_percent': psutil.virtual_memory().percent,
            'memory_used_gb': psutil.virtual_memory().used / (1024**3),
            'memory_total_gb': psutil.virtual_memory().total / (1024**3),
            'process_cpu': process.cpu_percent(),
            'process_memory_mb': process.memory_info().rss / (1024**2),
            'gpus': gpu_info
        }
    except Exception as e:
        print(f"[resource-monitor] Error getting system resources: {e}")
        return {'error': str(e), 'timestamp': datetime.now().isoformat()}


def get_recent_turns(kloros_instance) -> List[Dict[str, Any]]:
    """Get recent conversation turns from dialogue monitor."""
    try:
        if not hasattr(kloros_instance, 'meta_dialogue_monitor'):
            return []
        
        monitor = kloros_instance.meta_dialogue_monitor
        turns = []
        
        for turn in monitor.recent_turns:
            turns.append({
                'role': turn['role'],
                'text': turn['text'],
                'timestamp': datetime.fromtimestamp(turn['timestamp']).isoformat() if turn.get('timestamp') else None
            })
        
        return turns
    except Exception as e:
        print(f"[state-export] Error getting turns: {e}")
        return []


def get_consciousness_details(kloros_instance) -> Dict[str, Any]:
    """Get detailed consciousness state including primary emotions."""
    try:
        if not hasattr(kloros_instance, 'consciousness') or not kloros_instance.consciousness:
            return {}
        
        consciousness = kloros_instance.consciousness
        affect = consciousness.current_affect

        details = {}

        if affect is not None:
            details['core_affect'] = {
                'valence': affect.valence,
                'arousal': affect.arousal,
                'dominance': getattr(affect, 'dominance', 0.0),
                'uncertainty': affect.uncertainty,
                'fatigue': affect.fatigue,
                'curiosity': affect.curiosity
            }
        
        # Get primary emotions if available
        if hasattr(consciousness, 'emotional_state') and consciousness.emotional_state is not None:
            emotional_state = consciousness.emotional_state
            details['primary_emotions'] = {
                'seeking': getattr(emotional_state, 'seeking', 0.0),
                'rage': getattr(emotional_state, 'rage', 0.0),
                'fear': getattr(emotional_state, 'fear', 0.0),
                'panic': getattr(emotional_state, 'panic', 0.0),
                'care': getattr(emotional_state, 'care', 0.0),
                'play': getattr(emotional_state, 'play', 0.0),
                'lust': getattr(emotional_state, 'lust', 0.0)
            }
        
        # Get homeostatic variables if available
        if hasattr(consciousness, 'homeostatic_variables'):
            details['homeostatic'] = []
            for var in consciousness.homeostatic_variables:
                details['homeostatic'].append({
                    'name': var.name,
                    'current': var.current,
                    'target': var.target,
                    'pressure': var.pressure,
                    'satisfied': var.satisfied
                })
        
        return details
    except Exception as e:
        print(f"[state-export] Error getting consciousness: {e}")
        return {}


def get_memory_insights(kloros_instance) -> Dict[str, Any]:
    """Get recent memory insights from reflective system."""
    try:
        insights = {
            'recent_reflections': [],
            'active_patterns': [],
            'memory_stats': {}
        }
        
        # Get reflective system insights
        if hasattr(kloros_instance, 'reflective_system'):
            reflective = kloros_instance.reflective_system
            
            # Get recent reflections (last 10)
            if hasattr(reflective, 'get_recent_reflections'):
                try:
                    recent = reflective.get_recent_reflections(limit=10)
                    for reflection in recent:
                        insights['recent_reflections'].append({
                            'pattern_type': getattr(reflection, 'pattern_type', 'unknown'),
                            'insight': getattr(reflection, 'insight', ''),
                            'confidence': getattr(reflection, 'confidence', 0.0),
                            'timestamp': getattr(reflection, 'timestamp', None)
                        })
                except:
                    pass
        
        # Get memory statistics from MemoryStore database
        try:
            from src.kloros_memory.storage import MemoryStore
            store = MemoryStore()
            stats = store.get_stats()
            
            # Map to dashboard expected format
            # Events are episodic memories, summaries are semantic/condensed memories
            insights['memory_stats'] = {
                'total_memories': stats.get('total_events', 0) + stats.get('total_summaries', 0),
                'episodic_count': stats.get('total_events', 0),
                'semantic_count': stats.get('total_summaries', 0),
                'events_24h': stats.get('events_24h', 0),
                'db_size_mb': stats.get('db_size_bytes', 0) / (1024 * 1024)
            }
        except Exception as mem_err:
            print(f"[state-export] Could not get memory stats: {mem_err}")
            insights['memory_stats'] = {
                'total_memories': 0,
                'episodic_count': 0,
                'semantic_count': 0
            }
        
        return insights
    except Exception as e:
        print(f"[state-export] Error getting memory insights: {e}")
        return {}


def track_intervention(intervention_type: str, reason: str):
    """Track an intervention in history."""
    intervention_history.append({
        'timestamp': datetime.now().isoformat(),
        'type': intervention_type,
        'reason': reason
    })


def export_enhanced_state(kloros_instance) -> dict:
    """Export comprehensive state with all dashboard data."""
    if not hasattr(kloros_instance, 'meta_bridge') or kloros_instance.meta_bridge is None:
        return _get_empty_state()
    
    try:
        bridge = kloros_instance.meta_bridge
        state = bridge.current_state
        
        # Core affect data
        affect_data = {
            'valence': 0.0,
            'arousal': 0.0,
            'dominance': 0.0,
            'uncertainty': state.uncertainty,
            'fatigue': state.fatigue,
            'curiosity': calculate_dynamic_curiosity()  # Dynamic from actual question feed
        }
        
        if hasattr(kloros_instance, 'consciousness') and kloros_instance.consciousness:
            affect = kloros_instance.consciousness.current_affect
            if affect is not None:
                affect_data.update({
                    'valence': affect.valence,
                    'arousal': affect.arousal,
                    'dominance': getattr(affect, 'dominance', 0.0)
                })
        
        # Session data
        session_data = {
            'turn_count': state.turn_count,
            'duration_seconds': 0,
            'topics': [],
            'entities': []
        }
        
        if hasattr(kloros_instance, 'conversation_flow') and kloros_instance.conversation_flow:
            flow_state = kloros_instance.conversation_flow.current
            session_data.update({
                'topics': list(flow_state.recent_topics) if hasattr(flow_state, 'recent_topics') else [],
                'entities': [str(e) for e in flow_state.entities.keys()] if hasattr(flow_state, 'entities') else []
            })
        
        # Quality scores
        quality_scores = {
            'progress': state.progress_score,
            'clarity': state.clarity_score,
            'engagement': 1.0
        }
        
        # Track interventions
        if state.needs_clarification:
            track_intervention('clarify', 'User confusion detected')
        if state.needs_approach_change:
            track_intervention('change_approach', 'Stuck pattern detected')
        if state.needs_summary:
            track_intervention('summarize', 'Conversation complexity threshold')
        
        # Add to historical data
        quality_history.append({
            'timestamp': datetime.now().isoformat(),
            'health': state.conversation_health,
            'progress': quality_scores['progress'],
            'clarity': quality_scores['clarity'],
            'engagement': quality_scores['engagement']
        })
        
        emotional_trajectory.append({
            'timestamp': datetime.now().isoformat(),
            'valence': affect_data['valence'],
            'arousal': affect_data['arousal']
        })
        
        resource_data = get_system_resources()
        resource_history.append(resource_data)
        
        # Build comprehensive state
        comprehensive_state = {
            'timestamp': datetime.now().isoformat(),
            'conversation_health': state.conversation_health,
            'quality_scores': quality_scores,
            'issues': {
                'repetition': state.repetition_detected,
                'stuck': state.needs_approach_change,
                'confusion': state.user_confused
            },
            'interventions': {
                'clarify': state.needs_clarification,
                'change_approach': state.needs_approach_change,
                'summarize': state.needs_summary,
                'confirm': state.needs_confirmation,
                'break_suggested': state.needs_break
            },
            'affect': affect_data,
            'session': session_data,
            'meta_confidence': state.meta_confidence,
            
            # Enhanced data
            'recent_turns': get_recent_turns(kloros_instance),
            'consciousness_details': get_consciousness_details(kloros_instance),
            'memory_insights': get_memory_insights(kloros_instance),
            'system_resources': resource_data,
            
            # Historical data (recent subsets)
            'intervention_history': list(intervention_history)[-20:],  # Last 20
            'quality_history': list(quality_history)[-60:],  # Last minute
            'emotional_trajectory': list(emotional_trajectory)[-60:],  # Last minute
            'resource_history': list(resource_history)[-30:]  # Last 30 seconds
        }
        
        return comprehensive_state
        
    except Exception as e:
        print(f"[state-export] Error: {e}")
        import traceback
        traceback.print_exc()
        return _get_empty_state()


def _get_empty_state() -> dict:
    """Return empty state structure."""
    return {
        'timestamp': datetime.now().isoformat(),
        'conversation_health': 0.0,
        'quality_scores': {'progress': 0.0, 'clarity': 0.0, 'engagement': 0.0},
        'issues': {'repetition': False, 'stuck': False, 'confusion': False},
        'interventions': {'clarify': False, 'change_approach': False, 'summarize': False, 'confirm': False, 'break_suggested': False},
        'affect': {'valence': 0.0, 'arousal': 0.0, 'dominance': 0.0, 'uncertainty': 1.0, 'fatigue': 0.0, 'curiosity': 0.0},
        'session': {'turn_count': 0, 'duration_seconds': 0, 'topics': [], 'entities': []},
        'meta_confidence': 0.0,
        'recent_turns': [],
        'consciousness_details': {},
        'memory_insights': {},
        'system_resources': {},
        'intervention_history': [],
        'quality_history': [],
        'emotional_trajectory': [],
        'resource_history': []
    }


def write_state_file(kloros_instance):
    """Write enhanced state to file using atomic write (temp + rename)."""
    state = export_enhanced_state(kloros_instance)
    try:
        # Write to temp file first (atomic write pattern)
        # Use PID+timestamp to make temp file unique PER INVOCATION and prevent race conditions
        import os
        import threading
        pid = os.getpid()
        tid = threading.get_ident()
        ts = int(time.time() * 1000000)  # microsecond timestamp
        temp_file = Path(f'/tmp/kloros_meta_state_{_USER}.json.{pid}.{tid}.{ts}.tmp')

        try:
            with open(temp_file, 'w') as f:
                json.dump(state, f, indent=2)
        except Exception as write_err:
            print(f"[state-export] Failed to write temp file {temp_file}: {write_err}")
            return

        try:
            # Atomic rename (prevents readers from seeing partial writes)
            os.replace(str(temp_file), str(STATE_FILE))
        except Exception as rename_err:
            print(f"[state-export] Failed to rename {temp_file} -> {STATE_FILE}: {rename_err}")
            # Clean up temp file if it exists
            if temp_file.exists():
                try:
                    temp_file.unlink()
                except Exception:
                    pass  # Best effort cleanup
            return
    except Exception as e:
        print(f"[state-export] Unexpected error: {e}")


def start_enhanced_export_daemon(kloros_instance):
    """Start enhanced export daemon."""
    def export_loop():
        print("[state-export] 📊 Enhanced state export daemon started (GPU via NVML)")
        while True:
            try:
                write_state_file(kloros_instance)
                export_curiosity_state()  # Export KLoROS's curiosity questions
                time.sleep(EXPORT_INTERVAL)
            except Exception as e:
                print(f"[state-export] Error in loop: {e}")
                time.sleep(EXPORT_INTERVAL)
    
    thread = threading.Thread(target=export_loop, daemon=True, name="EnhancedMetaStateExport")
    thread.start()
    print(f"[state-export] Enhanced export to {STATE_FILE} every {EXPORT_INTERVAL}s")
