#!/usr/bin/env python3
"""
D-REAM Evolution System for KLoROS - Enhanced with Intelligent Self-Reflection Integration

Complete autonomous AI evolution system with safety guarantees, personality preservation,
and intelligent analysis of KLoROS's own self-reflection data for data-driven improvements.
"""

import os
import sys
import time
import json
import shutil
from datetime import datetime, timedelta
from typing import Dict, List, Any, Optional, Tuple
from pathlib import Path
import hashlib

# Add KLoROS src to path for imports
current_dir = os.path.dirname(os.path.abspath(__file__))
if current_dir not in sys.path:
    sys.path.insert(0, current_dir)

# Try to import KLoROS memory system
try:
    from src.kloros_memory.storage import MemoryStore
    from src.kloros_memory.models import Event, EventType
    KLOROS_MEMORY_AVAILABLE = True
except ImportError:
    KLOROS_MEMORY_AVAILABLE = False
    print("[dream] KLoROS memory system not available - using fallback mode")

try:
    from kloros.orchestration.maintenance_mode import is_maintenance_mode
except ImportError:
    def is_maintenance_mode():
        return False

class DreamEvolutionManager:
    """Main D-REAM evolution manager for KLoROS autonomous improvement."""

    def __init__(self):
        self.evolution_enabled = int(os.getenv("KLR_ENABLE_DREAM_EVOLUTION", "0"))
        self.evolution_interval = int(os.getenv("KLR_DREAM_EVOLUTION_INTERVAL", "3600"))
        self.last_evolution_time = 0

        # Initialize components
        self.memory_adapter = KLoROSMemoryAdapter()
        self.safety_system = SafetyGateSystem()
        self.component_trainer = KLoROSComponentTrainer()

        # Create log directory
        self.log_dir = Path("/home/kloros/.kloros")
        self.log_dir.mkdir(exist_ok=True)

        if self.evolution_enabled:
            print("[dream] D-REAM Evolution Manager initialized with intelligent self-reflection integration")

    def should_evolve(self) -> bool:
        """Check if it's time for an evolution cycle."""
        # Re-check environment variable dynamically (in case it was set after initialization)
        evolution_enabled = int(os.getenv("KLR_ENABLE_DREAM_EVOLUTION", "0"))
        if not evolution_enabled:
            return False
        current_time = time.time()
        evolution_interval = int(os.getenv("KLR_DREAM_EVOLUTION_INTERVAL", "3600"))
        return (current_time - self.last_evolution_time) >= evolution_interval

    def run_evolution_cycle(self) -> Dict[str, Any]:
        """Run a complete evolution cycle with intelligent task generation."""
        # Check maintenance mode before running evolution
        if is_maintenance_mode():
            print("[dream] Skipping evolution cycle - system in maintenance mode")
            return {
                "timestamp": datetime.now().isoformat(),
                "success": False,
                "improvements_applied": [],
                "intelligent_analysis": True,
                "skipped": "maintenance_mode"
            }

        cycle_start = time.time()
        self.last_evolution_time = cycle_start

        result = {
            "timestamp": datetime.now().isoformat(),
            "success": False,
            "improvements_applied": [],
            "intelligent_analysis": True
        }

        try:
            print("[dream] Starting intelligent evolution cycle with self-reflection analysis...")

            # Get intelligent operational tasks based on real performance data
            tasks = self.memory_adapter.get_operational_tasks()
            print(f"[dream] Generated {len(tasks)} intelligent tasks from performance analysis")

            # INTEGRATION: Get winning experiments from external D-REAM runner
            try:
                from dream_winner_consumer import get_winner_consumer
                from dream_promotion_applier import get_promotion_applier

                winner_consumer = get_winner_consumer()
                applier = get_promotion_applier()

                external_winners = winner_consumer.get_new_winners(max_age_hours=24)
                if external_winners:
                    print(f"[dream] Consumed {len(external_winners)} winning experiments from external runner")

                    # Apply promotions with apply_map (if they have one)
                    for winner in external_winners:
                        if winner.get("source") == "external_dream_promotion":
                            # This is a promotion with apply_map - apply directly
                            params_hash = winner.get("params_hash")
                            promo_data = winner.get("parameter_recommendations", {})

                            # Reconstruct promotion for applier
                            promotion = {
                                "promotion_id": winner["task_id"],
                                "winner": {
                                    "params": promo_data.get("params", {}),
                                    "metrics": promo_data.get("metrics", {}),
                                    "fitness": winner.get("fitness")
                                },
                                "apply_map": promo_data.get("apply_map", {})
                            }

                            success, ack = applier.apply_promotion(promotion, params_hash)
                            if success:
                                print(f"[dream] ✓ Applied promotion {winner['task_id']}: {len(ack['changes'])} config changes")
                            else:
                                print(f"[dream] ✗ Blocked promotion {winner['task_id']}: {ack.get('reason', 'unknown')}")
                        else:
                            # Legacy winner without apply_map - add as task
                            tasks.append(winner)
            except Exception as e:
                print(f"[dream] Warning: Could not consume external winners: {e}")

            # Generate improvement candidates
            candidates = []
            for task in tasks:
                candidate = {
                    "task_id": task.get("task_id", "unknown"),
                    "text": task.get("text", ""),
                    "component": task.get("component", "system"),
                    "priority": task.get("priority", 5),
                    "evidence": task.get("evidence", "unknown"),
                    "parameter_recommendations": self._generate_recommendations(task)
                }
                candidates.append(candidate)

            # Sort by priority (higher is more important)
            candidates.sort(key=lambda x: x.get("priority", 0), reverse=True)

            # Apply evolutionary optimization for complex candidates
            improvements = []
            tool_synthesis_candidates = []
            simple_candidates = []
            
            # Separate complex evolutionary candidates from simple parameter tuning
            for candidate in candidates:
                if candidate.get('evidence') == 'tool_synthesis_analysis':
                    tool_synthesis_candidates.append(candidate)
                else:
                    simple_candidates.append(candidate)
            
            # Run evolutionary optimization for tool synthesis candidates
            if tool_synthesis_candidates:
                print(f"[dream] Running evolutionary optimization for {len(tool_synthesis_candidates)} complex candidates")
                evolutionary_results = self._run_evolutionary_optimization(tool_synthesis_candidates)
                improvements.extend(evolutionary_results)
            
            # Handle simple candidates with traditional parameter tuning
            for candidate in simple_candidates:
                is_safe, reason = self.safety_system.validate_candidate_safety(candidate)
                if is_safe:
                    improvement = self.component_trainer.apply_improvement(candidate)
                    if improvement:
                        improvement["evidence"] = candidate.get("evidence", "unknown")
                        improvement["priority"] = candidate.get("priority", 5)
                        improvements.append(improvement)
                        print(f"[dream] Applied improvement: {improvement['parameter']} = {improvement['new_value']} (evidence: {improvement['evidence']})")

            # Deduplicate improvements by parameter name (keep highest priority)
            seen_params = {}
            unique_improvements = []
            for imp in improvements:
                param = imp.get('parameter')
                if param not in seen_params or imp.get('priority', 0) > seen_params[param].get('priority', 0):
                    if param in seen_params:
                        print(f"[dream] Replacing duplicate {param}: priority {seen_params[param].get('priority')} → {imp.get('priority')}")
                    seen_params[param] = imp
                else:
                    print(f"[dream] Skipping duplicate improvement for {param}")

            unique_improvements = list(seen_params.values())

            result["improvements_applied"] = unique_improvements
            result["success"] = len(improvements) > 0
            result["tasks_analyzed"] = len(tasks)
            result["candidates_generated"] = len(candidates)

            if result["success"]:
                print(f"[dream] Applied {len(improvements)} intelligent improvements from {len(tasks)} analyzed performance issues")
            else:
                print("[dream] No improvements applied - system already optimized or no issues detected")

        except Exception as e:
            result["error"] = str(e)
            print(f"[dream] Evolution cycle failed: {e}")

        # Log results
        try:
            log_file = self.log_dir / "dream_evolution.log"
            with open(log_file, "a") as f:
                f.write(json.dumps(result) + "\n")
        except:
            pass

        return result


    def _run_evolutionary_optimization(self, candidates: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """Run complete D-REAM evolutionary optimization with real integration."""
        improvements = []

        try:
            # Import the complete D-REAM system
            from complete_dream_system import CompleteDreamSystem

            print(f"[dream] 🧬 Initializing Complete D-REAM System")

            # Initialize complete D-REAM system
            dream_system = CompleteDreamSystem()

            # Run complete D-REAM cycle with real integration
            cycle_result = dream_system.run_complete_dream_cycle(candidates)

            # Process results into improvements
            if cycle_result.status == "success":
                for winner in cycle_result.evolutionary_winners:
                    improvement = {
                        'candidate_id': winner.get('approach_id', 'unknown'),
                        'cycle': cycle_result.cycle_id,
                        'winner_approach': winner.get('approach_id'),
                        'improvement_score': winner.get('improvement_score', 0),
                        'performance_score': winner.get('performance_score', 0),
                        'evidence': 'complete_dream_system',
                        'type': 'real_evolutionary_improvement',
                        'real_integration': True,
                        'approval_requests': cycle_result.approval_requests,
                        'ready_for_deployment': winner.get('ready_for_deployment', False)
                    }
                    improvements.append(improvement)
                    print(f"[dream] 🏆 Real evolutionary improvement: {winner.get('approach_id')} (score: {winner.get('performance_score', 0):.3f})")

                # Store D-REAM system reference for approval processing
                self.dream_system = dream_system

                print(f"[dream] ✅ Complete D-REAM cycle successful: {len(improvements)} improvements, {len(cycle_result.approval_requests)} approval requests")

                # If there are approval requests, notify about them
                if cycle_result.approval_requests:
                    print(f"[dream] 📋 {len(cycle_result.approval_requests)} evolutionary improvements ready for KLoROS approval")
                    # Store pending approvals for later processing
                    self.pending_evolutionary_approvals = cycle_result.approval_requests

            else:
                print(f"[dream] ❌ D-REAM cycle failed: {cycle_result.status}")
                # Create fallback improvements for failed cycle
                for candidate in candidates:
                    fallback_improvement = {
                        'candidate_id': candidate.get('task_id', 'unknown'),
                        'error': f"D-REAM cycle failed: {cycle_result.status}",
                        'evidence': 'dream_cycle_failure',
                        'type': 'fallback'
                    }
                    improvements.append(fallback_improvement)

        except Exception as e:
            print(f"[dream] ❌ Complete D-REAM system failed: {e}")
            # Fallback to simple improvements for these candidates
            for candidate in candidates:
                fallback_improvement = {
                    'candidate_id': candidate.get('task_id', 'unknown'),
                    'error': str(e),
                    'evidence': 'dream_system_fallback',
                    'type': 'fallback'
                }
                improvements.append(fallback_improvement)
        
        return improvements

    def process_kloros_approval_response(self, response: str) -> Dict[str, Any]:
        """Process KLoROS approval response for evolutionary improvements."""
        try:
            if hasattr(self, 'dream_system') and self.dream_system:
                print(f"[dream] 📝 Processing KLoROS approval response: {response}")

                # Forward to complete D-REAM system
                result = self.dream_system.process_kloros_approval_response(response)

                if result.get("ready_for_deployment"):
                    print(f"[dream] 🚀 Evolutionary improvement approved and deployed!")
                elif result.get("action") == "declined":
                    print(f"[dream] ❌ Evolutionary improvement declined by KLoROS")
                elif result.get("action") == "details_provided":
                    print(f"[dream] 📊 Detailed information provided to KLoROS")

                return result
            else:
                return {"error": "No D-REAM system available for approval processing"}

        except Exception as e:
            print(f"[dream] ❌ Failed to process approval response: {e}")
            return {"error": str(e)}

    def get_pending_evolutionary_approvals(self) -> List[str]:
        """Get list of pending evolutionary approval requests."""
        if hasattr(self, 'pending_evolutionary_approvals'):
            return self.pending_evolutionary_approvals
        return []

    def has_pending_evolutionary_approvals(self) -> bool:
        """Check if there are pending evolutionary approvals."""
        return len(self.get_pending_evolutionary_approvals()) > 0
    def _generate_recommendations(self, task: Dict[str, Any]) -> List[Dict[str, Any]]:
        """Generate intelligent parameter recommendations based on task evidence."""
        component = task.get("component", "system")
        priority = task.get("priority", 5)
        evidence = task.get("evidence", "unknown")
        details = task.get("details", {})

        recommendations = []

        if component == "audio":
            # Intelligent audio recommendations based on evidence
            current_gain = float(os.getenv("KLR_INPUT_GAIN", "4.5"))

            if "false_positive" in evidence or "wake_word" in task.get("text", "").lower():
                # Reduce sensitivity for false positives
                recommendations.append({
                    "parameter": "KLR_VAD_THRESHOLD",
                    "current_value": float(os.getenv("KLR_VAD_THRESHOLD", "0.5")),
                    "recommended_value": min(0.8, float(os.getenv("KLR_VAD_THRESHOLD", "0.5")) + 0.1),
                    "reason": f"Reduce false positives (evidence: {evidence})"
                })
            elif "silence" in evidence or "sensitivity" in task.get("text", "").lower():
                # Increase gain for silence issues
                recommendations.append({
                    "parameter": "KLR_INPUT_GAIN",
                    "current_value": current_gain,
                    "recommended_value": min(8.0, current_gain + 0.5),
                    "reason": f"Improve audio sensitivity for silence detection (evidence: {evidence})"
                })
            else:
                # Default audio optimization
                recommendations.append({
                    "parameter": "KLR_INPUT_GAIN",
                    "current_value": current_gain,
                    "recommended_value": min(8.0, current_gain + 0.3),
                    "reason": f"Improve audio input quality (evidence: {evidence})"
                })

        elif component == "memory":
            # Intelligent memory recommendations
            current_events = int(os.getenv("KLR_MAX_CONTEXT_EVENTS", "8"))

            if priority > 7:  # High priority memory issues
                recommendations.append({
                    "parameter": "KLR_MAX_CONTEXT_EVENTS",
                    "current_value": current_events,
                    "recommended_value": max(3, current_events - 2),
                    "reason": f"Optimize memory retrieval speed for high-priority issue (evidence: {evidence})"
                })
            else:
                recommendations.append({
                    "parameter": "KLR_MAX_CONTEXT_EVENTS",
                    "current_value": current_events,
                    "recommended_value": max(3, current_events - 1),
                    "reason": f"Optimize memory retrieval performance (evidence: {evidence})"
                })

        elif component == "conversation":
            # Conversation flow optimizations
            current_timeout = int(os.getenv("KLR_CONVERSATION_TIMEOUT", "15"))
            recommendations.append({
                "parameter": "KLR_CONVERSATION_TIMEOUT",
                "current_value": current_timeout,
                "recommended_value": min(30, current_timeout + 5),
                "reason": f"Improve conversation flow stability (evidence: {evidence})"
            })

        return recommendations

    def get_evolution_summary(self) -> Dict[str, Any]:
        """Get evolution system status."""
        # Check current environment state dynamically
        evolution_enabled = int(os.getenv("KLR_ENABLE_DREAM_EVOLUTION", "0"))
        evolution_interval = int(os.getenv("KLR_DREAM_EVOLUTION_INTERVAL", "3600"))
        return {
            "evolution_enabled": evolution_enabled,
            "last_evolution": self.last_evolution_time,
            "next_evolution_in": max(0, evolution_interval - (time.time() - self.last_evolution_time)),
            "intelligent_analysis": True
        }

class KLoROSMemoryAdapter:
    """Intelligent adapter for KLoROS memory system integration using real performance data."""

    def __init__(self):
        self.memory_available = KLOROS_MEMORY_AVAILABLE
        self.reflection_log_path = "/home/kloros/.kloros/reflection.log"
        self.memory_db_path = "/home/kloros/.kloros/memory.db"

    def get_operational_tasks(self, lookback_hours: int = 24) -> List[Dict[str, Any]]:
        """Generate intelligent operational improvement tasks based on real performance data."""
        tasks = []

        print("[dream] Analyzing reflection insights for optimization opportunities...")
        # Analyze reflection insights for optimization opportunities
        reflection_tasks = self._analyze_reflection_insights(lookback_hours)
        tasks.extend(reflection_tasks)

        print("[dream] Analyzing episodic memory for performance patterns...")
        # Analyze episodic memory for performance patterns
        memory_tasks = self._analyze_memory_performance(lookback_hours)
        tasks.extend(memory_tasks)

        print("[dream] Analyzing conversation patterns for user experience improvements...")
        # Analyze conversation patterns for user experience improvements
        conversation_tasks = self._analyze_conversation_patterns(lookback_hours)
        tasks.extend(conversation_tasks)
        
        print("[dream] Adding tool synthesis evolution candidates for background optimization...")
        # Add tool synthesis improvement candidates for continuous evolution
        tool_synthesis_candidates = self._get_tool_synthesis_candidates()
        tasks.extend(tool_synthesis_candidates)

        # If no intelligent tasks found, provide baseline optimizations
        if not tasks:
            print("[dream] No specific issues detected - providing baseline optimizations")
            tasks = self._get_baseline_tasks()

        # Sort by priority and return top tasks
        tasks.sort(key=lambda x: x.get("priority", 0), reverse=True)
        return tasks[:5]  # Limit to top 5 most important tasks

    def _analyze_reflection_insights(self, lookback_hours: int) -> List[Dict[str, Any]]:
        """Analyze recent reflection logs for optimization opportunities."""
        tasks = []
        detected_issues_this_cycle = set()

        try:
            # Look for recent reflection entries with specific optimization signals
            reflection_data = self._get_recent_reflection_data(lookback_hours)
            print(f"[dream] Analyzing {len(reflection_data)} recent reflection entries")

            for entry in reflection_data:
                # Check for audio quality issues
                if self._detect_audio_issues(entry):
                    issue_fingerprint = "audio_quality"
                    if issue_fingerprint not in detected_issues_this_cycle:
                        detected_issues_this_cycle.add(issue_fingerprint)
                        tasks.append({
                            "task_id": f"audio_quality_fix_{int(time.time())}",
                            "text": "Address audio quality issues detected in reflection analysis",
                            "component": "audio",
                            "priority": 8,
                            "evidence": "reflection_analysis",
                            "details": self._extract_audio_issue_details(entry)
                        })
                        print("[dream] Found audio quality issue in reflection data")

                # Check for memory performance issues
                if self._detect_memory_issues(entry):
                    issue_fingerprint = "memory_performance"
                    if issue_fingerprint not in detected_issues_this_cycle:
                        detected_issues_this_cycle.add(issue_fingerprint)
                        tasks.append({
                            "task_id": f"memory_optimization_{int(time.time())}",
                            "text": "Optimize memory system based on performance patterns",
                            "component": "memory",
                            "priority": 7,
                            "evidence": "reflection_analysis",
                            "details": self._extract_memory_issue_details(entry)
                        })
                        print("[dream] Found memory performance issue in reflection data")

                # Check for conversation flow issues
                if self._detect_conversation_issues(entry):
                    issue_fingerprint = "conversation_flow"
                    if issue_fingerprint not in detected_issues_this_cycle:
                        detected_issues_this_cycle.add(issue_fingerprint)
                        tasks.append({
                            "task_id": f"conversation_flow_{int(time.time())}",
                            "text": "Improve conversation flow based on interaction patterns",
                            "component": "conversation",
                            "priority": 6,
                            "evidence": "reflection_analysis",
                            "details": self._extract_conversation_issue_details(entry)
                        })
                        print("[dream] Found conversation flow issue in reflection data")

            if detected_issues_this_cycle:
                print(f"[dream] Deduplication: Found {len(detected_issues_this_cycle)} unique issues from {len(reflection_data)} entries")

        except Exception as e:
            print(f"[dream] Reflection analysis error: {e}")

        return tasks

    def _analyze_memory_performance(self, lookback_hours: int) -> List[Dict[str, Any]]:
        """Analyze episodic memory database for performance patterns."""
        tasks = []

        if not self.memory_available:
            print("[dream] Memory system not available for analysis")
            return tasks

        try:
            import sqlite3
            from datetime import datetime, timedelta

            since_time = (datetime.now() - timedelta(hours=lookback_hours)).timestamp()

            conn = sqlite3.connect(self.memory_db_path, timeout=5.0)
            cursor = conn.cursor()

            # Analyze wake word detection accuracy
            cursor.execute("""
                SELECT content, metadata FROM events
                WHERE event_type = 'wake_detected' AND timestamp > ?
                ORDER BY timestamp DESC LIMIT 20
            """, (since_time,))

            wake_events = cursor.fetchall()
            if len(wake_events) > 5:
                false_positives = sum(1 for event in wake_events if 'false' in event[0].lower() or 'error' in event[0].lower())
                false_positive_rate = false_positives / len(wake_events)

                if false_positive_rate > 0.2:  # >20% false positive rate
                    tasks.append({
                        "task_id": f"wake_word_tuning_{int(time.time())}",
                        "text": f"Reduce wake word false positives (current rate: {false_positives}/{len(wake_events)})",
                        "component": "audio",
                        "priority": 9,
                        "evidence": "memory_analysis",
                        "details": {"false_positive_rate": false_positive_rate, "sample_size": len(wake_events)}
                    })
                    print(f"[dream] High false positive rate detected: {false_positive_rate:.2f}")

            # Analyze conversation patterns for timeout/silence issues
            cursor.execute("""
                SELECT content FROM events
                WHERE event_type = 'llm_response' AND timestamp > ?
                AND (content LIKE '%no vocal input%' OR content LIKE '%silence%' OR content LIKE '%not receiving%')
                ORDER BY timestamp DESC LIMIT 10
            """, (since_time,))

            silence_events = cursor.fetchall()
            if len(silence_events) > 3:
                tasks.append({
                    "task_id": f"audio_sensitivity_{int(time.time())}",
                    "text": f"Improve audio input sensitivity - {len(silence_events)} silence events detected",
                    "component": "audio",
                    "priority": 8,
                    "evidence": "memory_analysis",
                    "details": {"silence_event_count": len(silence_events)}
                })
                print(f"[dream] Multiple silence events detected: {len(silence_events)}")

            # Analyze conversation completion rates
            cursor.execute("""
                SELECT COUNT(CASE WHEN event_type = 'conversation_start' THEN 1 END) as starts,
                       COUNT(CASE WHEN event_type = 'conversation_end' THEN 1 END) as ends
                FROM events
                WHERE timestamp > ?
            """, (since_time,))

            conversation_stats = cursor.fetchone()
            if conversation_stats and conversation_stats[0] > 0:
                starts, ends = conversation_stats
                completion_rate = ends / starts if starts > 0 else 0

                if completion_rate < 0.8 and starts > 3:  # Less than 80% completion rate
                    tasks.append({
                        "task_id": f"conversation_stability_{int(time.time())}",
                        "text": f"Improve conversation completion rate ({ends}/{starts} = {completion_rate:.2f})",
                        "component": "conversation",
                        "priority": 7,
                        "evidence": "memory_analysis",
                        "details": {"completion_rate": completion_rate, "starts": starts, "ends": ends}
                    })
                    print(f"[dream] Low conversation completion rate: {completion_rate:.2f}")

            conn.close()

        except Exception as e:
            print(f"[dream] Memory analysis error: {e}")

        return tasks

    def _analyze_conversation_patterns(self, lookback_hours: int) -> List[Dict[str, Any]]:
        """Analyze conversation patterns for user experience improvements."""
        tasks = []

        if not self.memory_available:
            return tasks
        
        # Add basic conversation pattern analysis
        # TODO: Implement conversation pattern detection
        return tasks
    def _get_tool_synthesis_candidates(self) -> List[Dict[str, Any]]:
        """Get predefined tool synthesis improvement candidates for D-REAM evolution.
        
        These are complex optimization challenges identified during tool synthesis
        analysis that require evolutionary approaches rather than direct implementation.
        """
        candidates = []
        
        # High Priority: Memory Context Integration
        candidates.append({
            'task_id': 'memory_context_integration',
            'text': 'Optimize memory context integration architecture for standalone chat',
            'component': 'memory',
            'priority': 9,  # High priority
            'evidence': 'tool_synthesis_analysis', 
            'details': {
                'challenge': 'Standalone chat bypasses memory-enhanced wrapper',
                'impact': 'High - Enhanced conversational capabilities',
                'approaches': ['wrapper_integration', 'direct_injection', 'hybrid_approach', 'context_caching'],
                'success_metrics': ['context_relevance_score', 'response_latency', 'conversation_continuity'],
                'spec_file': '/home/kloros/d_ream_candidates/memory_context_integration.md'
            }
        })
        
        # High Priority: LLM Tool Generation Consistency  
        candidates.append({
            'task_id': 'llm_tool_generation_consistency',
            'text': 'Evolve LLM prompt engineering for consistent tool name generation',
            'component': 'reasoning',
            'priority': 8,  # High priority
            'evidence': 'tool_synthesis_analysis',
            'details': {
                'challenge': 'LLM generates inconsistent tool names across contexts',
                'impact': 'Medium-High - Reduce 20% failure rate to <5%',
                'approaches': ['constraint_prompts', 'example_injection', 'template_enforcement', 'feedback_learning'],
                'success_metrics': ['tool_name_consistency', 'mapping_success_rate', 'natural_language_preservation'],
                'spec_file': '/home/kloros/d_ream_candidates/llm_tool_generation_consistency.md'
            }
        })
        
        # Medium Priority: RAG Example Quality Enhancement
        candidates.append({
            'task_id': 'rag_example_quality_enhancement', 
            'text': 'Optimize RAG example curation for improved tool synthesis guidance',
            'component': 'reasoning',
            'priority': 6,  # Medium priority
            'evidence': 'tool_synthesis_analysis',
            'details': {
                'challenge': 'RAG examples lack sufficient tool synthesis guidance',
                'impact': 'Medium - Improved consistency through better examples',
                'approaches': ['curated_examples', 'dynamic_injection', 'hybrid_retrieval', 'context_weighting'],
                'success_metrics': ['tool_generation_consistency', 'personality_preservation', 'retrieval_relevance'],
                'spec_file': '/home/kloros/d_ream_candidates/rag_example_quality_enhancement.md'
            }
        })
        
        # Low Priority: Conversational Boundary Detection
        candidates.append({
            'task_id': 'conversational_boundary_detection',
            'text': 'Enhance query classification for ambiguous conversation/tool boundaries',
            'component': 'reasoning', 
            'priority': 4,  # Lower priority (95%+ already working)
            'evidence': 'tool_synthesis_analysis',
            'details': {
                'challenge': 'Edge cases in conversational vs tool intent classification',
                'impact': 'Low-Medium - Handle edge cases more gracefully',
                'approaches': ['enhanced_heuristics', 'ml_classification', 'intent_detection', 'context_analysis'],
                'success_metrics': ['classification_accuracy', 'edge_case_handling', 'false_positive_rate'],
                'spec_file': '/home/kloros/d_ream_candidates/conversational_boundary_detection.md'
            }
        })
        
        # Filter candidates based on configuration
        enabled_candidates = []
        
        # Check individual candidate enablement
        candidate_configs = {
            'memory_context_integration': int(os.getenv('KLR_MEMORY_INTEGRATION_EVOLUTION', '1')),
            'llm_tool_generation_consistency': int(os.getenv('KLR_LLM_CONSISTENCY_EVOLUTION', '1')), 
            'rag_example_quality_enhancement': int(os.getenv('KLR_RAG_QUALITY_EVOLUTION', '1')),
            'conversational_boundary_detection': int(os.getenv('KLR_BOUNDARY_DETECTION_EVOLUTION', '0'))
        }
        
        priority_threshold = int(os.getenv('KLR_TOOL_SYNTHESIS_PRIORITY_THRESHOLD', '6'))
        
        for candidate in candidates:
            task_id = candidate['task_id']
            priority = candidate['priority']
            
            # Check if candidate is enabled and meets priority threshold
            if (candidate_configs.get(task_id, 0) and 
                priority >= priority_threshold):
                enabled_candidates.append(candidate)
                print(f'[dream] Enabled tool synthesis candidate: {task_id} (priority: {priority})')
        
        print(f'[dream] Generated {len(enabled_candidates)}/{len(candidates)} enabled tool synthesis candidates')
        return enabled_candidates


        try:
            import sqlite3
            from datetime import datetime, timedelta

            since_time = (datetime.now() - timedelta(hours=lookback_hours)).timestamp()

            conn = sqlite3.connect(self.memory_db_path, timeout=5.0)
            cursor = conn.cursor()

            # Analyze response times and conversation quality
            cursor.execute("""
                SELECT event_type, COUNT(*) as count
                FROM events
                WHERE timestamp > ?
                GROUP BY event_type
                ORDER BY count DESC
            """, (since_time,))

            event_counts = dict(cursor.fetchall())

            # Check for error patterns
            error_count = event_counts.get('error', 0)
            total_events = sum(event_counts.values())

            if error_count > 0 and total_events > 10:
                error_rate = error_count / total_events
                if error_rate > 0.1:  # More than 10% error rate
                    tasks.append({
                        "task_id": f"error_reduction_{int(time.time())}",
                        "text": f"Reduce system error rate ({error_count}/{total_events} = {error_rate:.2f})",
                        "component": "system",
                        "priority": 9,
                        "evidence": "pattern_analysis",
                        "details": {"error_rate": error_rate, "error_count": error_count, "total_events": total_events}
                    })
                    print(f"[dream] High error rate detected: {error_rate:.2f}")

            conn.close()

        except Exception as e:
            print(f"[dream] Conversation analysis error: {e}")

        return tasks

    def _get_recent_reflection_data(self, lookback_hours: int) -> List[Dict[str, Any]]:
        """Extract recent reflection data for analysis."""
        reflection_entries = []

        try:
            from datetime import datetime, timedelta
            import json

            cutoff_time = datetime.now() - timedelta(hours=lookback_hours)

            with open(self.reflection_log_path, 'r') as f:
                content = f.read()

            # Split by delimiter and parse JSON entries
            entries = content.split('---\n')
            for entry in entries[-10:]:  # Look at last 10 entries
                entry = entry.strip()
                if entry:
                    try:
                        data = json.loads(entry)
                        entry_time = datetime.fromisoformat(data.get('timestamp', '1970-01-01T00:00:00'))
                        if entry_time > cutoff_time:
                            reflection_entries.append(data)
                    except:
                        continue

        except Exception as e:
            print(f"[dream] Reflection data parsing error: {e}")

        return reflection_entries

    def _detect_audio_issues(self, reflection_entry: Dict[str, Any]) -> bool:
        """Detect audio-related issues in reflection data."""
        content_str = str(reflection_entry).lower()
        audio_issues = ['audio quality', 'poor quality', 'low volume', 'noise', 'distortion', 'gain', 'microphone', 'input']
        return any(issue in content_str for issue in audio_issues)

    def _detect_memory_issues(self, reflection_entry: Dict[str, Any]) -> bool:
        """Detect memory-related issues in reflection data."""
        content_str = str(reflection_entry).lower()
        memory_issues = ['slow retrieval', 'memory', 'performance', 'database', 'context', 'lag', 'timeout']
        return any(issue in content_str for issue in memory_issues)

    def _detect_conversation_issues(self, reflection_entry: Dict[str, Any]) -> bool:
        """Detect conversation flow issues in reflection data."""
        content_str = str(reflection_entry).lower()
        conversation_issues = ['timeout', 'response time', 'flow', 'interruption', 'silence', 'hang', 'stuck']
        return any(issue in content_str for issue in conversation_issues)

    def _extract_audio_issue_details(self, reflection_entry: Dict[str, Any]) -> Dict[str, Any]:
        """Extract specific details about audio issues."""
        return {"source": "reflection", "type": "audio_quality", "timestamp": reflection_entry.get("timestamp")}

    def _extract_memory_issue_details(self, reflection_entry: Dict[str, Any]) -> Dict[str, Any]:
        """Extract specific details about memory issues."""
        return {"source": "reflection", "type": "memory_performance", "timestamp": reflection_entry.get("timestamp")}

    def _extract_conversation_issue_details(self, reflection_entry: Dict[str, Any]) -> Dict[str, Any]:
        """Extract specific details about conversation issues."""
        return {"source": "reflection", "type": "conversation_flow", "timestamp": reflection_entry.get("timestamp")}

    def _get_baseline_tasks(self) -> List[Dict[str, Any]]:
        """Provide baseline optimization tasks when no specific issues detected."""
        return [
            {
                "task_id": f"proactive_audio_optimization_{int(time.time())}",
                "text": "Proactive audio input gain optimization for speech recognition quality",
                "component": "audio",
                "priority": 3,
                "evidence": "baseline_optimization"
            },
            {
                "task_id": f"proactive_memory_tuning_{int(time.time())}",
                "text": "Proactive memory context parameter tuning for retrieval efficiency",
                "component": "memory",
                "priority": 2,
                "evidence": "baseline_optimization"
            }
        ]

class SafetyGateSystem:
    """Enhanced safety gate system for evolution validation."""

    def __init__(self):
        self.safe_parameters = {
            "KLR_INPUT_GAIN": (0.5, 8.0),
            "KLR_VAD_THRESHOLD": (0.1, 0.9),
            "KLR_MAX_CONTEXT_EVENTS": (1, 50),
            "KLR_CONVERSATION_TIMEOUT": (5, 60)
        }

    def validate_candidate_safety(self, candidate: Dict[str, Any]) -> Tuple[bool, str]:
        """Validate candidate safety with enhanced checks."""
        try:
            recommendations = candidate.get("parameter_recommendations", [])
            for rec in recommendations:
                param = rec.get("parameter", "")
                new_value = rec.get("recommended_value")

                if param in self.safe_parameters:
                    min_val, max_val = self.safe_parameters[param]
                    if not (min_val <= new_value <= max_val):
                        return False, f"value_out_of_range: {param} ({new_value} not in [{min_val}, {max_val}])"

                # Additional safety check for evidence-based recommendations
                evidence = candidate.get("evidence", "unknown")
                if evidence == "unknown":
                    return False, "no_evidence_provided"

            return True, "safe"
        except Exception as e:
            return False, f"validation_error: {e}"

class KLoROSComponentTrainer:
    """Enhanced component trainer for applying intelligent improvements."""

    def apply_improvement(self, candidate: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        """Apply an improvement candidate with enhanced logging."""
        try:
            recommendations = candidate.get("parameter_recommendations", [])
            for rec in recommendations:
                param = rec.get("parameter", "")
                new_value = rec.get("recommended_value")
                current_value = rec.get("current_value")

                # Update environment variable
                success = self._update_parameter(param, str(new_value))
                if success:
                    return {
                        "parameter": param,
                        "old_value": current_value,
                        "new_value": new_value,
                        "reason": rec.get("reason", "optimization"),
                        "task_id": candidate.get("task_id", "unknown")
                    }
            return None
        except Exception as e:
            print(f"[dream] Component trainer error: {e}")
            return None

    def _update_parameter(self, param: str, value: str) -> bool:
        """Update parameter in .kloros_env file."""
        try:
            env_file = "/home/kloros/.kloros_env"
            if os.path.exists(env_file):
                with open(env_file, 'r') as f:
                    lines = f.readlines()
            else:
                lines = []

            # Update or add parameter
            updated = False
            for i, line in enumerate(lines):
                if line.strip().startswith(f"{param}="):
                    lines[i] = f"{param}={value}\n"
                    updated = True
                    break

            if not updated:
                lines.append(f"{param}={value}\n")

            # Write back
            with open(env_file, 'w') as f:
                f.writelines(lines)

            os.environ[param] = value
            return True
        except Exception as e:
            print(f"[dream] Parameter update error: {e}")
            return False

class DreamIdleIntegration:
    """Enhanced integration with KLoROS idle reflection system."""

    def __init__(self, kloros_instance=None):
        self.kloros = kloros_instance
        self.evolution_manager = DreamEvolutionManager()

        # Initialize improvement proposer and bridge
        try:
            sys.path.insert(0, '/home/kloros')
            from src.dream.improvement_proposer import get_improvement_proposer
            from src.dream.proposal_to_candidate_bridge import get_proposal_bridge
            self.improvement_proposer = get_improvement_proposer()
            self.proposal_bridge = get_proposal_bridge()
            self.proposer_enabled = True
            print("[dream] Improvement proposer integrated with idle reflection")
        except Exception as e:
            print(f"[dream] Failed to initialize improvement proposer: {e}")
            self.proposer_enabled = False

    def should_perform_evolution(self) -> bool:
        """Check if evolution should be performed."""
        return self.evolution_manager.should_evolve()

    def perform_evolutionary_reflection(self) -> Dict[str, Any]:
        """Perform intelligent evolution as part of idle reflection."""
        # Check maintenance mode before running reflection
        if is_maintenance_mode():
            print("[dream] Skipping evolutionary reflection - system in maintenance mode")
            return {
                "type": "evolutionary_reflection",
                "timestamp": datetime.now().isoformat(),
                "success": False,
                "intelligent_analysis": True,
                "proposals_submitted": 0,
                "tools_submitted": 0,
                "skipped": "maintenance_mode"
            }

        result = {
            "type": "evolutionary_reflection",
            "timestamp": datetime.now().isoformat(),
            "success": False,
            "intelligent_analysis": True,
            "proposals_submitted": 0,
            "tools_submitted": 0
        }

        try:
            # STEP 1: Process tool synthesis queue (PATHWAY 1)
            # NOTE: Tool synthesis bridge disabled - module does not exist yet
            # TODO: Implement src.dream.tool_synthesis_to_dream_bridge when ready
            # try:
            #     from src.dream.tool_synthesis_to_dream_bridge import ToolSynthesisToDreamBridge
            #
            #     tool_bridge = ToolSynthesisToDreamBridge()
            #     tool_result = tool_bridge.process_queue()
            #
            #     if tool_result['submitted_to_dream'] > 0:
            #         print(f"[dream] 🔧 Processed {tool_result['submitted_to_dream']} synthesized tools from queue")
            #         result["tools_submitted"] = tool_result['submitted_to_dream']
            #
            # except Exception as e:
            #     print(f"[dream] ⚠️ Tool synthesis bridge error: {e}")

            # STEP 2: Run improvement proposer to detect runtime issues (PATHWAY 2)
            if self.proposer_enabled:
                try:
                    proposals_submitted = self.improvement_proposer.run_analysis_cycle()
                    result["proposals_submitted"] = proposals_submitted

                    if proposals_submitted > 0:
                        print(f"[dream] 🔍 Detected {proposals_submitted} runtime issues, forwarding to D-REAM")

                        # Convert proposals to D-REAM candidates
                        pending_proposals = self.improvement_proposer.get_pending_proposals()
                        if pending_proposals:
                            candidates_submitted = self.proposal_bridge.submit_proposals_as_candidates(
                                [p.__dict__ for p in pending_proposals]
                            )
                            result["candidates_submitted"] = candidates_submitted
                            print(f"[dream] ✅ Submitted {candidates_submitted} proposals as D-REAM candidates")

                except Exception as e:
                    print(f"[dream] ⚠️ Improvement proposer error: {e}")

            # STEP 3: Run standard evolution cycle
            evolution_result = self.evolution_manager.run_evolution_cycle()
            result["evolution_cycle"] = evolution_result
            result["success"] = evolution_result.get("success", False)

            if result["success"]:
                improvements = evolution_result.get("improvements_applied", [])
                tasks_analyzed = evolution_result.get("tasks_analyzed", 0)
                result["insights"] = [
                    f"Applied {len(improvements)} autonomous improvements from {tasks_analyzed} performance issues analyzed",
                    "Improvements based on real reflection data and memory patterns"
                ]

                if result["proposals_submitted"] > 0:
                    result["insights"].insert(0, f"Detected and forwarded {result['proposals_submitted']} runtime issues to D-REAM queue")

                for improvement in improvements:
                    param = improvement.get("parameter", "unknown")
                    new_val = improvement.get("new_value", "unknown")
                    evidence = improvement.get("evidence", "unknown")
                    result["insights"].append(f"- {param} = {new_val} (evidence: {evidence})")
            else:
                result["insights"] = ["Evolution cycle completed - system performance optimal, no improvements needed"]

                if result["proposals_submitted"] > 0:
                    result["insights"].insert(0, f"Detected and forwarded {result['proposals_submitted']} runtime issues to D-REAM queue")

        except Exception as e:
            result["error"] = str(e)
            result["insights"] = [f"Evolution system monitoring: {str(e)[:100]}"]

        return result

# Test function
def test_dream_system():
    """Test enhanced D-REAM system."""
    try:
        dream = DreamEvolutionManager()
        status = dream.get_evolution_summary()
        print(f"[test] Enhanced D-REAM system ready - enabled: {status['evolution_enabled']}")
        print(f"[test] Intelligent analysis: {status.get('intelligent_analysis', False)}")
        return True
    except Exception as e:
        print(f"[test] Enhanced D-REAM test failed: {e}")
        return False

if __name__ == "__main__":
    test_dream_system()