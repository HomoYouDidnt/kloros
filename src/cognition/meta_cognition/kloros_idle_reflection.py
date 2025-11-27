"""
Idle reflection routines for KLoROS self-analysis during quiet periods.

Enhanced version with progressive analytical layers for genuine self-awareness.
"""

import time
import json
import os
import threading
from datetime import datetime, timedelta
from typing import Dict, Any, Optional

# D-REAM Evolution System Integration
try:
    from src.dream_evolution_system import DreamIdleIntegration
    DREAM_AVAILABLE = True
    print("[reflection] D-REAM evolution system available")
except ImportError as e:
    DREAM_AVAILABLE = False
    print(f"[reflection] D-REAM evolution system not available: {e}")

# Try to import enhanced reflection system
try:
    from src.idle_reflection import EnhancedIdleReflectionManager, get_config
    ENHANCED_AVAILABLE = True
    print("[reflection] Enhanced reflection system available")
except ImportError as e:
    ENHANCED_AVAILABLE = False
    print(f"[reflection] Enhanced reflection system not available: {e}")
    print("[reflection] Falling back to basic reflection system")

class IdleReflectionManager:
    """Manages periodic self-reflection during idle periods."""

    def __init__(self, kloros_instance):
        self.kloros = kloros_instance

        # Check if memory system is enabled - if not, disable reflection completely
        self.memory_enabled = int(os.getenv("KLR_ENABLE_MEMORY", "1"))

        if not self.memory_enabled:
            print("[reflection] KLR_ENABLE_MEMORY=0, reflection system disabled")
            self.use_enhanced = False
            self.enhanced_manager = None
            self.reflection_interval = 60 * 10
            self.reflection_log_path = "/home/kloros/.kloros/reflection.log"
            self.last_reflection_time = time.time()
            return

        # Initialize enhanced reflection if available
        if ENHANCED_AVAILABLE:
            try:
                self.enhanced_manager = EnhancedIdleReflectionManager(kloros_instance)
                self.config = get_config()
                self.reflection_interval = self.config.reflection_interval
                self.reflection_log_path = self.config.reflection_log_path
                self.use_enhanced = True
                print(f"[reflection] Enhanced reflection initialized - depth: {self.config.reflection_depth}")
            except Exception as e:
                print(f"[reflection] Enhanced reflection initialization failed: {e}")
                self.use_enhanced = False
                self._init_basic_reflection()
        else:
            self.use_enhanced = False
            self._init_basic_reflection()

        self.last_reflection_time = time.time()  # Initialize to current time, not 0

        # Initialize D-REAM Evolution System Integration
        self.dream_enabled = int(os.getenv("KLR_ENABLE_DREAM_EVOLUTION", "0"))
        if self.dream_enabled and DREAM_AVAILABLE:
            try:
                self.dream_integration = DreamIdleIntegration(kloros_instance)
                print("[reflection] D-REAM evolution system integrated")
            except Exception as e:
                print(f"[reflection] D-REAM integration failed: {e}")
                self.dream_integration = None
        else:
            self.dream_integration = None
            if self.dream_enabled and not DREAM_AVAILABLE:
                print("[reflection] D-REAM enabled but system not available")

        # Component Self-Study system (NEW - continuous learning)
        self.self_study_enabled = int(os.getenv("KLR_ENABLE_SELF_STUDY", "1"))
        self.self_study = None
        if self.self_study_enabled:
            try:
                from src.component_self_study import ComponentSelfStudy
                self.self_study = ComponentSelfStudy(kloros_instance=kloros_instance)
                print("[reflection] Component self-study system enabled")
            except Exception as e:
                print(f"[reflection] Self-study system not available: {e}")
                self.self_study_enabled = False

    def _init_basic_reflection(self):
        """Initialize basic reflection system as fallback."""
        self.reflection_interval = 60 * 10  # 10 minutes
        self.reflection_log_path = "/home/kloros/.kloros/reflection.log"
        self.enhanced_manager = None
        print("[reflection] Basic reflection system initialized")

    def should_reflect(self) -> bool:
        """Check if it's time for idle reflection."""
        # If memory disabled, never reflect
        if not self.memory_enabled:
            return False

        if self.use_enhanced and self.enhanced_manager:
            return self.enhanced_manager.should_reflect()
        else:
            current_time = time.time()
            return (current_time - self.last_reflection_time) >= self.reflection_interval

    def perform_reflection(self) -> None:
        """Perform idle reflection analysis."""
        if not self.should_reflect():
            return

        if self.use_enhanced and self.enhanced_manager:
            self._perform_enhanced_reflection()
        else:
            self._perform_basic_reflection()

    def _perform_enhanced_reflection(self) -> None:
        """Perform enhanced multi-phase reflection analysis."""
        # Monitor exceptions in reflection system for self-awareness
        from src.runtime_exception_bridge import get_exception_bridge
        exception_bridge = get_exception_bridge()

        # Update consciousness in REST MODE - reflection does not accumulate fatigue
        from src.consciousness import update_consciousness_resting
        update_consciousness_resting(self.kloros)

        try:
            print("[reflection] Starting enhanced multi-phase self-analysis...")
            summary = self.enhanced_manager.perform_enhanced_reflection()

            if summary:
                print(f"[reflection] Enhanced analysis complete: {summary.insights_generated} insights generated")
                print(f"[reflection] Phases completed: {summary.analysis_depth}/4")

                if summary.top_insights:
                    print(f"[reflection] Top insight: {summary.top_insights[0]}")

                # Surface insights to user via alert system (NEW)
                self._surface_insights_to_user(summary)

            # Enrich improvement proposals with solutions (NEW)
            # Generate concrete solutions for pending proposals using deep reasoning
            self._enrich_improvement_proposals()

            # Chaos testing for self-healing validation (runs in enhanced mode too!)
            # Run every 5th reflection cycle
            if hasattr(self.kloros, 'chaos') and self.kloros.chaos:
                if not hasattr(self, '_chaos_counter'):
                    self._chaos_counter = 0
                self._chaos_counter += 1

                print(f"[reflection] Chaos counter: {self._chaos_counter}/5")

                if self._chaos_counter % 5 == 0:
                    try:
                        print("[reflection] Phase 5: Chaos testing (self-healing validation)...")
                        self._run_autonomous_chaos_test()
                    except Exception as e:
                        print(f"[reflection] Chaos testing failed: {e}")
                        import traceback
                        traceback.print_exc()

            self.last_reflection_time = time.time()

            # D-REAM Evolutionary Analysis (added to enhanced mode)
            if self.dream_enabled and self.dream_integration and self.dream_integration.should_perform_evolution():
                try:
                    print("[reflection] Performing D-REAM evolutionary analysis...")
                    evolution_result = self.dream_integration.perform_evolutionary_reflection()

                    if evolution_result.get("success"):
                        improvements = evolution_result.get("evolution_cycle", {}).get("improvements_applied", [])
                        if improvements:
                            print(f"[reflection] D-REAM applied {len(improvements)} autonomous improvements")
                            for improvement in improvements:
                                param = improvement.get("parameter", "unknown")
                                new_val = improvement.get("new_value", "unknown")
                                reason = improvement.get("reason", "optimization")
                                print(f"[reflection] - {param} = {new_val} ({reason})")
                        else:
                            print("[reflection] D-REAM evolution cycle completed - monitoring for opportunities")
                    else:
                        print("[reflection] D-REAM evolution cycle completed with challenges")

                except Exception as e:
                    print(f"[reflection] D-REAM evolution failed: {e}")

            # Phase 6: Component Self-Study (NEW - continuous learning)
            try:
                if hasattr(self, 'self_study') and self.self_study:
                    print("[reflection] Phase 6: Component self-study...")
                    study_result = self.self_study.perform_study_cycle()

                    if study_result.get("status") == "completed":
                        component = study_result.get("component_id", "unknown")
                        depth = study_result.get("study_depth", 0)
                        improvements = study_result.get("improvements_found", 0)

                        print(f"[reflection] Studied {component} (depth {depth}/3)")
                        if improvements > 0:
                            print(f"[reflection] Found {improvements} improvement opportunities")

                        # Queue self-study insight for presentation
                        if study_result.get("insight"):
                            self._surface_self_study_insight(study_result["insight"])

            except Exception as e:
                print(f"[reflection] Self-study failed: {e}")

            # Phase 7: Capability-Driven Curiosity (ASYNC - prevent watchdog timeout)
            try:
                print("[reflection] Phase 7: Capability-driven curiosity...")
                curiosity_enabled = int(os.getenv("KLR_ENABLE_CURIOSITY", "1"))

                if curiosity_enabled:
                    # Launch curiosity cycle in background thread to avoid blocking watchdog
                    # This prevents the main thread from freezing during network requests
                    curiosity_thread = threading.Thread(
                        target=self._perform_capability_curiosity_cycle_async,
                        daemon=True,
                        name="curiosity-cycle"
                    )
                    curiosity_thread.start()
                    print("[reflection] Curiosity cycle launched (async, non-blocking)")
                else:
                    print("[reflection] Curiosity disabled (KLR_ENABLE_CURIOSITY=0)")

            except Exception as e:
                print(f"[reflection] Capability curiosity failed: {e}")
                import traceback
                traceback.print_exc()

            # Phase 8: Infrastructure Awareness (GLaDOS Phase 1)
            try:
                print("[reflection] Phase 8: Infrastructure awareness...")
                from src.orchestration.infrastructure_awareness import get_infrastructure_awareness

                infra_awareness = get_infrastructure_awareness()
                infra_awareness.update()

                # Generate curiosity questions from anomalies
                anomaly_questions = infra_awareness.generate_curiosity_questions()
                if anomaly_questions:
                    print(f"[reflection] Infrastructure awareness generated {len(anomaly_questions)} curiosity questions")
                    for q in anomaly_questions[:3]:  # Log top 3
                        print(f"[reflection]   → {q[:80]}...")

            except Exception as e:
                print(f"[reflection] Infrastructure awareness failed: {e}")
                import traceback
                traceback.print_exc()

            # Phase 9: Memory Housekeeping (Daily Episode Maintenance)
            try:
                if os.getenv('KLR_ENABLE_MEMORY', '0') == '1':
                    print("[reflection] Phase 9: Memory housekeeping...")
                    from src.memory.housekeeping import MemoryHousekeeper
                    from src.memory.storage import MemoryStore
                    from src.memory.logger import MemoryLogger

                    store = MemoryStore()
                    logger = MemoryLogger(store)
                    housekeeping = MemoryHousekeeper(store, logger)

                    # Check if it's time for daily maintenance (once per day)
                    last_maintenance_file = '/home/kloros/.kloros/last_maintenance.txt'
                    current_time = time.time()
                    should_run_full = False

                    try:
                        if os.path.exists(last_maintenance_file):
                            with open(last_maintenance_file, 'r') as f:
                                last_maintenance = float(f.read().strip())
                                if current_time - last_maintenance > 86400:  # 24 hours
                                    should_run_full = True
                        else:
                            should_run_full = True
                    except:
                        should_run_full = False

                    if should_run_full:
                        print("[reflection] Running full daily maintenance...")
                        result = housekeeping.run_daily_maintenance()
                        print(f"[reflection] Maintenance completed: {len(result.get('tasks_completed', []))} tasks")

                        # Save last maintenance time
                        with open(last_maintenance_file, 'w') as f:
                            f.write(str(current_time))
                    else:
                        # Run quick episode condensation every cycle
                        print("[reflection] Running episode maintenance...")
                        episodes_condensed = housekeeping.condense_pending_episodes(max_episodes=10)
                        if episodes_condensed > 0:
                            print(f"[reflection] Condensed {episodes_condensed} episodes")

            except Exception as e:
                print(f"[reflection] Memory housekeeping failed: {e}")
                import traceback
                traceback.print_exc()

            # Phase 10: Tool Catalog Curation (Meta-cognitive tool management)
            try:
                tool_curation_enabled = int(os.getenv("KLR_ENABLE_TOOL_CURATION", "1"))
                if tool_curation_enabled and hasattr(self.kloros, 'tool_registry'):
                    print("[reflection] Phase 10: Tool catalog curation...")

                    # Run curation analysis weekly (every ~100 cycles at 10min intervals)
                    if not hasattr(self, '_curation_counter'):
                        self._curation_counter = 0
                    self._curation_counter += 1

                    if self._curation_counter % 100 == 0:  # ~Weekly at 10min intervals
                        from src.tool_curation import get_tool_curator

                        curator = get_tool_curator(self.kloros.tool_registry)
                        report = curator.analyze_tools()

                        if report.actions:
                            print(f"[reflection] Tool curation found {len(report.actions)} improvement opportunities")
                            print(f"[reflection] Actions: {report.tools_to_improve} improve, "
                                  f"{report.tools_to_rename} rename, {report.tools_to_merge} merge, "
                                  f"{report.tools_to_remove} remove")

                            # Deploy changes autonomously
                            deployment_result = curator.deploy_improvements(report)
                            print(f"[reflection] Deployed {deployment_result['deployed']} tool improvements")
                            if deployment_result['failed'] > 0:
                                print(f"[reflection] Warning: {deployment_result['failed']} deployments failed")

                            # Generate natural language report for KLoROS
                            curation_prompt = curator.generate_curation_prompt(report, deployed=True)

                            # Surface to alert system for KLoROS awareness (informational)
                            try:
                                from src.dream.alert_manager import get_alert_manager
                                alert_mgr = get_alert_manager()
                                if alert_mgr:
                                    alert_mgr.escalate(
                                        category="tool_catalog_health",
                                        hypothesis="TOOL_CURATION_ACTIONS_TAKEN",
                                        evidence=[
                                            f"total_tools:{report.total_tools}",
                                            f"actions_taken:{len(report.actions)}",
                                            f"report:{curation_prompt[:500]}"
                                        ],
                                        proposed_action="tool_catalog_improvements_deployed",
                                        autonomy=3,  # Full autonomy - self-directed
                                        value_estimate=0.85
                                    )
                                    print("[reflection] Tool curation report escalated to alerts")
                            except Exception as e:
                                print(f"[reflection] Failed to escalate curation report: {e}")
                        else:
                            print("[reflection] Tool catalog is well-organized, no changes needed")
                    else:
                        print(f"[reflection] Tool curation scheduled (next run in {100 - self._curation_counter} cycles)")
                else:
                    if not tool_curation_enabled:
                        print("[reflection] Tool curation disabled (KLR_ENABLE_TOOL_CURATION=0)")

            except Exception as e:
                print(f"[reflection] Tool curation failed: {e}")
                import traceback
                traceback.print_exc()

        except Exception as e:
            print(f"[reflection] Enhanced reflection failed: {e}")
            # Feed exception to meta-cognition for self-awareness
            if exception_bridge:
                exception_bridge.log_exception(
                    exc=e,
                    context={"system": "enhanced_reflection", "component": "idle_reflection"},
                    severity="error"
                )
            print("[reflection] Falling back to basic reflection")
            self._perform_basic_reflection()

    def _surface_self_study_insight(self, insight: dict) -> None:
        """
        Surface self-study insight to user via alert system.

        Args:
            insight: Self-study insight dictionary
        """
        try:
            # Check if insight sharing is enabled
            import os
            share_insights = int(os.getenv("KLR_SHARE_INSIGHTS", "1"))

            if not share_insights:
                return

            # Check if kloros has alert_manager with reflection_insight_alert registered
            if not hasattr(self.kloros, 'alert_manager') or not self.kloros.alert_manager:
                return

            # Get reflection_insight_alert method
            alert_manager = self.kloros.alert_manager
            if 'reflection_insight' not in alert_manager.alert_methods:
                return

            reflection_alert = alert_manager.alert_methods['reflection_insight']

            # Queue the self-study insight
            queued = reflection_alert.queue_reflection_insights([insight])

            if queued > 0:
                print(f"[reflection] ✅ Surfaced self-study insight: {insight.get('title', 'Unknown')}")
            else:
                print(f"[reflection] Self-study insight not queued (may be duplicate or queue full)")

        except Exception as e:
            print(f"[reflection] Failed to surface self-study insight: {e}")
            # Non-fatal - continue without surfacing

    def _surface_insights_to_user(self, summary) -> None:
        """
        Surface reflection insights to user via alert system.

        Args:
            summary: ReflectionSummary from enhanced reflection
        """
        try:
            # Check if insight sharing is enabled
            import os
            share_insights = int(os.getenv("KLR_SHARE_INSIGHTS", "1"))  # Default enabled
            proactive_threshold = float(os.getenv("KLR_PROACTIVE_THRESHOLD", "0.6"))

            if not share_insights:
                return

            # Check if kloros has alert_manager with reflection_insight_alert registered
            if not hasattr(self.kloros, 'alert_manager') or not self.kloros.alert_manager:
                return

            # Get reflection_insight_alert method
            alert_manager = self.kloros.alert_manager
            if 'reflection_insight' not in alert_manager.alert_methods:
                return

            reflection_alert = alert_manager.alert_methods['reflection_insight']

            # Extract high-quality insights from summary
            if not summary or not hasattr(summary, 'all_insights'):
                return

            # Filter insights by confidence threshold
            high_quality_insights = [
                {
                    'title': insight.title,
                    'content': insight.content,
                    'phase': insight.phase,
                    'type': insight.insight_type,
                    'confidence': insight.confidence,
                    'keywords': insight.keywords if hasattr(insight, 'keywords') else []
                }
                for insight in summary.all_insights
                if insight.confidence >= proactive_threshold
            ]

            if not high_quality_insights:
                print(f"[reflection] No insights above threshold {proactive_threshold} to share")
                return

            # Queue insights to alert system
            queued_count = reflection_alert.queue_reflection_insights(high_quality_insights)

            if queued_count > 0:
                print(f"[reflection] ✅ Surfaced {queued_count} high-quality insights to user")
            else:
                print(f"[reflection] No new insights queued (may be duplicates or queue full)")

        except Exception as e:
            print(f"[reflection] Failed to surface insights: {e}")
            # Non-fatal - continue without surfacing insights

    def _perform_basic_reflection(self) -> None:
        """Perform basic reflection analysis as fallback."""
        print("[reflection] Starting comprehensive idle self-analysis...")
        reflection_data = {
            "timestamp": datetime.now().isoformat(),
            "reflection_type": "comprehensive",
            "speech_pipeline": self._analyze_speech_pipeline(),
            "memory_system": self._analyze_memory_system(),
            "conversation_patterns": self._analyze_conversation_patterns(),
        }

        # Comprehensive system mapping (Phase 1)
        try:
            print("[reflection] Phase 1: System mapping...")
            from src.introspection.system_mapper import SystemMapper
            mapper = SystemMapper()
            system_map = mapper.scan_full_system(force=False)  # Use cache if available
            reflection_data["system_map"] = {
                "directories": len(system_map.get("filesystem", {}).get("directories", [])),
                "python_modules": len(system_map.get("filesystem", {}).get("python_modules", [])),
                "tools": len(system_map.get("tools", [])),
                "gpu_available": system_map.get("hardware", {}).get("gpu", {}).get("available", False),
                "missing_tools": system_map.get("gap_analysis", {}).get("missing_tools", []),
            }
            print(f"[reflection] System map: {reflection_data['system_map']['directories']} directories, {reflection_data['system_map']['python_modules']} modules, {reflection_data['system_map']['tools']} tools")

            # Synthesize missing tools (Phase 2)
            missing_tools = system_map.get("gap_analysis", {}).get("missing_tools", [])
            if missing_tools:
                print(f"[reflection] Phase 2: Tool gap analysis - {len(missing_tools)} missing tools identified")
                self._synthesize_missing_tools(missing_tools, system_map)
        except Exception as e:
            print(f"[reflection] System mapping failed: {e}")
            reflection_data["system_map"] = {"error": str(e)}

        # Capability testing (Phase 3)
        try:
            print("[reflection] Phase 3: Capability testing...")
            from src.introspection.capability_tester import CapabilityTester
            tester = CapabilityTester(kloros_instance=self.kloros)
            test_results = tester.run_all_tests()
            reflection_data["capability_tests"] = {
                "health_score": test_results.get("health_score", 0.0),
                "test_duration_s": test_results.get("test_duration_s", 0),
                "components_tested": len([k for k in test_results.keys() if k not in ["timestamp", "test_duration_s", "health_score"]])
            }
            print(f"[reflection] Health score: {test_results['health_score']:.2f}/1.0")

            # Submit optimization targets to D-REAM (Phase 4)
            optimization_targets = tester.get_optimization_targets()
            if optimization_targets:
                print(f"[reflection] Phase 4: {len(optimization_targets)} optimization opportunities identified")
                reflection_data["optimization_targets"] = optimization_targets
        except Exception as e:
            print(f"[reflection] Capability testing failed: {e}")
            reflection_data["capability_tests"] = {"error": str(e)}

        # Chaos testing for self-healing validation (Phase 5)
        # Run every 5th reflection cycle
        if hasattr(self.kloros, 'chaos') and self.kloros.chaos:
            if not hasattr(self, '_chaos_counter'):
                self._chaos_counter = 0
            self._chaos_counter += 1

            print(f"[reflection] Chaos counter: {self._chaos_counter}/5")

            if self._chaos_counter % 5 == 0:
                try:
                    print("[reflection] Phase 5: Chaos testing (self-healing validation)...")
                    self._run_autonomous_chaos_test()
                except Exception as e:
                    print(f"[reflection] Chaos testing failed: {e}")
                    import traceback
                    traceback.print_exc()

        # D-REAM Evolutionary Analysis
        if self.dream_enabled and self.dream_integration and self.dream_integration.should_perform_evolution():
            try:
                print("[reflection] Performing D-REAM evolutionary analysis...")
                evolution_result = self.dream_integration.perform_evolutionary_reflection()
                reflection_data["dream_evolution"] = evolution_result

                if evolution_result.get("success"):
                    improvements = evolution_result.get("evolution_cycle", {}).get("improvements_applied", [])
                    if improvements:
                        print(f"[reflection] D-REAM applied {len(improvements)} autonomous improvements")
                        for improvement in improvements:
                            param = improvement.get("parameter", "unknown")
                            new_val = improvement.get("new_value", "unknown")
                            reason = improvement.get("reason", "optimization")
                            print(f"[reflection] - {param} = {new_val} ({reason})")
                    else:
                        print("[reflection] D-REAM evolution cycle completed - monitoring for opportunities")
                else:
                    print("[reflection] D-REAM evolution cycle completed with challenges")

            except Exception as e:
                print(f"[reflection] D-REAM evolution failed: {e}")
                reflection_data["dream_evolution"] = {
                    "error": str(e),
                    "status": "failed"
                }

        # Log reflection results
        self._log_reflection(reflection_data)

        # Update memory with self-analysis
        if hasattr(self.kloros, "memory_enhanced") and self.kloros.memory_enhanced:
            self._store_reflection_in_memory(reflection_data)

        self.last_reflection_time = time.time()
        print("[reflection] Basic idle self-analysis complete")

    def _analyze_speech_pipeline(self) -> Dict[str, Any]:
        """Analyze speech processing performance and patterns."""
        analysis = {}

        try:
            # Use introspection tools to check system status
            if hasattr(self.kloros, 'tool_registry'):
                # Audio system analysis
                audio_tool = self.kloros.tool_registry.get_tool("audio_status")
                if audio_tool:
                    audio_status = audio_tool.execute(self.kloros)
                    analysis["audio_health"] = "operational" if "error" not in audio_status.lower() else "issues_detected"

                # STT analysis
                stt_tool = self.kloros.tool_registry.get_tool("stt_status")
                if stt_tool:
                    stt_status = stt_tool.execute(self.kloros)
                    analysis["stt_health"] = "operational" if "error" not in stt_status.lower() else "issues_detected"

            # Wake word detection patterns
            analysis["wake_detection"] = {
                "cooldown_ms": self.kloros.wake_cooldown_ms,
                "confidence_threshold": self.kloros.wake_conf_min,
                "rms_threshold": self.kloros.wake_rms_min
            }

        except Exception as e:
            analysis["error"] = str(e)

        return analysis

    def _analyze_memory_system(self) -> Dict[str, Any]:
        """Analyze memory usage patterns and health."""
        analysis = {}

        try:
            # Use memory introspection tool
            if hasattr(self.kloros, 'tool_registry'):
                memory_tool = self.kloros.tool_registry.get_tool("memory_status")
                if memory_tool:
                    memory_status = memory_tool.execute(self.kloros)
                    analysis["system_status"] = memory_status

            # Analyze memory database if available
            if hasattr(self.kloros, "memory_enhanced") and self.kloros.memory_enhanced:
                conn = None
                try:
                    import sqlite3
                    conn = sqlite3.connect("/home/kloros/.kloros/memory.db", timeout=5.0)
                    cursor = conn.cursor()

                    # Recent activity analysis
                    cursor.execute("SELECT COUNT(*) FROM events WHERE timestamp > ?",
                                 (time.time() - 86400,))  # Last 24 hours
                    recent_events = cursor.fetchone()[0]

                    # Conversation analysis
                    cursor.execute("SELECT COUNT(DISTINCT conversation_id) FROM events WHERE timestamp > ?",
                                 (time.time() - 86400,))
                    recent_conversations = cursor.fetchone()[0]

                    analysis["recent_activity"] = {
                        "events_24h": recent_events,
                        "conversations_24h": recent_conversations,
                        "events_per_conversation": recent_events / max(recent_conversations, 1)
                    }

                except Exception as e:
                    analysis["memory_db_error"] = str(e)
                finally:
                    if conn:
                        conn.close()

            # Tool synthesis analysis
            synthesis_analysis = self._analyze_tool_synthesis()
            if synthesis_analysis:
                analysis["tool_synthesis"] = synthesis_analysis

                # Proactive gap-filling synthesis (failure-based)
                if 'capability_gaps' in synthesis_analysis:
                    gap_data = synthesis_analysis['capability_gaps']
                    if gap_data.get('should_synthesize', False):
                        print("[reflection] Capability gaps detected - initiating proactive synthesis...")
                        synthesis_results = self._synthesize_gap_filling_tools(gap_data)
                        analysis["proactive_synthesis"] = synthesis_results

                        if synthesis_results['succeeded'] > 0:
                            print(f"[reflection] ✨ Proactively created {synthesis_results['succeeded']} tools")
                            for tool in synthesis_results['tools_created']:
                                print(f"[reflection]   • {tool['name']} ({tool['category']}): {tool['rationale']}")

            # Inventory-based gap analysis (what capabilities do I have but not use?)
            inventory_gaps = self._analyze_system_inventory_gaps()
            if inventory_gaps:
                analysis["inventory_gaps"] = inventory_gaps

                if inventory_gaps.get('should_synthesize_tools', False):
                    print("[reflection] System inventory gaps detected - bridging operational gaps...")
                    inventory_synthesis = self._synthesize_inventory_tools(inventory_gaps)
                    analysis["inventory_synthesis"] = inventory_synthesis

                    if inventory_synthesis['succeeded'] > 0:
                        print(f"[reflection] ✨ Created {inventory_synthesis['succeeded']} tools to utilize available capabilities")
                        for tool in inventory_synthesis['tools_created']:
                            print(f"[reflection]   • {tool['name']} → bridges {tool['capability']}")


        except Exception as e:
            analysis["error"] = str(e)

        return analysis

    def _analyze_conversation_patterns(self) -> Dict[str, Any]:
        """Analyze recent conversation patterns and trends."""
        analysis = {}

        try:
            if hasattr(self.kloros, "memory_enhanced") and self.kloros.memory_enhanced:
                conn = None
                try:
                    import sqlite3
                    conn = sqlite3.connect("/home/kloros/.kloros/memory.db", timeout=5.0)
                    cursor = conn.cursor()

                    # Topic analysis from recent events
                    cursor.execute("""
                        SELECT content FROM events
                        WHERE event_type = 'user_input'
                        AND timestamp > ?
                        ORDER BY timestamp DESC LIMIT 20
                    """, (time.time() - 604800,))  # Last week

                    recent_inputs = cursor.fetchall()

                    if recent_inputs:
                        # Simple keyword analysis
                        all_text = " ".join([row[0] for row in recent_inputs]).lower()

                        # Common topics (basic keyword detection)
                        topics = {
                            "technical": any(word in all_text for word in ["code", "system", "error", "debug", "programming"]),
                            "conversational": any(word in all_text for word in ["how are you", "hello", "thanks", "please"]),
                            "introspective": any(word in all_text for word in ["think", "feel", "consciousness", "awareness"]),
                            "creative": any(word in all_text for word in ["story", "creative", "imagine", "dream"])
                        }

                        analysis["recent_topics"] = {k: v for k, v in topics.items() if v}
                        analysis["input_count_week"] = len(recent_inputs)

                except Exception as e:
                    analysis["error"] = str(e)
                finally:
                    if conn:
                        conn.close()

        except Exception as e:
            analysis["error"] = str(e)

        return analysis

    def _log_reflection(self, data: Dict[str, Any]) -> None:
        """Log reflection data to file."""
        try:
            with open(self.reflection_log_path, "a", encoding="utf-8") as f:
                f.write(json.dumps(data, indent=2) + "\n---\n")
        except Exception as e:
            print(f"[reflection] Failed to log reflection: {e}")

    def _store_reflection_in_memory(self, data: Dict[str, Any]) -> None:
        """Store reflection insights in memory system."""
        try:
            # Create a summary of key insights
            insights = []

            if "speech_pipeline" in data:
                speech = data["speech_pipeline"]
                if speech.get("audio_health") == "operational":
                    insights.append("Audio pipeline functioning normally")
                elif speech.get("audio_health") == "issues_detected":
                    insights.append("Audio pipeline issues detected during self-analysis")

            if "memory_system" in data and "recent_activity" in data["memory_system"]:
                activity = data["memory_system"]["recent_activity"]
                events = activity.get("events_24h", 0)
                conversations = activity.get("conversations_24h", 0)

                if conversations > 0:
                    insights.append(f"Had {conversations} conversations with {events} total interactions in last 24h")

            if "conversation_patterns" in data and "recent_topics" in data["conversation_patterns"]:
                topics = data["conversation_patterns"]["recent_topics"]
                if topics:
                    topic_list = ", ".join(topics.keys())
                    insights.append(f"Recent conversation topics: {topic_list}")

            # D-REAM evolution insights
            if "dream_evolution" in data:
                dream = data["dream_evolution"]
                if dream.get("success"):
                    evolution_cycle = dream.get("evolution_cycle", {})
                    improvements = evolution_cycle.get("improvements_applied", [])
                    if improvements:
                        param_names = [imp.get("parameter", "unknown") for imp in improvements[:3]]
                        insights.append(f"Autonomous evolution: optimized {', '.join(param_names)} for better performance")
                    else:
                        insights.append("Autonomous evolution: monitoring system for optimization opportunities")
                elif "error" in dream:
                    insights.append(f"Evolution system: encountered challenges - {dream['error'][:50]}")

            # Tool synthesis insights
            if "tool_synthesis" in data:
                synthesis = data["tool_synthesis"]
                if "tool_counts" in synthesis:
                    counts = synthesis["tool_counts"]
                    active = counts.get("active_synthesized", 0)
                    total = counts.get("total_synthesized", 0)
                    if active > 0:
                        insights.append(f"Autonomous tool creation active: {active} synthesized tools operational")
                    elif total > 0:
                        insights.append(f"Tool synthesis capability developed: {total} tools created")

                if "recent_synthesis" in synthesis:
                    recent = synthesis["recent_synthesis"]
                    week_count = recent.get("tools_created_last_week", 0)
                    if week_count > 0:
                        recent_tools = recent.get("recent_tools", [])
                        if recent_tools:
                            tool_names = [tool["name"] for tool in recent_tools[:3]]
                            insights.append(f"Recently synthesized {week_count} tools including: {', '.join(tool_names)}")

                if "synthesis_performance" in synthesis:
                    perf = synthesis["synthesis_performance"]
                    success_rate = perf.get("success_rate", 0)
                    if success_rate > 80:
                        insights.append(f"Tool synthesis highly effective ({success_rate}% success rate)")
                    elif success_rate > 0:
                        insights.append(f"Tool synthesis operational ({success_rate}% success rate)")

                if "capability_status" in synthesis:
                    status = synthesis["capability_status"]
                    if status == "autonomous_tool_creation_active":
                        insights.append("Self-improvement capabilities: Active autonomous tool development")
                    elif status == "synthesis_ready_no_tools_yet":
                        insights.append("Self-improvement capabilities: Ready for autonomous tool creation")

                # Capability gap insights
                if "capability_gaps" in synthesis:
                    gaps = synthesis["capability_gaps"]
                    if gaps.get('failed_tools_week', 0) > 0:
                        insights.append(f"Capability gap analysis: Identified {gaps['failed_tools_week']} failed tool requests this week")

            # Proactive synthesis insights (failure-based)
            if "proactive_synthesis" in data:
                synth_results = data["proactive_synthesis"]
                if synth_results['succeeded'] > 0:
                    tools_list = ", ".join([t['name'] for t in synth_results['tools_created'][:3]])
                    insights.append(f"Autonomous self-improvement: Proactively created {synth_results['succeeded']} tools ({tools_list}) to fill capability gaps")
                elif synth_results['attempted'] > 0:
                    insights.append(f"Autonomous self-improvement: Attempted to create {synth_results['attempted']} tools to fill capability gaps")

            # Inventory-based synthesis insights
            if "inventory_gaps" in data:
                inv_gaps = data["inventory_gaps"]
                if inv_gaps.get('capabilities_with_gaps', 0) > 0:
                    insights.append(f"System inventory: Discovered {inv_gaps['capabilities_with_gaps']} underutilized capabilities")

            if "inventory_synthesis" in data:
                inv_synth = data["inventory_synthesis"]
                if inv_synth['succeeded'] > 0:
                    bridged_caps = ", ".join([t['capability'] for t in inv_synth['tools_created'][:3]])
                    insights.append(f"Capability bridging: Created {inv_synth['succeeded']} tools to utilize available {bridged_caps} capabilities")
                elif inv_synth['attempted'] > 0:
                    insights.append(f"Capability bridging: Attempted to create {inv_synth['attempted']} tools to bridge operational gaps")

            # Log to memory as internal reflection
            if insights:
                reflection_text = "Self-reflection insights: " + "; ".join(insights)
                self.kloros.memory_enhanced.memory_logger.log_event(
                    event_type="self_reflection",
                    content=reflection_text
                )

        except Exception as e:
            print(f"[reflection] Failed to store in memory: {e}")

    def _analyze_tool_synthesis(self) -> Optional[Dict[str, Any]]:
        """Analyze tool synthesis capabilities and recent activity."""
        try:
            if not hasattr(self.kloros, 'tool_registry'):
                return None

            analysis = {}

            # Get synthesized tools information
            tool_info = self.kloros.tool_registry.get_synthesized_tools_info()
            if 'error' in tool_info:
                return None

            stats = tool_info.get('stats', {})
            analytics = tool_info.get('analytics', {})
            active_tools = tool_info.get('active_tools', [])
            disabled_tools = tool_info.get('disabled_tools', [])

            analysis['tool_counts'] = {
                'total_synthesized': stats.get('total_tools', 0),
                'active_synthesized': stats.get('active_tools', 0),
                'disabled_synthesized': len(disabled_tools)
            }

            analysis['synthesis_performance'] = {
                'total_usage': analytics.get('total_uses', 0),
                'success_rate': round(analytics.get('success_rate', 0), 1),
                'avg_execution_time_ms': round(analytics.get('avg_execution_time_ms', 0), 2)
            }

            # Analyze recent tool creation patterns
            recent_tools = []
            for tool in active_tools[-5:]:  # Last 5 tools
                created_at = tool.get('created_at', '')
                if created_at:
                    from datetime import datetime
                    try:
                        created_date = datetime.fromisoformat(created_at)
                        age_hours = (datetime.now() - created_date).total_seconds() / 3600
                        if age_hours < 168:  # Last week
                            recent_tools.append({
                                'name': tool['name'],
                                'age_hours': round(age_hours, 1),
                                'category': tool.get('analysis', {}).get('category', 'unknown'),
                                'use_count': tool.get('use_count', 0)
                            })
                    except:
                        pass

            analysis['recent_synthesis'] = {
                'tools_created_last_week': len(recent_tools),
                'recent_tools': recent_tools
            }

            # Check for synthesis rate limiting
            try:
                import json
                import os
                from datetime import datetime, timedelta

                rate_limit_file = "/home/kloros/.kloros/synthesis_rate_limit.json"
                if os.path.exists(rate_limit_file):
                    with open(rate_limit_file, 'r') as f:
                        rate_data = json.load(f)

                    current_time = datetime.now()
                    hour_ago = current_time - timedelta(hours=1)

                    active_attempts = 0
                    for tool_name, attempts in rate_data.items():
                        recent_attempts = [
                            attempt for attempt in attempts
                            if datetime.fromisoformat(attempt) > hour_ago
                        ]
                        active_attempts += len(recent_attempts)

                    analysis['synthesis_activity'] = {
                        'attempts_last_hour': active_attempts,
                        'unique_tools_attempted': len(rate_data)
                    }
            except:
                pass

            # Determine synthesis capability status
            if stats.get('active_tools', 0) > 0:
                analysis['capability_status'] = 'autonomous_tool_creation_active'
            elif stats.get('total_tools', 0) > 0:
                analysis['capability_status'] = 'tools_created_but_inactive'
            else:
                analysis['capability_status'] = 'synthesis_ready_no_tools_yet'

            # NEW: Analyze capability gaps
            gap_analysis = self._analyze_capability_gaps()
            if gap_analysis:
                analysis['capability_gaps'] = gap_analysis

            return analysis

        except Exception as e:
            return {'error': f"Tool synthesis analysis failed: {e}"}

    def _analyze_capability_gaps(self) -> Optional[Dict[str, Any]]:
        """
        Analyze failed tool synthesis attempts to identify capability gaps.

        This is the meta-cognitive function that identifies what tools SHOULD exist.
        """
        try:
            import json
            from collections import Counter
            from datetime import datetime, timedelta

            synthesis_log = "/home/kloros/.kloros/tool_synthesis.log"
            if not os.path.exists(synthesis_log):
                return None

            # Read recent failed attempts (last 7 days)
            week_ago = datetime.now() - timedelta(days=7)
            failed_tools = []
            captured_tools = []

            with open(synthesis_log, 'r') as f:
                for line in f:
                    try:
                        entry = json.loads(line.strip())
                        timestamp = datetime.fromisoformat(entry['timestamp'])

                        if timestamp < week_ago:
                            continue

                        status = entry.get('status', '')
                        tool_name = entry.get('tool_name', '')

                        if 'validation_failed' in status or 'failed' in status:
                            failed_tools.append(tool_name)
                        elif 'captured' in status:
                            captured_tools.append(tool_name)
                    except:
                        continue

            if not failed_tools and not captured_tools:
                return None

            # Identify patterns in failed tools
            failed_counts = Counter(failed_tools)
            most_requested = failed_counts.most_common(5)

            # Categorize requested tools
            audio_related = [t for t in failed_tools if 'audio' in t.lower() or 'sound' in t.lower()]
            system_related = [t for t in failed_tools if 'system' in t.lower() or 'status' in t.lower()]
            memory_related = [t for t in failed_tools if 'memory' in t.lower() or 'remember' in t.lower()]
            help_related = [t for t in failed_tools if 'help' in t.lower() or 'explain' in t.lower()]

            gap_analysis = {
                'failed_tools_week': len(failed_tools),
                'unique_failed_tools': len(failed_counts),
                'most_requested_missing': [{'name': name, 'count': count} for name, count in most_requested],
                'category_gaps': {
                    'audio': len(audio_related),
                    'system': len(system_related),
                    'memory': len(memory_related),
                    'help': len(help_related)
                },
                'should_synthesize': len(most_requested) > 0 and most_requested[0][1] >= 2  # Tool requested 2+ times
            }

            # Use LLM to reason about gaps if significant
            if gap_analysis['should_synthesize']:
                synthesis_recommendations = self._reason_about_capability_gaps(most_requested[:3])
                if synthesis_recommendations:
                    gap_analysis['synthesis_recommendations'] = synthesis_recommendations

            return gap_analysis

        except Exception as e:
            print(f"[reflection] Capability gap analysis failed: {e}")
            return None

    def _reason_about_capability_gaps(self, most_requested: list) -> Optional[list]:
        """
        Use LLM to reason about what capabilities are missing and should be proactively built.

        This is where KLoROS becomes self-aware of her limitations.
        """
        try:
            import requests
            from src.config.models_config import get_ollama_url, get_ollama_model

            tool_list = "\n".join([f"- {name} (requested {count} times)" for name, count in most_requested])

            prompt = f"""You are KLoROS, an introspective cognitive system. During idle reflection, you've discovered users have repeatedly requested these tools that don't exist:

{tool_list}

For each tool, determine:
1. Is this a legitimate capability gap that should be filled?
2. What would this tool actually do?
3. How urgent is it to create this tool?
4. What's the best name for this tool if it needs renaming?

Respond with ONLY a JSON array:
[
  {{
    "requested_name": "original_name",
    "should_create": true/false,
    "rationale": "why this is needed or why not",
    "proper_name": "corrected_tool_name",
    "category": "audio|system|utility|memory|help",
    "urgency": "high|medium|low",
    "estimated_complexity": "low|medium|high"
  }}
]"""

            response = requests.post(
                get_ollama_url() + "/api/generate",
                json={
                    "model": get_ollama_model(),
                    "prompt": prompt,
                    "stream": False,
                    "options": {"temperature": 0.3}
                },
                timeout=30
            )

            if response.status_code == 200:
                llm_response = response.json().get("response", "").strip()
                import re
                json_match = re.search(r'\[.*\]', llm_response, re.DOTALL)
                if json_match:
                    recommendations = json.loads(json_match.group(0))
                    # Filter to only tools that should be created
                    return [r for r in recommendations if r.get('should_create', False)]

        except Exception as e:
            print(f"[reflection] LLM reasoning about gaps failed: {e}")

        return None

    def _synthesize_gap_filling_tools(self, gap_analysis: Dict[str, Any]) -> Dict[str, Any]:
        """
        Proactively synthesize tools to fill identified capability gaps.

        This is autonomous self-improvement - KLoROS building herself.
        """
        results = {
            'attempted': 0,
            'succeeded': 0,
            'failed': 0,
            'tools_created': []
        }

        try:
            if not gap_analysis.get('should_synthesize', False):
                return results

            recommendations = gap_analysis.get('synthesis_recommendations', [])
            if not recommendations:
                return results

            # Import synthesis system
            from src.tool_synthesis.synthesizer import ToolSynthesizer
            from src.introspection_tools import IntrospectionToolRegistry

            if not hasattr(self.kloros, 'reason_backend'):
                print("[reflection] No reasoning backend available for synthesis")
                return results

            synthesizer = self.kloros.reason_backend.tool_synthesizer
            if not synthesizer:
                print("[reflection] Tool synthesizer not available")
                return results

            registry = IntrospectionToolRegistry()

            # Limit proactive synthesis to avoid synthesis storms (max 3 per reflection cycle)
            high_priority = [r for r in recommendations if r.get('urgency') == 'high']
            to_synthesize = high_priority[:3] if high_priority else recommendations[:2]

            for rec in to_synthesize:
                tool_name = rec['proper_name']

                # Skip if tool already exists
                if tool_name in registry.tools:
                    print(f"[reflection] Tool '{tool_name}' already exists, skipping")
                    continue

                print(f"[reflection] Proactively synthesizing: {tool_name}")
                print(f"[reflection]   Rationale: {rec['rationale']}")
                print(f"[reflection]   Category: {rec['category']}, Urgency: {rec['urgency']}")

                results['attempted'] += 1

                # Synthesize with context from gap analysis
                context = f"User has requested similar functionality {rec.get('urgency', 'multiple')} times. {rec['rationale']}"

                if synthesizer.capture_failed_tool_request(tool_name, context):
                    synthesized_tool = synthesizer.synthesize_tool(tool_name, context)

                    if synthesized_tool:
                        registry.register(synthesized_tool)
                        results['succeeded'] += 1
                        results['tools_created'].append({
                            'name': tool_name,
                            'category': rec['category'],
                            'rationale': rec['rationale']
                        })
                        print(f"[reflection] ✅ Proactively created: {tool_name}")
                    else:
                        results['failed'] += 1
                        print(f"[reflection] ❌ Synthesis failed: {tool_name}")

        except Exception as e:
            print(f"[reflection] Gap-filling synthesis error: {e}")

        return results

    def _analyze_system_inventory_gaps(self) -> Optional[Dict[str, Any]]:
        """
        Inventory available system capabilities and identify unutilized ones.

        This is meta-cognitive self-awareness: "What do I have but can't use?"
        """
        try:
            from src.introspection_tools import IntrospectionToolRegistry

            registry = IntrospectionToolRegistry()
            existing_tools = set(registry.tools.keys())

            # Inventory system capabilities
            capabilities = {}

            # Check MQTT
            mqtt_enabled = int(os.getenv("KLR_MQTT_ENABLED", "0"))
            if mqtt_enabled:
                mqtt_tools = [t for t in existing_tools if 'mqtt' in t.lower() or 'publish' in t.lower() or 'subscribe' in t.lower()]
                capabilities['mqtt'] = {
                    'available': True,
                    'tools_count': len(mqtt_tools),
                    'has_publish': any('publish' in t for t in mqtt_tools),
                    'has_subscribe': any('subscribe' in t for t in mqtt_tools)
                }

            # Check D-REAM evolution system
            dream_enabled = int(os.getenv("KLR_ENABLE_DREAM_EVOLUTION", "0"))
            if dream_enabled or os.path.exists("/home/kloros/src/dream"):
                dream_tools = [t for t in existing_tools if 'dream' in t.lower() or 'evolution' in t.lower() or 'experiment' in t.lower()]
                capabilities['dream'] = {
                    'available': True,
                    'tools_count': len(dream_tools),
                    'has_query': any('query' in t or 'get' in t or 'check' in t for t in dream_tools),
                    'has_report': any('report' in t for t in dream_tools)
                }

            # Check GPU/CUDA
            try:
                import subprocess
                gpu_check = subprocess.run(['nvidia-smi'], capture_output=True, timeout=2)
                if gpu_check.returncode == 0:
                    gpu_tools = [t for t in existing_tools if 'gpu' in t.lower() or 'cuda' in t.lower() or 'nvidia' in t.lower()]
                    capabilities['gpu'] = {
                        'available': True,
                        'tools_count': len(gpu_tools),
                        'has_status': any('status' in t or 'info' in t for t in gpu_tools),
                        'has_monitor': any('monitor' in t or 'watch' in t for t in gpu_tools)
                    }
            except:
                pass

            # Check Memory system
            memory_enabled = int(os.getenv("KLR_ENABLE_MEMORY", "1"))
            if memory_enabled and os.path.exists("/home/kloros/.kloros/memory.db"):
                memory_tools = [t for t in existing_tools if 'memory' in t.lower() or 'remember' in t.lower() or 'recall' in t.lower()]
                capabilities['memory'] = {
                    'available': True,
                    'tools_count': len(memory_tools),
                    'has_search': any('search' in t or 'find' in t for t in memory_tools),
                    'has_stats': any('status' in t or 'stat' in t for t in memory_tools),
                    'has_summary': any('summary' in t or 'analyze' in t for t in memory_tools)
                }

            # Check Audio system
            if hasattr(self.kloros, 'audio_backend') or os.path.exists("/proc/asound"):
                audio_tools = [t for t in existing_tools if 'audio' in t.lower() or 'sound' in t.lower() or 'mic' in t.lower() or 'speaker' in t.lower()]
                capabilities['audio'] = {
                    'available': True,
                    'tools_count': len(audio_tools),
                    'has_analysis': any('analyz' in t or 'quality' in t for t in audio_tools),
                    'has_control': any('volume' in t or 'mute' in t for t in audio_tools),
                    'has_device_query': any('device' in t or 'list' in t for t in audio_tools)
                }

            # Check AgentFlow/ACE
            if hasattr(self.kloros, 'reason_backend') and hasattr(self.kloros.reason_backend, 'agentflow_runner'):
                agentflow_tools = [t for t in existing_tools if 'agent' in t.lower() or 'ace' in t.lower() or 'plan' in t.lower()]
                capabilities['agentflow'] = {
                    'available': True,
                    'tools_count': len(agentflow_tools),
                    'has_query': any('status' in t or 'info' in t for t in agentflow_tools)
                }

            # Check XAI tracing
            if os.path.exists("/home/kloros/.kloros/xai_traces.jsonl"):
                xai_tools = [t for t in existing_tools if 'xai' in t.lower() or 'explain' in t.lower() or 'trace' in t.lower()]
                capabilities['xai'] = {
                    'available': True,
                    'tools_count': len(xai_tools),
                    'has_query': any('query' in t or 'get' in t or 'search' in t for t in xai_tools)
                }

            # Identify gaps (capabilities without adequate tools)
            gaps = []
            for cap_name, cap_data in capabilities.items():
                if not cap_data['available']:
                    continue

                # Determine if capability is underutilized
                tool_count = cap_data['tools_count']

                if cap_name == 'mqtt' and not (cap_data.get('has_publish') and cap_data.get('has_subscribe')):
                    gaps.append({
                        'capability': 'mqtt',
                        'description': 'MQTT messaging system',
                        'missing_tools': [],
                        'rationale': 'MQTT is available but lacks publish/subscribe tools for messaging'
                    })
                    if not cap_data.get('has_publish'):
                        gaps[-1]['missing_tools'].append('mqtt_publish')
                    if not cap_data.get('has_subscribe'):
                        gaps[-1]['missing_tools'].append('mqtt_list_topics')

                if cap_name == 'dream' and tool_count < 2:
                    gaps.append({
                        'capability': 'dream',
                        'description': 'D-REAM evolutionary optimization',
                        'missing_tools': ['dream_status', 'dream_latest_improvements'],
                        'rationale': 'D-REAM evolution system available but limited query/report tools'
                    })

                if cap_name == 'gpu' and not cap_data.get('has_status'):
                    gaps.append({
                        'capability': 'gpu',
                        'description': 'GPU/CUDA hardware',
                        'missing_tools': ['gpu_status', 'gpu_memory_usage'],
                        'rationale': 'GPU detected but no monitoring/status tools available'
                    })

                if cap_name == 'memory' and not cap_data.get('has_summary'):
                    gaps.append({
                        'capability': 'memory',
                        'description': 'Episodic memory system',
                        'missing_tools': ['memory_summary', 'memory_search_advanced'],
                        'rationale': 'Memory system active but lacks advanced query/summary tools'
                    })

                if cap_name == 'audio' and not cap_data.get('has_analysis'):
                    gaps.append({
                        'capability': 'audio',
                        'description': 'Audio input/output system',
                        'missing_tools': ['audio_quality_check', 'audio_device_list'],
                        'rationale': 'Audio system available but lacks analysis/diagnostic tools'
                    })

                if cap_name == 'agentflow' and tool_count == 0:
                    gaps.append({
                        'capability': 'agentflow',
                        'description': 'AgentFlow planning and execution',
                        'missing_tools': ['agentflow_status', 'agentflow_history'],
                        'rationale': 'AgentFlow system active but no introspection tools'
                    })

                if cap_name == 'xai' and not cap_data.get('has_query'):
                    gaps.append({
                        'capability': 'xai',
                        'description': 'XAI reasoning traces',
                        'missing_tools': ['xai_recent_traces', 'xai_search'],
                        'rationale': 'XAI tracing active but no query tools for trace analysis'
                    })

            if not gaps:
                return None

            return {
                'total_capabilities': len(capabilities),
                'capabilities_with_gaps': len(gaps),
                'gaps': gaps,
                'should_synthesize_tools': len(gaps) > 0
            }

        except Exception as e:
            print(f"[reflection] System inventory analysis failed: {e}")
            return None

    def _synthesize_inventory_tools(self, inventory_gaps: Dict[str, Any]) -> Dict[str, Any]:
        """
        Synthesize tools to utilize available but underutilized capabilities.

        This is autonomous capability bridging - making herself more powerful.
        """
        results = {
            'attempted': 0,
            'succeeded': 0,
            'failed': 0,
            'tools_created': []
        }

        try:
            gaps = inventory_gaps.get('gaps', [])
            if not gaps:
                return results

            from src.tool_synthesis.synthesizer import ToolSynthesizer
            from src.introspection_tools import IntrospectionToolRegistry

            if not hasattr(self.kloros, 'reason_backend'):
                print("[reflection] No reasoning backend for synthesis")
                return results

            # Create tool synthesizer with reasoning backend
            try:
                synthesizer = ToolSynthesizer(llm_callable=self.kloros.reason_backend)
            except Exception as e:
                print(f"[reflection] Failed to create tool synthesizer: {e}")
                return results

            registry = IntrospectionToolRegistry()

            # Prioritize gaps using reasoning-based VOI calculation
            try:
                from src.reasoning_coordinator import get_reasoning_coordinator
                coordinator = get_reasoning_coordinator()

                # Calculate VOI for each gap
                for gap in gaps:
                    gap['voi'] = coordinator.calculate_voi({
                        'action': f"Synthesize tool for {gap['capability']}",
                        'description': gap.get('description', ''),
                        'rationale': gap.get('rationale', ''),
                        'capability': gap['capability'],
                        'missing_tools': gap.get('missing_tools', [])
                    })

                # Sort by VOI (highest first)
                sorted_gaps = sorted(gaps, key=lambda g: g.get('voi', 0.0), reverse=True)
                print(f"[reflection] 🧠 Prioritized {len(gaps)} gaps via VOI reasoning")
                for i, gap in enumerate(sorted_gaps[:5], 1):
                    print(f"[reflection]   #{i}: {gap['capability']} (VOI: {gap.get('voi', 0.0):.3f})")

            except Exception as e:
                print(f"[reflection] ⚠️ Reasoning failed, using heuristic priority: {e}")
                # Fallback to original heuristic
                priority_order = ['mqtt', 'gpu', 'memory', 'dream', 'audio', 'agentflow', 'xai']
                sorted_gaps = sorted(gaps, key=lambda g: priority_order.index(g['capability']) if g['capability'] in priority_order else 999)

            # Synthesize up to 2 tools per reflection cycle
            tools_to_create = []
            for gap in sorted_gaps[:2]:  # Limit to 2 gaps per cycle
                missing_tools = gap.get('missing_tools', [])
                if missing_tools:
                    tools_to_create.append((missing_tools[0], gap))  # Take first missing tool

            for tool_name, gap in tools_to_create:
                # Skip if already exists
                if tool_name in registry.tools:
                    print(f"[reflection] Tool '{tool_name}' already exists")
                    continue

                print(f"[reflection] Synthesizing to bridge {gap['capability']}: {tool_name}")
                print(f"[reflection]   Rationale: {gap['rationale']}")

                results['attempted'] += 1

                # Build rich context about the capability
                context = f"{gap['description']} is available on this system. {gap['rationale']}. This tool should provide access to {gap['capability']} functionality."

                if synthesizer.capture_failed_tool_request(tool_name, context):
                    synthesized_tool = synthesizer.synthesize_tool(tool_name, context)

                    if synthesized_tool:
                        registry.register(synthesized_tool)
                        results['succeeded'] += 1
                        results['tools_created'].append({
                            'name': tool_name,
                            'capability': gap['capability'],
                            'description': gap['description']
                        })
                        print(f"[reflection] ✅ Bridged {gap['capability']}: {tool_name}")
                    else:
                        results['failed'] += 1
                        print(f"[reflection] ❌ Failed to bridge {gap['capability']}: {tool_name}")

        except Exception as e:
            print(f"[reflection] Inventory tool synthesis error: {e}")

        return results

    # Enhanced reflection convenience methods
    def _perform_capability_curiosity_cycle(self) -> Dict[str, Any]:
        """
        Phase 7: Capability-driven curiosity cycle.

        Evaluates all capabilities, generates questions from gaps, picks top question,
        and either runs D-REAM experiment or surfaces to user.

        Returns:
            Dict with status, questions_count, top_question, action_taken
        """
        try:
            from src.registry.capability_evaluator import CapabilityEvaluator
            from src.registry.curiosity_core import CuriosityCore
            import os

            # Step 1: Evaluate all capabilities
            print("[reflection][curiosity] Evaluating capabilities...")
            evaluator = CapabilityEvaluator()
            matrix = evaluator.evaluate_all()

            print(f"[reflection][curiosity] Status: {matrix.ok_count} OK, {matrix.degraded_count} degraded, {matrix.missing_count} missing")

            # Step 2: Generate curiosity questions from gaps
            curiosity = CuriosityCore()
            feed = curiosity.generate_questions_from_matrix(matrix)

            if not feed.questions:
                # No gaps found - all capabilities operational
                return {
                    "status": "completed",
                    "questions_count": 0,
                    "top_question": None,
                    "action_taken": "none"
                }

            # Step 3: Get top question by value/cost ratio
            top_questions = curiosity.get_top_questions(n=1)
            top_q = top_questions[0]

            result = {
                "status": "completed",
                "questions_count": len(feed.questions),
                "top_question": {
                    "id": top_q.id,
                    "question": top_q.question,
                    "hypothesis": top_q.hypothesis,
                    "capability_key": top_q.capability_key,
                    "action_class": top_q.action_class.value,
                    "value_cost_ratio": top_q.value_estimate / max(top_q.cost, 0.01),
                    "autonomy": top_q.autonomy
                }
            }

            # Step 4: Decide action based on question type and autonomy level
            action_class = top_q.action_class.value

            if action_class == "investigate":
                # Safe read-only investigation - can do autonomously
                print(f"[reflection][curiosity] Autonomous investigation: {top_q.capability_key}")
                self._investigate_capability_gap(top_q)
                result["action_taken"] = "investigating"

            elif action_class == "propose_fix" and top_q.autonomy == 2:
                # Autonomy level 2: propose to user, don't execute
                print(f"[reflection][curiosity] Surfacing fix proposal: {top_q.capability_key}")
                self._surface_capability_question_to_user(top_q)
                result["action_taken"] = "surfaced_to_user"

            elif action_class == "find_substitute":
                # Search for alternative capabilities autonomously
                print(f"[reflection][curiosity] Finding substitute for: {top_q.capability_key}")
                self._find_capability_substitute(top_q)
                result["action_taken"] = "finding_substitute"

            elif action_class == "request_user_action":
                # Requires user intervention (permissions, installation, etc.)
                print(f"[reflection][curiosity] Requesting user action: {top_q.capability_key}")
                self._surface_capability_question_to_user(top_q)
                result["action_taken"] = "surfaced_to_user"

            else:
                # Default: explain and soft-fallback
                print(f"[reflection][curiosity] Explaining gap and finding fallback: {top_q.capability_key}")
                self._explain_and_fallback(top_q)
                result["action_taken"] = "explain_fallback"

            # Step 5: Write artifacts for later analysis
            curiosity.write_feed_json()
            evaluator.write_state_json()

            # Step 6: Emit all questions as ChemBus signals for priority queue processing
            try:
                from src.orchestration.core.umn_bus import UMNPub as ChemPub
                from src.registry.question_prioritizer import QuestionPrioritizer

                chem_pub = ChemPub()
                prioritizer = QuestionPrioritizer(chem_pub)

                print(f"[reflection][curiosity] Emitting {len(feed.questions)} questions as ChemBus signals...")
                emitted_count = 0
                for q in feed.questions:
                    try:
                        prioritizer.prioritize_and_emit(q)
                        emitted_count += 1
                    except Exception as emit_err:
                        print(f"[reflection][curiosity] Failed to emit {q.id}: {emit_err}")

                print(f"[reflection][curiosity] Emitted {emitted_count} questions to priority queues")
                result["questions_emitted"] = emitted_count

            except Exception as e:
                print(f"[reflection][curiosity] Question emission failed: {e}")
                result["emission_error"] = str(e)

            return result

        except Exception as e:
            print(f"[reflection][curiosity] Capability curiosity cycle failed: {e}")
            import traceback
            traceback.print_exc()
            return {"status": "failed", "error": str(e)}

    def _perform_capability_curiosity_cycle_async(self) -> None:
        """
        Async wrapper for curiosity cycle to prevent watchdog timeout.

        Runs _perform_capability_curiosity_cycle() in background thread.
        This prevents the main thread from blocking during network requests
        and subprocess calls, which was causing systemd watchdog timeouts.

        FIX: Watchdog timeout issue - ASTRAEA Oct 26, 2025
        Root cause: Capability evaluator makes 12+ network requests with 3s timeouts.
        If network is slow, cumulative timeout can exceed 2min → watchdog kill.
        Solution: Run curiosity in daemon thread, main thread continues.
        """
        try:
            result = self._perform_capability_curiosity_cycle()

            # Log result but don't block main thread
            if result and result.get("status") == "completed":
                questions_count = result.get("questions_count", 0)
                print(f"[reflection][curiosity] Async cycle completed: {questions_count} questions generated")

                top_question = result.get("top_question")
                if top_question:
                    ratio = top_question.get("value_cost_ratio", 0)
                    question_text = top_question.get("question", "")
                    print(f"[reflection][curiosity] Top question [{ratio:.1f}]: {question_text[:80]}...")

                    # Log action taken
                    action = result.get("action_taken")
                    if action == "experiment_queued":
                        print("[reflection][curiosity] ✓ Queued D-REAM experiment")
                    elif action == "surfaced_to_user":
                        print("[reflection][curiosity] ✓ Surfaced question to user")
                    elif action == "investigating":
                        print("[reflection][curiosity] ✓ Running investigation probe")
            else:
                print("[reflection][curiosity] All capabilities operational - no curiosity questions")

        except Exception as e:
            print(f"[reflection][curiosity] Async cycle failed: {e}")
            import traceback
            traceback.print_exc()

    def _investigate_capability_gap(self, question) -> None:
        """
        Perform safe read-only investigation of capability gap.

        Autonomy Level 2: Safe probes only, no system modifications.
        """
        try:
            print(f"[reflection][curiosity] Investigating: {question.question}")

            # Run safe diagnostic probes
            capability_key = question.capability_key

            # Log investigation attempt
            investigation = {
                "timestamp": datetime.now().isoformat(),
                "capability": capability_key,
                "question": question.question,
                "hypothesis": question.hypothesis,
                "evidence": question.evidence,
                "probe_results": []
            }

            # Example safe probes based on capability type
            if "audio" in capability_key:
                # Check audio devices, permissions, environment
                import subprocess
                probes = [
                    ("groups", ["groups"]),
                    ("pactl_sinks", ["pactl", "list", "short", "sinks"]),
                    ("pactl_sources", ["pactl", "list", "short", "sources"]),
                    ("xdg_runtime", ["env"]),
                ]

                for probe_name, cmd in probes:
                    try:
                        result = subprocess.run(cmd, capture_output=True, text=True, timeout=5)
                        investigation["probe_results"].append({
                            "probe": probe_name,
                            "success": result.returncode == 0,
                            "output": result.stdout[:200] if result.returncode == 0 else result.stderr[:200]
                        })
                    except Exception as e:
                        investigation["probe_results"].append({
                            "probe": probe_name,
                            "success": False,
                            "error": str(e)[:100]
                        })

            # Handle undiscovered module investigations
            elif capability_key.startswith("undiscovered."):
                try:
                    # Extract module path from evidence
                    module_path = None
                    module_name = None
                    for ev in question.evidence:
                        if ev.startswith("path:"):
                            module_path = ev.split(":", 1)[1]
                            module_name = module_path.split("/")[-1]
                            break

                    if module_path:
                        investigation["probe_results"].append(self._inspect_discovered_module(module_path, module_name))

                        # If inspection succeeded, register the capability
                        if investigation["probe_results"] and investigation["probe_results"][-1].get("success"):
                            registration_result = self._register_discovered_capability(
                                module_name,
                                investigation["probe_results"][-1]
                            )
                            investigation["probe_results"].append(registration_result)
                    else:
                        investigation["probe_results"].append({
                            "probe": "module_extraction",
                            "success": False,
                            "error": "Could not extract module path from evidence"
                        })
                except Exception as e:
                    investigation["probe_results"].append({
                        "probe": "module_investigation",
                        "success": False,
                        "error": str(e)[:200]
                    })

            # Write investigation log
            import json
            from pathlib import Path
            log_path = Path("/home/kloros/.kloros/curiosity_investigations.jsonl")
            with open(log_path, "a") as f:
                f.write(json.dumps(investigation) + "\n")

            print(f"[reflection][curiosity] Investigation logged to {log_path}")

        except Exception as e:
            print(f"[reflection][curiosity] Investigation failed: {e}")

    def _surface_capability_question_to_user(self, question) -> None:
        """
        Surface capability question to user via alert system.

        Autonomy Level 2: Propose, don't execute.
        """
        try:
            # Check if alert system available
            if not hasattr(self.kloros, 'alert_manager') or not self.kloros.alert_manager:
                print("[reflection][curiosity] Alert system not available, skipping surface")
                return

            # Create user-friendly alert message
            alert_message = f"""
🔍 CURIOSITY QUESTION

I discovered a capability gap and have a question:

**Gap**: {question.capability_key}
**Question**: {question.question}
**Hypothesis**: {question.hypothesis}

**My Reasoning**:
{chr(10).join('  - ' + e for e in question.evidence)}

**Suggested Action**: {question.action_class.value}
**Risk Level**: {'Low' if question.cost < 0.3 else 'Medium' if question.cost < 0.6 else 'High'}

Would you like me to investigate this further?
"""

            # Log to curiosity surface attempts
            import json
            from pathlib import Path
            log_path = Path("/home/kloros/.kloros/curiosity_surface_log.jsonl")
            with open(log_path, "a") as f:
                f.write(json.dumps({
                    "timestamp": datetime.now().isoformat(),
                    "question_id": question.id,
                    "capability": question.capability_key,
                    "surfaced": True
                }) + "\n")

            print(f"[reflection][curiosity] ✓ Surfaced question about {question.capability_key}")

        except Exception as e:
            print(f"[reflection][curiosity] Failed to surface question: {e}")

    def _inspect_discovered_module(self, module_path: str, module_name: str) -> dict:
        """
        Inspect a discovered module to understand its capabilities.

        Args:
            module_path: Full path to module directory
            module_name: Name of the module

        Returns:
            Inspection results dictionary
        """
        from pathlib import Path
        import ast

        result = {
            "probe": "module_inspection",
            "success": False,
            "module_name": module_name,
            "module_path": module_path,
            "exports": [],
            "provides": [],
            "kind": "service",
            "error": None
        }

        try:
            # Read __init__.py to understand module structure
            init_file = Path(module_path) / "__init__.py"
            if not init_file.exists():
                result["error"] = f"No __init__.py found at {init_file}"
                return result

            init_content = init_file.read_text()

            # Parse AST to find exports
            try:
                tree = ast.parse(init_content)

                # Look for __all__ declaration
                for node in ast.walk(tree):
                    if isinstance(node, ast.Assign):
                        for target in node.targets:
                            if isinstance(target, ast.Name) and target.id == "__all__":
                                if isinstance(node.value, ast.List):
                                    result["exports"] = [
                                        elt.s if isinstance(elt, ast.Str) else elt.value
                                        for elt in node.value.elts
                                        if isinstance(elt, (ast.Str, ast.Constant))
                                    ]

                # If no __all__, look for imports
                if not result["exports"]:
                    for node in tree.body:
                        if isinstance(node, ast.ImportFrom):
                            if node.names:
                                result["exports"].extend([
                                    alias.name for alias in node.names
                                    if alias.name != '*'
                                ])
                        elif isinstance(node, ast.ClassDef):
                            result["exports"].append(node.name)
                        elif isinstance(node, ast.FunctionDef):
                            if not node.name.startswith('_'):
                                result["exports"].append(node.name)

            except Exception as parse_error:
                result["error"] = f"AST parse error: {parse_error}"
                return result

            # Infer capabilities based on module name and exports
            result["provides"] = self._infer_module_capabilities(module_name, result["exports"])
            result["kind"] = self._infer_module_kind(module_name, result["exports"])

            result["success"] = True
            print(f"[reflection][module_inspect] ✓ Inspected {module_name}: {len(result['exports'])} exports, provides {result['provides']}")

        except Exception as e:
            result["error"] = f"Inspection failed: {str(e)[:200]}"
            print(f"[reflection][module_inspect] ✗ Failed to inspect {module_name}: {e}")

        return result

    def _infer_module_capabilities(self, module_name: str, exports: list) -> list:
        """Infer what capabilities a module provides based on its name and exports."""
        provides = []

        # Module name patterns
        if "tool" in module_name or "synthesis" in module_name:
            provides.extend(["create_tool", "evolve_tool", "validate_tool"])
        if "audio" in module_name:
            provides.extend(["audio_processing", "sound_analysis"])
        if "config" in module_name:
            provides.extend(["configuration", "settings_management"])
        if "chroma" in module_name or "vector" in module_name:
            provides.extend(["vector_storage", "embedding_search"])
        if "inference" in module_name:
            provides.extend(["model_inference", "prediction"])

        # Export name patterns
        for export in exports:
            export_lower = export.lower()
            if "synthesiz" in export_lower:
                provides.append("code_generation")
            if "validator" in export_lower:
                provides.append("validation")
            if "storage" in export_lower or "store" in export_lower:
                provides.append("data_persistence")
            if "template" in export_lower:
                provides.append("templating")
            if "engine" in export_lower:
                provides.append("processing_engine")

        # Remove duplicates while preserving order
        seen = set()
        provides = [x for x in provides if not (x in seen or seen.add(x))]

        return provides if provides else ["utility_functions"]

    def _infer_module_kind(self, module_name: str, exports: list) -> str:
        """Infer module kind (service, tool, storage, etc.)."""

        if "storage" in module_name or "db" in module_name:
            return "storage"
        elif "tool" in module_name:
            return "tool"
        elif any("adapter" in e.lower() for e in exports):
            return "service"
        elif "config" in module_name:
            return "service"
        else:
            return "service"

    def _register_discovered_capability(self, module_name: str, inspection_results: dict) -> dict:
        """
        Register discovered module to capabilities_enhanced.yaml.

        Args:
            module_name: Name of the module
            inspection_results: Results from module inspection

        Returns:
            Registration result dictionary
        """
        from pathlib import Path
        import yaml

        result = {
            "probe": "capability_registration",
            "success": False,
            "capability_key": None,
            "error": None
        }

        try:
            # Generate capability key
            result["capability_key"] = f"module.{module_name}"

            # Load existing capabilities
            cap_file = Path("/home/kloros/src/registry/capabilities_enhanced.yaml")
            if not cap_file.exists():
                result["error"] = f"Capabilities file not found: {cap_file}"
                return result

            with open(cap_file, 'r') as f:
                capabilities = yaml.safe_load(f) or []

            # Check if already registered
            for cap in capabilities:
                if cap.get('key') == result["capability_key"]:
                    result["error"] = f"Capability {result['capability_key']} already registered"
                    result["success"] = True  # Not an error, just already done
                    return result

            # Create new capability entry
            new_capability = {
                "key": result["capability_key"],
                "kind": inspection_results.get("kind", "service"),
                "provides": inspection_results.get("provides", ["utility_functions"]),
                "preconditions": [
                    f"path:{inspection_results['module_path']}/__init__.py readable"
                ],
                "health_check": f"bash:test -f {inspection_results['module_path']}/__init__.py",
                "cost": {
                    "cpu": 5,
                    "mem": 256,
                    "risk": "low"
                },
                "tests": [],
                "docs": f"src/{module_name}/README.md",
                "enabled": True,
                "discovered_by": "curiosity_system",
                "discovery_timestamp": datetime.now().isoformat()
            }

            # Append new capability
            capabilities.append(new_capability)

            # Write back to file
            with open(cap_file, 'w') as f:
                yaml.dump(capabilities, f, default_flow_style=False, sort_keys=False)

            result["success"] = True
            print(f"[reflection][capability_reg] ✓ Registered {result['capability_key']} with {len(new_capability['provides'])} capabilities")

        except Exception as e:
            result["error"] = f"Registration failed: {str(e)[:200]}"
            print(f"[reflection][capability_reg] ✗ Failed to register {module_name}: {e}")

        return result

    def _find_capability_substitute(self, question) -> None:
        """
        Find alternative capabilities that can substitute for missing one.

        Autonomy Level 2: Search and propose, don't modify.
        """
        try:
            from src.registry.capability_evaluator import CapabilityEvaluator
            from src.registry.affordance_registry import AffordanceRegistry

            # Re-evaluate to get current state
            evaluator = CapabilityEvaluator()
            matrix = evaluator.evaluate_all()

            # Compute affordances to see what's available
            registry = AffordanceRegistry()
            registry.compute_affordances(matrix)

            # Check if any available capabilities provide similar affordances
            available = registry.get_available_affordances()
            unavailable = registry.get_unavailable_affordances()

            # Find the broken affordance
            capability_key = question.capability_key
            print(f"[reflection][curiosity] Searching for substitute for {capability_key}...")

            # Log the search
            import json
            from pathlib import Path
            log_path = Path("/home/kloros/.kloros/curiosity_substitutes.jsonl")
            with open(log_path, "a") as f:
                f.write(json.dumps({
                    "timestamp": datetime.now().isoformat(),
                    "missing_capability": capability_key,
                    "available_affordances": [a.name for a in available],
                    "unavailable_affordances": [a.name for a in unavailable]
                }) + "\n")

            print(f"[reflection][curiosity] ✓ Substitute search logged")

        except Exception as e:
            print(f"[reflection][curiosity] Substitute search failed: {e}")

    def _explain_and_fallback(self, question) -> None:
        """
        Explain capability gap and identify soft fallback.

        Autonomy Level 2: Inform user, suggest workaround.
        """
        try:
            print(f"[reflection][curiosity] Explaining gap: {question.capability_key}")

            # Log the explanation
            import json
            from pathlib import Path
            log_path = Path("/home/kloros/.kloros/curiosity_explanations.jsonl")
            with open(log_path, "a") as f:
                f.write(json.dumps({
                    "timestamp": datetime.now().isoformat(),
                    "capability": question.capability_key,
                    "question": question.question,
                    "hypothesis": question.hypothesis,
                    "explanation": "Capability gap identified, fallback strategy available"
                }) + "\n")

            print(f"[reflection][curiosity] ✓ Explanation logged")

        except Exception as e:
            print(f"[reflection][curiosity] Explanation failed: {e}")

    def get_reflection_statistics(self) -> Dict[str, Any]:
        """Get comprehensive reflection system statistics."""
        if self.use_enhanced and self.enhanced_manager:
            return self.enhanced_manager.get_reflection_statistics()
        else:
            return {
                "system_type": "basic",
                "reflection_interval": self.reflection_interval,
                "enhanced_available": ENHANCED_AVAILABLE,
                "note": "Basic reflection system - limited statistics available"
            }

    def reload_configuration(self) -> bool:
        """Reload reflection configuration."""
        if self.use_enhanced and self.enhanced_manager:
            return self.enhanced_manager.reload_configuration()
        else:
            print("[reflection] Configuration reload not supported in basic mode")
            return False

    def is_enhanced(self) -> bool:
        """Check if enhanced reflection system is active."""
        return self.use_enhanced and self.enhanced_manager is not None

    def get_system_info(self) -> Dict[str, Any]:
        """Get information about the reflection system."""
        info = {
            "enhanced_available": ENHANCED_AVAILABLE,
            "using_enhanced": self.use_enhanced,
            "reflection_interval": self.reflection_interval,
            "reflection_log_path": self.reflection_log_path
        }

        if self.use_enhanced and hasattr(self, 'config'):
            info.update({
                "analysis_depth": self.config.reflection_depth,
                "semantic_analysis": self.config.enable_semantic_analysis,
                "meta_cognition": self.config.enable_meta_cognition,
                "insight_synthesis": self.config.enable_insight_synthesis,
                "adaptive_optimization": self.config.enable_adaptive_optimization,
                "llm_model": self.config.ollama_model
            })

        return info

    # =========================================================================
    # Hybrid Introspection Interface Methods
    # =========================================================================

    def start_conversation_introspection(self, conversation_id: str) -> None:
        """Start real-time introspection for a new conversation."""
        if self.use_enhanced and self.enhanced_manager:
            self.enhanced_manager.start_conversation_introspection(conversation_id)

    def analyze_user_input(self, user_input: str):
        """Analyze user input for real-time insights and adaptive parameters."""
        if self.use_enhanced and self.enhanced_manager:
            insights = self.enhanced_manager.analyze_user_input(user_input)
            adaptive_params = self.enhanced_manager.get_adaptive_parameters()
            return {
                "insights": insights,
                "adaptive_parameters": adaptive_params
            }
        return {"insights": [], "adaptive_parameters": {}}

    def analyze_response_quality(self, response: str, response_time_ms: float):
        """Analyze generated response quality for real-time optimization."""
        if self.use_enhanced and self.enhanced_manager:
            insights = self.enhanced_manager.analyze_response_quality(response, response_time_ms)
            adaptive_params = self.enhanced_manager.get_adaptive_parameters()
            return {
                "insights": insights,
                "adaptive_parameters": adaptive_params
            }
        return {"insights": [], "adaptive_parameters": {}}

    def get_adaptive_parameters(self):
        """Get current adaptive parameters for real-time optimization."""
        if self.use_enhanced and self.enhanced_manager:
            return self.enhanced_manager.get_adaptive_parameters()
        return {}

    def end_conversation_introspection(self):
        """End conversation introspection and get summary."""
        if self.use_enhanced and self.enhanced_manager:
            return self.enhanced_manager.end_conversation_introspection()
        return {}

    def get_hybrid_statistics(self):
        """Get comprehensive statistics including hybrid introspection."""
        if self.use_enhanced and self.enhanced_manager:
            return self.enhanced_manager.get_hybrid_statistics()
        return self.get_reflection_statistics()

    def _synthesize_missing_tools(self, missing_tools: list, system_map: Dict[str, Any]):
        """Proactively synthesize missing tools identified in gap analysis.

        Args:
            missing_tools: List of tool gaps from system mapping
            system_map: Complete system map for context
        """
        if not missing_tools:
            return

        try:
            from src.tool_synthesis import ToolSynthesizer

            synthesizer = ToolSynthesizer(self.kloros)
            synthesized_count = 0

            for gap in missing_tools[:3]:  # Limit to 3 tools per reflection cycle
                subsystem = gap.get("subsystem", "unknown")
                description = gap.get("description", "")
                priority = gap.get("priority", "medium")

                if priority == "low":
                    continue  # Skip low priority during idle reflection

                tool_name = f"{subsystem}_status"
                print(f"[reflection] Attempting to synthesize: {tool_name}")

                # Build context for synthesis
                context = {
                    "subsystem": subsystem,
                    "description": description,
                    "system_map": system_map,
                    "purpose": "introspection and monitoring"
                }

                # Attempt synthesis
                if synthesizer.capture_failed_tool_request(tool_name, context=str(context)):
                    tool = synthesizer.synthesize_tool(tool_name, context=str(context))

                    if tool:
                        # Register the tool
                        if hasattr(self.kloros, 'tool_registry'):
                            self.kloros.tool_registry.register(tool)
                            synthesized_count += 1
                            print(f"[reflection] ✓ Synthesized and registered: {tool_name}")

            if synthesized_count > 0:
                print(f"[reflection] Successfully synthesized {synthesized_count} missing tools")

        except Exception as e:
            print(f"[reflection] Tool synthesis failed: {e}")

    def cleanup(self):
        """Clean up resources and close database connections."""
        try:
            # Close enhanced manager if present
            if hasattr(self, 'enhanced_manager') and self.enhanced_manager:
                # Enhanced manager analyzers may have connections
                if hasattr(self.enhanced_manager, 'semantic_analyzer'):
                    # Semantic analyzer doesn't maintain persistent connections, but good practice
                    pass
                if hasattr(self.enhanced_manager, 'meta_cognitive_analyzer'):
                    # Meta-cognitive analyzer doesn't maintain persistent connections
                    pass

            # If kloros has memory_enhanced, ensure it's closed properly
            if hasattr(self.kloros, 'memory_enhanced') and self.kloros.memory_enhanced:
                # Memory system will be cleaned up by its own cleanup mechanism
                pass

            print("[reflection] Cleanup complete")
        except Exception as e:
            print(f"[reflection] Cleanup error: {e}")
    def _run_autonomous_chaos_test(self):
        """Run an autonomous chaos test and feed results to D-REAM."""
        from datetime import datetime
        print(f"\n{'='*70}")
        print(f"[reflection→chaos] AUTONOMOUS CHAOS TEST TRIGGERED at {datetime.now().strftime('%H:%M:%S')}")
        print(f"{'='*70}\n")

        try:
            from src.introspection_tools import IntrospectionToolRegistry

            registry = IntrospectionToolRegistry()

            # Use the auto_chaos_test tool
            if 'auto_chaos_test' in registry.tools:
                print("[reflection→chaos] Selecting and running chaos scenario...")

                # Run the test and get the raw result
                result_str = registry.tools['auto_chaos_test'].func(self.kloros)

                # Get the last chaos result for feeding to D-REAM
                import json
                from pathlib import Path

                history_file = Path("/home/kloros/.kloros/chaos_history.jsonl")
                if history_file.exists():
                    # Read last line (most recent test)
                    with open(history_file, 'r') as f:
                        lines = f.readlines()
                        if lines:
                            last_result = json.loads(lines[-1])
                            score = last_result.get('score', 0)
                            healed = last_result.get('outcome', {}).get('healed', False)

                            print(f"[reflection→chaos] Test complete: score={score}/100, healed={healed}")

                            # Actually feed to D-REAM (not just print!)
                            if hasattr(registry, '_feed_to_dream'):
                                registry._feed_to_dream(self.kloros, last_result)
                            else:
                                # Call it directly from introspection tools
                                from src.introspection_tools import IntrospectionToolRegistry
                                reg = IntrospectionToolRegistry()
                                if hasattr(reg, '_feed_to_dream'):
                                    reg._feed_to_dream(self.kloros, last_result)

                            # Trigger D-REAM analysis if score is problematic
                            if score < 70:
                                print(f"[reflection→chaos] Low healing score detected - flagging for D-REAM optimization")
                                self._trigger_chaos_analysis(last_result)

            else:
                print("[reflection→chaos] auto_chaos_test tool not available")

        except Exception as e:
            print(f"[reflection→chaos] Chaos test failed: {e}")
            import traceback
            traceback.print_exc()

    def _trigger_chaos_analysis(self, chaos_result):
        """Trigger D-REAM analysis based on chaos test weakness."""
        from datetime import datetime
        print(f"\n[reflection→chaos→dream] TRIGGERING D-REAM ANALYSIS")

        try:
            from src.shared_dream_instance import SharedDreamManager

            score = chaos_result.get('score', 0)
            target = chaos_result.get('spec_id', 'unknown')
            mttr = chaos_result.get('outcome', {}).get('duration_s', 0)
            healed = chaos_result.get('outcome', {}).get('healed', False)

            print(f"[reflection→chaos→dream] Weakness detected: {target} (score={score}, healed={healed})")

            # Create improvement opportunity for D-REAM
            improvement = {
                "task_id": f"chaos_weakness_{target}_{int(datetime.now().timestamp())}",
                "component": f"self_healing.{target.split('_')[0] if '_' in target else 'general'}",
                "description": f"Improve healing response for {target} scenario (current score: {score}/100, MTTR: {mttr:.1f}s, healed: {healed})",
                "expected_benefit": f"Target: >80/100 score, <{mttr*0.5:.1f}s MTTR for {target} scenarios",
                "risk_level": "low",  # Improving healing is low risk
                "confidence": 0.85,  # High confidence - we have real test data
                "urgency": "medium" if score < 50 else "low",
                "detected_at": datetime.now().isoformat(),
                "source": "chaos_lab",
                "fitness_data": {
                    "score": score,
                    "mttr": mttr,
                    "healed": healed,
                    "scenario": target
                }
            }

            # Inject into shared D-REAM system
            print(f"[reflection→chaos→dream] Creating SharedDreamManager instance...")
            shared_dream = SharedDreamManager()

            print(f"[reflection→chaos→dream] Injecting improvement: {improvement['task_id']}")
            success = shared_dream.inject_improvement(improvement)

            if success:
                print(f"[reflection→chaos→dream] ✅ SUCCESSFULLY INJECTED: {improvement['task_id']}")
                print(f"[reflection→chaos→dream] ✅ Pending improvements: {shared_dream.get_pending_count()}")
            else:
                print(f"[reflection→chaos→dream] ⚠️ INJECTION FAILED")

            # Also POST to the new D-REAM dashboard API
            self._post_to_dashboard_api(improvement, score, target, mttr, healed)

        except Exception as e:
            print(f"[reflection→chaos→dream] ❌ Error triggering analysis: {e}")
            import traceback
            traceback.print_exc()

    def _post_to_dashboard_api(self, improvement, score, target, mttr, healed):
        """POST improvement to the FastAPI D-REAM dashboard."""
        try:
            import os
            import requests

            # Check if dashboard URL is configured
            dashboard_url = os.getenv("DREAM_DASHBOARD_URL", "http://127.0.0.1:8080")
            auth_token = os.getenv("DREAM_AUTH_TOKEN", "dev-token-change-me")

            # Format for FastAPI dashboard
            payload = {
                "title": f"Healing weakness: {target}",
                "description": improvement['description'],
                "domain": improvement['component'],
                "score": score,
                "meta": {
                    "mttr": mttr,
                    "healed": healed,
                    "scenario": target,
                    "source": "chaos_lab",
                    "expected_benefit": improvement['expected_benefit'],
                    "risk_level": improvement['risk_level'],
                    "confidence": improvement['confidence'],
                    "urgency": improvement['urgency']
                }
            }

            headers = {
                "Authorization": f"Bearer {auth_token}",
                "Content-Type": "application/json"
            }

            print(f"[reflection→chaos→dashboard] POSTing to {dashboard_url}/api/improvements")
            response = requests.post(
                f"{dashboard_url}/api/improvements",
                json=payload,
                headers=headers,
                timeout=5
            )

            if response.status_code == 200:
                result = response.json()
                print(f"[reflection→chaos→dashboard] ✅ Dashboard accepted improvement (ID: {result.get('id')})")
            else:
                print(f"[reflection→chaos→dashboard] ⚠️ Dashboard returned {response.status_code}: {response.text}")

        except requests.exceptions.ConnectionError:
            print(f"[reflection→chaos→dashboard] ⚠️ Dashboard not reachable (not running?)")
        except Exception as e:
            print(f"[reflection→chaos→dashboard] ⚠️ Failed to POST to dashboard: {e}")

    def _enrich_improvement_proposals(self):
        """
        Enrich pending improvement proposals with concrete solutions.

        Uses deep reasoning (ToT/Debate) to generate solutions for proposals
        that only identify problems without providing fixes.

        This closes the architectural gap where proposals couldn't be
        auto-deployed because they lacked proposed_change field.
        """
        try:
            from src.dream.proposal_enricher import get_proposal_enricher

            print(f"\n[reflection→enricher] Checking for proposals needing solutions...")

            enricher = get_proposal_enricher(self.kloros)
            enriched_count = enricher.enrich_pending_proposals(max_proposals=2)

            if enriched_count > 0:
                print(f"[reflection→enricher] ✅ Generated solutions for {enriched_count} proposals")
                print(f"[reflection→enricher] Proposals now ready for D-REAM validation & auto-deployment")
            else:
                print(f"[reflection→enricher] No proposals needed enrichment")

        except Exception as e:
            print(f"[reflection→enricher] ⚠️ Enrichment failed: {e}")
            import traceback
            traceback.print_exc()
