"""
Central coordinator for D-REAM alert system.
Manages alert routing, delivery, and user responses.
"""

import re
import json
from datetime import datetime
from typing import Dict, List, Any, Optional
from .alert_methods import AlertMethod, AlertResult, ImprovementAlert, AlertQueue, AlertHistory
from .alert_preferences import UserAlertPreferences

# Import deployment pipeline
try:
    from .deployment_pipeline import ImprovementDeployer, DeploymentResult
    DEPLOYMENT_AVAILABLE = True
except ImportError as e:
    print(f"[alerts] Deployment pipeline not available: {e}")
    DEPLOYMENT_AVAILABLE = False

# Import reasoning coordinator for auto-approval decisions
try:
    from src.reasoning_coordinator import get_reasoning_coordinator, ReasoningMode
    REASONING_AVAILABLE = True
except ImportError as e:
    print(f"[alerts] Reasoning coordinator not available: {e}")
    REASONING_AVAILABLE = False


class DreamAlertManager:
    """Central coordinator for all D-REAM improvement alerts."""

    def __init__(self):
        self.alert_methods: Dict[str, AlertMethod] = {}
        self.user_preferences = UserAlertPreferences()
        self.alert_queue = AlertQueue()
        self.alert_history = AlertHistory()
        self.active = True

        # Initialize deployment pipeline if available
        self.deployer = None
        if DEPLOYMENT_AVAILABLE:
            try:
                self.deployer = ImprovementDeployer()
                print("[alerts] D-REAM Alert Manager initialized with deployment pipeline")
            except Exception as e:
                print(f"[alerts] Failed to initialize deployment pipeline: {e}")
                print("[alerts] D-REAM Alert Manager initialized (deployment disabled)")
        else:
            print("[alerts] D-REAM Alert Manager initialized (deployment not available)")

    def notify_improvement_ready(self, improvement: Dict[str, Any]) -> Dict[str, Any]:
        """
        Main entry point: process new improvement and route alerts.

        Args:
            improvement: Improvement dictionary from D-REAM system

        Returns:
            Dict with routing results and delivery status
        """
        if not self.active or not self.user_preferences.is_alerts_enabled():
            return {"status": "disabled", "reason": "Alert system disabled"}

        # D-REAM-AntiFabrication: Validate improvement has implementation data
        has_implementation = (
            improvement.get('apply_map') or
            improvement.get('params') or
            improvement.get('code') or
            improvement.get('changes')
        )

        if not has_implementation:
            task_id = improvement.get('task_id', 'unknown')
            print(f"[alerts] ⚠️ Rejecting improvement without implementation: {task_id}")
            print(f"[alerts] Missing: apply_map, params, code, and changes")
            return {
                "status": "rejected",
                "reason": "Improvement missing implementation data (no apply_map/params/code/changes)",
                "task_id": task_id,
                "anti_fabrication": "Prevented hallucinated improvement from reaching approval"
            }

        print(f"[alerts] Processing improvement: {improvement.get('task_id', 'unknown')}")

        # Create alert from improvement
        alert = ImprovementAlert.from_improvement(improvement)

        # Check if this improvement qualifies for auto-approval
        auto_approval_result = self._check_auto_approval(alert, improvement)
        if auto_approval_result["auto_approved"]:
            print(f"[alerts] 🤖 Auto-approved improvement {alert.request_id}")
            return auto_approval_result

        # Otherwise, add to queue for manual approval
        self.alert_queue.add_alert(alert)

        # Determine routing based on urgency and preferences
        selected_methods = self._route_alert(alert)

        # Attempt delivery through selected methods
        results = self._deliver_alert(alert, selected_methods)

        # Handle results and fallbacks
        final_result = self._process_delivery_results(alert, results)

        return {
            "status": "processed",
            "alert_id": alert.request_id,
            "urgency": alert.urgency,
            "methods_attempted": len(selected_methods),
            "delivery_results": results,
            "final_status": final_result
        }

    def _check_auto_approval(self, alert: ImprovementAlert, improvement: Dict[str, Any]) -> Dict[str, Any]:
        """
        Check if improvement qualifies for automatic approval and deployment.

        Auto-approval criteria:
        - Risk level: low or medium
        - Confidence: >= 0.6 (60%)
        - Component: performance optimizations, tool refinements, documentation
        - NOT critical infrastructure changes

        Args:
            alert: ImprovementAlert object
            improvement: Original improvement dict

        Returns:
            Dict with auto_approved status and deployment results if approved
        """
        # Get auto-approval settings from preferences
        auto_approve_enabled = self.user_preferences.preferences.get("auto_approval", {}).get("enabled", True)

        if not auto_approve_enabled:
            return {"auto_approved": False, "reason": "Auto-approval disabled in preferences"}

        # Use reasoning-based decision if available, otherwise fall back to heuristics
        if REASONING_AVAILABLE:
            try:
                coordinator = get_reasoning_coordinator()

                # Prepare decision context for multi-agent debate
                proposed_decision = {
                    'action': 'auto_deploy_improvement',
                    'improvement_id': alert.request_id,
                    'component': alert.component,
                    'description': alert.description,
                    'rationale': alert.expected_benefit,
                    'confidence': alert.confidence,
                    'risk_level': alert.risk_level,
                    'urgency': alert.urgency,
                    'risks': [
                        f"Component affected: {alert.component}",
                        f"Risk level: {alert.risk_level}",
                        f"Confidence: {alert.confidence:.2%}",
                        "No human review before deployment",
                        "Auto-rollback available if validation fails"
                    ]
                }

                # Use multi-agent debate for safety-critical deployment decision
                debate_result = coordinator.debate_decision(
                    context="Should this improvement be auto-approved and deployed?",
                    proposed_decision=proposed_decision,
                    rounds=2  # Two rounds of debate for safety
                )

                verdict = debate_result.get('verdict', {})
                decision = verdict.get('verdict', 'rejected')
                reasoning = verdict.get('reasoning', 'No reasoning provided')
                confidence = verdict.get('confidence', 0.0)

                print(f"[alerts] 🧠 Reasoning-based auto-approval decision for {alert.request_id}:")
                print(f"[alerts]    Decision: {decision}, Confidence: {confidence:.2f}")
                print(f"[alerts]    Reasoning: {reasoning}")

                if decision == 'approved':
                    print(f"[alerts] ✅ Auto-approval approved via multi-agent debate")
                else:
                    return {
                        "auto_approved": False,
                        "reason": f"Rejected by multi-agent debate: {reasoning}"
                    }

            except Exception as e:
                print(f"[alerts] ⚠️ Reasoning failed, falling back to heuristics: {e}")
                # Fall through to heuristic logic below

        # Fallback heuristic logic if reasoning unavailable or failed
        if not REASONING_AVAILABLE:
            print(f"[alerts] Using heuristic auto-approval (reasoning unavailable)")

            # Safety criteria for auto-approval
            safe_risk_levels = ["low", "medium"]
            min_confidence = 0.6

            # Critical components that require manual review
            critical_components = [
                "security", "authentication", "authorization", "encryption",
                "kernel", "core", "bootstrap", "init", "systemd"
            ]

            # Check risk level
            if alert.risk_level not in safe_risk_levels:
                return {
                    "auto_approved": False,
                    "reason": f"Risk level '{alert.risk_level}' requires manual approval"
                }

            # Check confidence threshold
            if alert.confidence < min_confidence:
                return {
                    "auto_approved": False,
                    "reason": f"Confidence {alert.confidence:.2f} below threshold {min_confidence}"
                }

            # Check component safety
            component_lower = alert.component.lower()

            # Reject critical components
            if any(crit in component_lower for crit in critical_components):
                return {
                    "auto_approved": False,
                    "reason": f"Critical component '{alert.component}' requires manual approval"
                }

            print(f"[alerts] ✅ Heuristic auto-approval criteria met for {alert.request_id}:")
            print(f"[alerts]    Risk: {alert.risk_level}, Confidence: {alert.confidence:.2f}, Component: {alert.component}")

        # Auto-approve and deploy immediately
        if self.deployer:
            print(f"[alerts] 🚀 Auto-deploying improvement {alert.request_id}")

            # Convert alert to improvement data format
            improvement_data = {
                "request_id": alert.request_id,
                "component": alert.component,
                "description": alert.description,
                "expected_benefit": alert.expected_benefit,
                "risk_level": alert.risk_level,
                "confidence": alert.confidence,
                "urgency": alert.urgency,
                "detected_at": alert.detected_at.isoformat()
            }

            try:
                deployment_result = self.deployer.deploy_improvement(improvement_data)

                if deployment_result.success:
                    print(f"[alerts] ✅ Auto-deployed {alert.request_id} successfully")

                    # Record in history
                    self.alert_history.record_deployment(alert.request_id, deployment_result, True)

                    # Log for informational reporting
                    self._log_auto_deployment(alert, deployment_result)

                    return {
                        "auto_approved": True,
                        "status": "deployed",
                        "request_id": alert.request_id,
                        "message": f"Auto-approved and deployed: {alert.description}",
                        "deployment_status": "completed",
                        "changes_applied": deployment_result.changes_applied,
                        "backup_path": deployment_result.backup_path,
                        "reason": "Met auto-approval criteria (low risk, high confidence)"
                    }
                else:
                    print(f"[alerts] ❌ Auto-deployment failed for {alert.request_id}: {deployment_result.error_message}")

                    # Record failed deployment
                    self.alert_history.record_deployment(alert.request_id, deployment_result, False)

                    # Fall back to manual approval flow
                    return {
                        "auto_approved": False,
                        "reason": f"Auto-deployment failed: {deployment_result.error_message}. Falling back to manual approval."
                    }

            except Exception as e:
                print(f"[alerts] 💥 Auto-deployment exception for {alert.request_id}: {e}")

                # Fall back to manual approval on exception
                return {
                    "auto_approved": False,
                    "reason": f"Auto-deployment crashed: {str(e)}. Falling back to manual approval."
                }
        else:
            # No deployer available - queue for manual approval
            return {
                "auto_approved": False,
                "reason": "Deployment pipeline unavailable, requires manual approval"
            }

    def _log_auto_deployment(self, alert: ImprovementAlert, deployment_result) -> None:
        """
        Log auto-deployed improvement for informational reporting.

        This allows KLoROS to report what she's done during conversations.
        """
        log_entry = {
            "timestamp": datetime.now().isoformat(),
            "request_id": alert.request_id,
            "component": alert.component,
            "description": alert.description,
            "expected_benefit": alert.expected_benefit,
            "confidence": alert.confidence,
            "risk_level": alert.risk_level,
            "changes_applied": deployment_result.changes_applied if hasattr(deployment_result, 'changes_applied') else [],
            "backup_path": deployment_result.backup_path if hasattr(deployment_result, 'backup_path') else None,
            "deployment_type": "auto_approved"
        }

        # Save to auto-deployment log
        from pathlib import Path
        log_file = Path("/home/kloros/.kloros/auto_deployments.jsonl")
        log_file.parent.mkdir(parents=True, exist_ok=True)

        try:
            with open(log_file, 'a') as f:
                f.write(json.dumps(log_entry) + "\n")
            print(f"[alerts] 📝 Logged auto-deployment to {log_file}")
        except Exception as e:
            print(f"[alerts] ⚠️ Failed to log auto-deployment: {e}")

    def register_alert_method(self, name: str, method: AlertMethod) -> None:
        """Register new alert delivery method."""
        self.alert_methods[name] = method
        print(f"[alerts] Registered method: {name}")

    def _route_alert(self, alert: ImprovementAlert) -> List[AlertMethod]:
        """Determine which alert methods to use based on improvement and preferences."""

        # Get preferred methods for this urgency level
        preferred_method_names = self.user_preferences.get_routing_for_urgency(alert.urgency)

        selected_methods = []

        for method_name in preferred_method_names:
            method = self.alert_methods.get(method_name)

            if method and method.can_deliver_now():
                selected_methods.append(method)
                print(f"[alerts] Selected method: {method_name} for {alert.urgency} urgency")
            else:
                if method:
                    print(f"[alerts] Method {method_name} unavailable, skipping")
                else:
                    print(f"[alerts] Method {method_name} not registered")

        # Ensure at least passive method is available
        if not selected_methods and "passive" in self.alert_methods:
            passive_method = self.alert_methods["passive"]
            if passive_method.can_deliver_now():
                selected_methods.append(passive_method)
                print("[alerts] Using passive method as fallback")

        return selected_methods

    def _deliver_alert(self, alert: ImprovementAlert, methods: List[AlertMethod]) -> List[AlertResult]:
        """Attempt to deliver alert through selected methods."""
        results = []

        for method in methods:
            try:
                print(f"[alerts] Attempting delivery via {method.get_method_name()}")
                result = method.deliver_alert(alert)
                results.append(result)

                # Record delivery attempt
                self.alert_history.record_delivery(alert, result)

                if result.success:
                    print(f"[alerts] ✓ Successful delivery via {result.method}")
                else:
                    print(f"[alerts] ✗ Failed delivery via {result.method}: {result.reason}")

            except Exception as e:
                error_result = AlertResult(
                    success=False,
                    method=method.get_method_name(),
                    error=str(e),
                    reason="Exception during delivery"
                )
                results.append(error_result)
                self.alert_history.record_delivery(alert, error_result)

                print(f"[alerts] ✗ Exception in {method.get_method_name()}: {e}")

        return results

    def _process_delivery_results(self, alert: ImprovementAlert, results: List[AlertResult]) -> str:
        """Process delivery results and handle fallbacks."""

        successful_deliveries = [r for r in results if r.success]
        failed_deliveries = [r for r in results if not r.success]

        if successful_deliveries:
            # At least one delivery succeeded
            if len(successful_deliveries) == len(results):
                return "all_successful"
            else:
                return "partial_success"
        else:
            # All deliveries failed - need fallback
            print(f"[alerts] All delivery methods failed for {alert.request_id}")

            # Try passive method as ultimate fallback
            if "passive" in self.alert_methods:
                passive_method = self.alert_methods["passive"]
                if passive_method.can_deliver_now():
                    try:
                        fallback_result = passive_method.deliver_alert(alert)
                        self.alert_history.record_delivery(alert, fallback_result)

                        if fallback_result.success:
                            print("[alerts] ✓ Fallback to passive method successful")
                            return "fallback_successful"
                        else:
                            print("[alerts] ✗ Even fallback method failed")
                            return "complete_failure"

                    except Exception as e:
                        print(f"[alerts] ✗ Fallback method exception: {e}")
                        return "complete_failure"

            return "complete_failure"

    def process_user_response(self, response: str, channel: str) -> Dict[str, Any]:
        """
        Handle user approval/rejection responses from any channel.

        Args:
            response: User response text
            channel: Channel the response came from (voice, web, mobile, etc.)

        Returns:
            Dict with processing results
        """
        print(f"[alerts] Processing user response from {channel}: {response}")

        # Parse response for approval commands
        parsed = self._parse_user_response(response)

        if parsed.get("action") == "unknown":
            return {
                "success": False,
                "error": "Could not parse response",
                "suggestion": "Try 'APPROVE', 'REJECT', 'EXPLAIN', or 'STATUS' (you can also specify 'APPROVE LATEST' or 'APPROVE 1')"
            }

        # Record response in history
        request_id = parsed.get("request_id", "unknown")
        action = parsed.get("action")

        self.alert_history.record_response(request_id, response, action)

        # Handle the response based on action
        if action in ["approve", "reject"]:
            return self._handle_approval_response(parsed, channel)
        elif action == "explain":
            return self._handle_explain_request(parsed, channel)
        elif action == "status":
            return self._handle_status_request(channel)
        else:
            return {"success": False, "error": f"Unknown action: {action}"}

    def _parse_user_response(self, response: str) -> Dict[str, Any]:
        """Parse user response for alert actions."""
        response_lower = response.lower().strip()

        # Helper function to resolve request_id from various input formats
        def resolve_request_id(identifier: str) -> Optional[str]:
            """
            Resolve identifier to actual request_id.
            Supports: 'latest', 'last', numeric index (1,2,3), partial match, full ID
            """
            if not self.alert_queue.pending:
                return None

            # Latest/last - most recent alert
            if identifier in ["latest", "last"]:
                return self.alert_queue.pending[-1].request_id

            # Numeric index (1-based, as shown to user)
            if identifier.isdigit():
                idx = int(identifier) - 1  # Convert to 0-based
                if 0 <= idx < len(self.alert_queue.pending):
                    return self.alert_queue.pending[idx].request_id
                return None

            # Exact match
            for alert in self.alert_queue.pending:
                if alert.request_id == identifier:
                    return alert.request_id

            # Partial match (case-insensitive substring)
            matches = [a for a in self.alert_queue.pending
                      if identifier.lower() in a.request_id.lower()]
            if len(matches) == 1:
                return matches[0].request_id
            elif len(matches) > 1:
                # Multiple matches - ambiguous
                return None

            return None

        # Approval patterns - now supporting latest/last/numeric/no-ID and past-tense
        approval_patterns = [
            r"approved?\s+evolution\s+(.+)",
            r"yes,?\s*approved?\s+(.+)",
            r"go\s+ahead\s+with\s+(.+)",
            r"implemented?\s+(.+)",
            r"approved?\s+(.+)"
        ]

        for pattern in approval_patterns:
            match = re.search(pattern, response_lower)
            if match:
                identifier = match.group(1).strip()
                resolved_id = resolve_request_id(identifier)

                if resolved_id:
                    return {
                        "action": "approve",
                        "request_id": resolved_id,
                        "confidence": 0.9,
                        "user_input": identifier
                    }
                else:
                    return {
                        "action": "approve",
                        "request_id": identifier,  # Keep original for error message
                        "confidence": 0.5,
                        "user_input": identifier,
                        "resolution_failed": True
                    }

        # ID-less approval patterns (default to most recently presented/latest)
        # Includes natural responses to "Would you like to hear..." questions
        if re.match(r"^(approved?|yes|accepted?|ok|okay|do it|sure|yeah|yep|please|go ahead|let'?s hear it|tell me|share|show me)$", response_lower):
            resolved_id = resolve_request_id("latest")
            if resolved_id:
                return {
                    "action": "approve",
                    "request_id": resolved_id,
                    "confidence": 0.95,
                    "user_input": "latest",
                    "defaulted_to_latest": True
                }

        # Rejection patterns - now supporting latest/last/numeric/no-ID and past-tense
        rejection_patterns = [
            r"rejected?\s+evolution\s+(.+)",
            r"no,?\s*rejected?\s+(.+)",
            r"skipped?\s+(.+)",
            r"don'?t\s+implemented?\s+(.+)",
            r"rejected?\s+(.+)",
            r"declined?\s+(.+)"
        ]

        for pattern in rejection_patterns:
            match = re.search(pattern, response_lower)
            if match:
                identifier = match.group(1).strip()
                resolved_id = resolve_request_id(identifier)

                if resolved_id:
                    return {
                        "action": "reject",
                        "request_id": resolved_id,
                        "confidence": 0.9,
                        "user_input": identifier
                    }
                else:
                    return {
                        "action": "reject",
                        "request_id": identifier,
                        "confidence": 0.5,
                        "user_input": identifier,
                        "resolution_failed": True
                    }

        # ID-less rejection patterns (default to most recently presented/latest)
        if re.match(r"^(rejected?|declined?|no|skipped?|nope|don'?t|cancel|cancelled)$", response_lower):
            resolved_id = resolve_request_id("latest")
            if resolved_id:
                return {
                    "action": "reject",
                    "request_id": resolved_id,
                    "confidence": 0.95,
                    "user_input": "latest",
                    "defaulted_to_latest": True
                }

        # Explanation request patterns - now supporting latest/last/numeric/no-ID
        explain_patterns = [
            r"explain\s+evolution\s+(.+)",
            r"tell\s+me\s+more\s+about\s+(.+)",
            r"details\s+about\s+(.+)",
            r"explain\s+(.+)",
            r"what\s+is\s+(.+)"
        ]

        for pattern in explain_patterns:
            match = re.search(pattern, response_lower)
            if match:
                identifier = match.group(1).strip()
                resolved_id = resolve_request_id(identifier)

                if resolved_id:
                    return {
                        "action": "explain",
                        "request_id": resolved_id,
                        "confidence": 0.8,
                        "user_input": identifier
                    }

        # ID-less explanation patterns (default to most recently presented/latest)
        if re.match(r"^(explain|details|tell me more|what is it|more info)$", response_lower):
            resolved_id = resolve_request_id("latest")
            if resolved_id:
                return {
                    "action": "explain",
                    "request_id": resolved_id,
                    "confidence": 0.85,
                    "user_input": "latest",
                    "defaulted_to_latest": True
                }

        # Status request patterns
        if any(phrase in response_lower for phrase in [
            "what improvements", "pending", "status", "what's waiting", "any improvements"
        ]):
            return {"action": "status", "confidence": 0.8}

        return {"action": "unknown", "confidence": 0.0}

    def _handle_approval_response(self, parsed: Dict, channel: str) -> Dict[str, Any]:
        """Handle approval or rejection response."""
        request_id = parsed["request_id"]
        action = parsed["action"]

        # Find the alert in queue
        pending_alerts = [a for a in self.alert_queue.pending if a.request_id == request_id]

        if not pending_alerts:
            # Check if this was a resolution failure (e.g., ambiguous partial match)
            user_input = parsed.get("user_input", request_id)
            error_msg = f"No pending alert found with ID: {request_id}"

            if parsed.get("resolution_failed"):
                # Try to provide helpful feedback
                if user_input.isdigit():
                    error_msg = f"Invalid index '{user_input}'. You have {len(self.alert_queue.pending)} pending alert(s)."
                else:
                    # Check for ambiguous partial matches
                    matches = [a for a in self.alert_queue.pending
                              if user_input.lower() in a.request_id.lower()]
                    if len(matches) > 1:
                        match_ids = ", ".join([a.request_id for a in matches])
                        error_msg = f"Ambiguous identifier '{user_input}' matches multiple alerts: {match_ids}"
                    else:
                        error_msg = f"No pending alert matching '{user_input}'"

            return {
                "success": False,
                "error": error_msg,
                "suggestion": "Try 'APPROVE' (for most recent), 'APPROVE 1', or say 'STATUS' for pending alerts"
            }

        alert = pending_alerts[0]

        if action == "approve":
            # Remove from queue
            self.alert_queue.remove_alert(request_id)

            print(f"[alerts] ✓ User approved improvement {request_id}")

            # DEPLOY THE IMPROVEMENT using the deployment pipeline
            if self.deployer:
                print(f"[alerts] 🚀 Starting deployment for {request_id}")

                # Convert alert back to improvement data format for deployment
                improvement_data = {
                    "request_id": alert.request_id,
                    "component": alert.component,
                    "description": alert.description,
                    "expected_benefit": alert.expected_benefit,
                    "risk_level": alert.risk_level,
                    "confidence": alert.confidence,
                    "urgency": alert.urgency,
                    "detected_at": alert.detected_at.isoformat()
                }

                try:
                    deployment_result = self.deployer.deploy_improvement(improvement_data)

                    if deployment_result.success:
                        print(f"[alerts] ✅ Successfully deployed improvement {request_id}")

                        # Record successful deployment in history
                        self.alert_history.record_deployment(request_id, deployment_result, True)

                        return {
                            "success": True,
                            "action": "approved",
                            "request_id": request_id,
                            "message": f"Improvement {request_id} approved and successfully deployed",
                            "deployment_status": "completed",
                            "changes_applied": deployment_result.changes_applied,
                            "backup_path": deployment_result.backup_path
                        }
                    else:
                        print(f"[alerts] ❌ Deployment failed for {request_id}: {deployment_result.error_message}")

                        # Record failed deployment in history
                        self.alert_history.record_deployment(request_id, deployment_result, False)

                        return {
                            "success": False,
                            "action": "approved",
                            "request_id": request_id,
                            "error": f"Approval successful but deployment failed: {deployment_result.error_message}",
                            "deployment_status": "failed",
                            "rollback_performed": deployment_result.rollback_performed
                        }

                except Exception as e:
                    print(f"[alerts] 💥 Deployment exception for {request_id}: {e}")

                    return {
                        "success": False,
                        "action": "approved",
                        "request_id": request_id,
                        "error": f"Approval successful but deployment crashed: {str(e)}",
                        "deployment_status": "crashed"
                    }
            else:
                # Deployment pipeline not available - return legacy response
                print(f"[alerts] ⚠️ Deployment pipeline not available for {request_id}")

                return {
                    "success": True,
                    "action": "approved",
                    "request_id": request_id,
                    "message": f"Improvement {request_id} approved for implementation",
                    "next_step": "deployment_pending",
                    "deployment_status": "pipeline_unavailable"
                }

        elif action == "reject":
            # Remove from queue
            self.alert_queue.remove_alert(request_id)

            print(f"[alerts] ✗ User rejected improvement {request_id}")

            return {
                "success": True,
                "action": "rejected",
                "request_id": request_id,
                "message": f"Improvement {request_id} rejected and removed from queue"
            }

    def _handle_explain_request(self, parsed: Dict, channel: str) -> Dict[str, Any]:
        """Handle request for more details about an improvement."""
        request_id = parsed["request_id"]

        # Find the alert
        pending_alerts = [a for a in self.alert_queue.pending if a.request_id == request_id]

        if not pending_alerts:
            return {
                "success": False,
                "error": f"No pending alert found with ID: {request_id}"
            }

        alert = pending_alerts[0]

        # Find the index number for user-friendly reference
        alert_index = None
        for i, a in enumerate(self.alert_queue.pending, 1):
            if a.request_id == alert.request_id:
                alert_index = i
                break

        index_info = f" (#{alert_index})" if alert_index else ""

        detailed_explanation = f"""
        Detailed information for improvement {alert.request_id}{index_info}:

        Component: {alert.component}
        Description: {alert.description}
        Expected Benefit: {alert.expected_benefit}
        Risk Level: {alert.risk_level}
        Confidence: {int(alert.confidence * 100)}%
        Urgency: {alert.urgency}
        Detected: {alert.detected_at.strftime('%Y-%m-%d at %H:%M')}

        To approve: say 'APPROVE' (or 'APPROVE {alert_index}' for this specific one)
        To reject: say 'REJECT' (or 'REJECT {alert_index}')
        """

        return {
            "success": True,
            "action": "explanation",
            "request_id": request_id,
            "explanation": detailed_explanation.strip()
        }

    def _handle_status_request(self, channel: str) -> Dict[str, Any]:
        """Handle status request - list pending improvements."""
        pending = self.alert_queue.pending

        if not pending:
            return {
                "success": True,
                "action": "status",
                "message": "No pending improvements at this time."
            }

        status_summary = f"You have {len(pending)} pending improvement(s):\n\n"

        for i, alert in enumerate(pending, 1):
            status_summary += f"{i}. {alert.request_id} ({alert.urgency} priority)\n"
            status_summary += f"   {alert.description}\n"
            status_summary += f"   Expected: {alert.expected_benefit}\n\n"

        status_summary += "To act on an improvement, say:\n"
        status_summary += "  'APPROVE' (for most recent) or 'APPROVE 1' (for first)\n"
        status_summary += "  'REJECT' (for most recent) or 'REJECT 2' (for second)\n"
        status_summary += "  'EXPLAIN' (for most recent) or 'EXPLAIN 1' for specific details"

        return {
            "success": True,
            "action": "status",
            "pending_count": len(pending),
            "message": status_summary.strip()
        }

    def get_pending_alerts(self) -> List[ImprovementAlert]:
        """Get list of pending alerts."""
        return self.alert_queue.pending.copy()

    def get_alert_history(self, limit: int = 50) -> List[Dict[str, Any]]:
        """Get recent alert history."""
        return self.alert_history.get_recent_history(limit)

    def get_system_status(self) -> Dict[str, Any]:
        """Get overall alert system status."""
        stats = self.alert_history.get_delivery_stats()

        deployment_status = "available" if self.deployer else "unavailable"

        return {
            "active": self.active,
            "alerts_enabled": self.user_preferences.is_alerts_enabled(),
            "registered_methods": list(self.alert_methods.keys()),
            "pending_alerts": len(self.alert_queue.pending),
            "delivery_stats": stats,
            "preferences_summary": self.user_preferences.get_preferences_summary(),
            "deployment_pipeline": deployment_status
        }

    def enable_system(self) -> None:
        """Enable the alert system."""
        self.active = True
        print("[alerts] Alert system enabled")

    def disable_system(self) -> None:
        """Disable the alert system."""
        self.active = False
        print("[alerts] Alert system disabled")

    def get_pending_for_next_wake(self) -> List[ImprovementAlert]:
        """Get alerts queued for next-wake presentation."""
        # This will be used by next-wake integration
        return [alert for alert in self.alert_queue.pending
                if alert.urgency in ["high", "medium", "low"]]

    def clear_pending_alerts(self) -> int:
        """Clear all pending alerts (for testing/reset)."""
        count = len(self.alert_queue.pending)
        self.alert_queue.pending.clear()
        print(f"[alerts] Cleared {count} pending alerts")
        return count

    def get_deployment_statistics(self) -> Dict[str, Any]:
        """Get deployment pipeline statistics if available."""
        if self.deployer:
            return self.deployer.get_deployment_statistics()
        else:
            return {
                "total_deployments": 0,
                "successful_deployments": 0,
                "failed_deployments": 0,
                "success_rate": 0,
                "rollbacks_performed": 0,
                "rollback_rate": 0,
                "status": "deployment_pipeline_unavailable"
            }

    def share_observation(self, observation: Dict[str, Any]) -> Dict[str, Any]:
        """
        Share an observation from reflection/analysis without approval flow.

        Observations are informational insights that don't require user approval.
        They're shared conversationally, not queued for deployment.

        Args:
            observation: Dict with 'title', 'content', 'confidence', 'type'

        Returns:
            Dict with sharing status
        """
        if not self.active:
            return {"status": "disabled", "reason": "Alert system disabled"}

        print(f"[alerts] Sharing observation: {observation.get('title', 'unknown')}")
        print(f"[alerts] Type: observation (no approval required)")

        # Route to reflection_insight method for conversational presentation
        # (not the approval queue)
        if "reflection_insight" in self.alert_methods:
            insight_method = self.alert_methods["reflection_insight"]

            # Queue for next-wake conversational sharing
            insight_data = [{
                'title': observation.get('title', 'Observation'),
                'content': observation.get('content', ''),
                'phase': observation.get('phase', 1),
                'type': observation.get('type', 'general'),
                'confidence': observation.get('confidence', 0.5),
                'keywords': observation.get('keywords', [])
            }]

            queued = insight_method.queue_reflection_insights(insight_data)

            return {
                "status": "shared",
                "method": "reflection_insight",
                "queued": queued > 0,
                "message": "Observation queued for conversational sharing (no approval required)"
            }
        else:
            print("[alerts] ⚠️ reflection_insight method not available for observation sharing")
            return {
                "status": "failed",
                "reason": "reflection_insight method not registered"
            }