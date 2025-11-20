#!/usr/bin/env python3
"""
Evolutionary Approval System for KLoROS D-REAM
Handles presentation of evolutionary results and user approval workflow.
"""

import os
import sys
import time
import json
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Any, Optional, Tuple
from dataclasses import dataclass, asdict

@dataclass
class EvolutionaryResult:
    """Results from evolutionary optimization cycle."""
    approach_id: str
    candidate_type: str
    generation: int
    performance_score: float
    improvement_over_baseline: float
    response_time: float
    success_rate: float
    empirical_data: Dict[str, Any]
    approach_description: str
    code_preview: str
    timestamp: str

@dataclass
class ApprovalRequest:
    """Request for user approval of evolutionary improvement."""
    request_id: str
    evolutionary_result: EvolutionaryResult
    deployment_impact: str
    safety_assessment: str
    rollback_plan: str
    recommended_action: str
    approval_deadline: Optional[str] = None

class EvolutionaryApprovalInterface:
    """Interface for presenting evolutionary results and managing approvals."""

    def __init__(self):
        """Initialize approval interface."""
        self.approval_queue = Path("/home/kloros/.kloros/approval_queue")
        self.approval_queue.mkdir(parents=True, exist_ok=True)

        self.approval_history = Path("/home/kloros/.kloros/approval_history.json")
        self.pending_approvals = {}
        self.approval_responses = {}

        self._load_approval_history()

    def _load_approval_history(self):
        """Load approval history from disk."""
        if self.approval_history.exists():
            try:
                with open(self.approval_history, 'r') as f:
                    data = json.load(f)
                    self.approval_responses = data.get("responses", {})
            except Exception as e:
                print(f"[approval] Failed to load history: {e}")

    def _save_approval_history(self):
        """Save approval history to disk."""
        try:
            history_data = {
                "responses": self.approval_responses,
                "last_updated": datetime.now().isoformat()
            }
            with open(self.approval_history, 'w') as f:
                json.dump(history_data, f, indent=2, default=str)
        except Exception as e:
            print(f"[approval] Failed to save history: {e}")

    def create_approval_request(self, evolutionary_result: EvolutionaryResult) -> ApprovalRequest:
        """Create approval request from evolutionary result."""
        request_id = f"approval_{evolutionary_result.approach_id}_{int(time.time())}"

        # Assess deployment impact
        deployment_impact = self._assess_deployment_impact(evolutionary_result)

        # Perform safety assessment
        safety_assessment = self._perform_safety_assessment(evolutionary_result)

        # Create rollback plan
        rollback_plan = self._create_rollback_plan(evolutionary_result)

        # Generate recommendation
        recommended_action = self._generate_recommendation(evolutionary_result, safety_assessment)

        approval_request = ApprovalRequest(
            request_id=request_id,
            evolutionary_result=evolutionary_result,
            deployment_impact=deployment_impact,
            safety_assessment=safety_assessment,
            rollback_plan=rollback_plan,
            recommended_action=recommended_action,
            approval_deadline=None  # No deadline for now
        )

        # Save to queue
        self._save_approval_request(approval_request)

        return approval_request

    def _assess_deployment_impact(self, result: EvolutionaryResult) -> str:
        """Assess the impact of deploying this evolutionary improvement."""
        impact_level = "LOW"
        impact_details = []

        # Assess based on candidate type
        if result.candidate_type == "memory_context_integration":
            if result.performance_score > 0.8:
                impact_level = "MEDIUM"
                impact_details.append("Modifies chat method in core KLoROS class")
                impact_details.append("Enhances memory context retrieval")
            else:
                impact_details.append("Minor memory integration improvements")

        elif result.candidate_type == "llm_tool_generation_consistency":
            if result.performance_score > 0.9:
                impact_level = "HIGH"
                impact_details.append("Modifies tool execution in reasoning backend")
                impact_details.append("Affects all tool synthesis operations")
            else:
                impact_level = "MEDIUM"
                impact_details.append("Improves tool name consistency")

        elif result.candidate_type == "rag_example_quality_enhancement":
            impact_level = "MEDIUM"
            impact_details.append("Modifies RAG retrieval pipeline")
            impact_details.append("Affects tool synthesis example injection")

        # Assess performance improvement
        if result.improvement_over_baseline > 0.1:
            impact_details.append(f"Significant performance gain: +{result.improvement_over_baseline:.1%}")
        elif result.improvement_over_baseline > 0.05:
            impact_details.append(f"Moderate performance gain: +{result.improvement_over_baseline:.1%}")
        else:
            impact_details.append(f"Minor performance gain: +{result.improvement_over_baseline:.1%}")

        return f"IMPACT: {impact_level}\n" + "\n".join(f"• {detail}" for detail in impact_details)

    def _perform_safety_assessment(self, result: EvolutionaryResult) -> str:
        """Perform safety assessment of evolutionary improvement."""
        safety_score = 10  # Start with perfect score
        safety_issues = []
        safety_positives = []

        # Check performance scores
        if result.performance_score < 0.7:
            safety_score -= 3
            safety_issues.append("Performance score below safety threshold (0.7)")
        elif result.performance_score > 0.9:
            safety_positives.append("High performance score indicates stability")

        # Check success rate
        if result.success_rate < 0.8:
            safety_score -= 2
            safety_issues.append("Success rate below recommended threshold (0.8)")
        else:
            safety_positives.append("Good success rate in testing")

        # Check for error rates
        empirical_data = result.empirical_data
        if empirical_data.get("error_count", 0) > 0:
            safety_score -= 1
            safety_issues.append("Errors detected during testing")

        # Check response time impact
        if result.response_time > 2.0:
            safety_score -= 1
            safety_issues.append("Response time impact may affect user experience")

        # Assess code complexity
        code_lines = len(result.code_preview.split('\n'))
        if code_lines > 50:
            safety_score -= 1
            safety_issues.append("Complex code changes increase risk")

        # Generate safety assessment
        if safety_score >= 8:
            safety_level = "HIGH"
        elif safety_score >= 6:
            safety_level = "MEDIUM"
        else:
            safety_level = "LOW"

        assessment = f"SAFETY: {safety_level} (Score: {safety_score}/10)\n"

        if safety_positives:
            assessment += "\n✅ Safety Positives:\n"
            assessment += "\n".join(f"• {positive}" for positive in safety_positives)

        if safety_issues:
            assessment += "\n⚠️ Safety Concerns:\n"
            assessment += "\n".join(f"• {issue}" for issue in safety_issues)

        return assessment

    def _create_rollback_plan(self, result: EvolutionaryResult) -> str:
        """Create rollback plan for deployment."""
        plan_elements = [
            "1. Automatic backup created before deployment",
            "2. File-level rollback available via backup restoration",
            "3. Validation tests will detect failures immediately",
            "4. Failed deployments trigger automatic rollback",
            "5. Manual rollback command available: `kloros_rollback {approach_id}`"
        ]

        # Add specific rollback considerations
        if result.candidate_type == "memory_context_integration":
            plan_elements.append("6. Memory system will gracefully degrade if enhancement fails")

        elif result.candidate_type == "llm_tool_generation_consistency":
            plan_elements.append("6. Tool execution will fallback to original implementation")

        elif result.candidate_type == "rag_example_quality_enhancement":
            plan_elements.append("6. RAG system will continue with original retrieval if enhancement fails")

        return "ROLLBACK PLAN:\n" + "\n".join(plan_elements)

    def _generate_recommendation(self, result: EvolutionaryResult, safety_assessment: str) -> str:
        """Generate recommendation for approval decision."""
        # Parse safety level
        safety_level = "MEDIUM"
        if "HIGH" in safety_assessment:
            safety_level = "HIGH"
        elif "LOW" in safety_assessment:
            safety_level = "LOW"

        # Generate recommendation based on multiple factors
        if result.performance_score > 0.9 and safety_level == "HIGH" and result.improvement_over_baseline > 0.05:
            return "RECOMMENDED: Deploy immediately - High performance with excellent safety profile"

        elif result.performance_score > 0.8 and safety_level in ["HIGH", "MEDIUM"] and result.improvement_over_baseline > 0.02:
            return "RECOMMENDED: Deploy with monitoring - Good improvement with acceptable safety"

        elif result.performance_score > 0.7 and safety_level == "HIGH":
            return "CONDITIONAL: Deploy if you accept moderate performance gain"

        elif safety_level == "LOW":
            return "NOT RECOMMENDED: Safety concerns outweigh performance benefits"

        else:
            return "REVIEW: Manual evaluation recommended - Mixed performance/safety profile"

    def _save_approval_request(self, request: ApprovalRequest):
        """Save approval request to queue."""
        request_file = self.approval_queue / f"{request.request_id}.json"

        try:
            with open(request_file, 'w') as f:
                json.dump(asdict(request), f, indent=2, default=str)

            self.pending_approvals[request.request_id] = request
            print(f"[approval] Saved approval request: {request.request_id}")

        except Exception as e:
            print(f"[approval] Failed to save request: {e}")

    def present_approval_request_to_kloros(self, request: ApprovalRequest) -> str:
        """Format approval request for presentation by KLoROS."""
        result = request.evolutionary_result

        presentation = f"""
🧬 **EVOLUTIONARY IMPROVEMENT READY FOR DEPLOYMENT**

**Approach ID:** {result.approach_id}
**Generation:** {result.generation}
**Component:** {result.candidate_type.replace('_', ' ').title()}

**PERFORMANCE METRICS:**
• Performance Score: {result.performance_score:.1%}
• Improvement: +{result.improvement_over_baseline:.1%} over baseline
• Success Rate: {result.success_rate:.1%}
• Response Time: {result.response_time:.2f}s

**DESCRIPTION:**
{result.approach_description}

{request.deployment_impact}

{request.safety_assessment}

{request.rollback_plan}

**RECOMMENDATION:** {request.recommended_action}

**CODE PREVIEW:**
```python
{result.code_preview[:500]}{'...' if len(result.code_preview) > 500 else ''}
```

**To approve this deployment, respond with:**
"APPROVE EVOLUTION {request.request_id}"

**To decline this deployment, respond with:**
"DECLINE EVOLUTION {request.request_id}"

**For more details, respond with:**
"DETAILS EVOLUTION {request.request_id}"
"""

        return presentation

    def process_approval_response(self, user_response: str) -> Dict[str, Any]:
        """Process user approval response."""
        response_lower = user_response.lower().strip()

        # Extract request ID and action
        if "approve evolution" in response_lower:
            action = "approve"
            request_id = self._extract_request_id(user_response, "approve evolution")
        elif "decline evolution" in response_lower:
            action = "decline"
            request_id = self._extract_request_id(user_response, "decline evolution")
        elif "details evolution" in response_lower:
            action = "details"
            request_id = self._extract_request_id(user_response, "details evolution")
        else:
            return {"error": "Invalid approval response format"}

        if not request_id:
            return {"error": "Could not extract request ID from response"}

        # Check if request exists
        if request_id not in self.pending_approvals:
            return {"error": f"Request {request_id} not found in pending approvals"}

        # Process action
        if action == "approve":
            return self._approve_request(request_id)
        elif action == "decline":
            return self._decline_request(request_id)
        elif action == "details":
            return self._provide_details(request_id)

    def _extract_request_id(self, response: str, command: str) -> Optional[str]:
        """Extract request ID from user response."""
        try:
            # Find the command and extract what follows
            command_pos = response.lower().find(command)
            if command_pos == -1:
                return None

            after_command = response[command_pos + len(command):].strip()
            # Extract the first word/token as request ID
            request_id = after_command.split()[0] if after_command.split() else None

            return request_id
        except Exception:
            return None

    def _approve_request(self, request_id: str) -> Dict[str, Any]:
        """Approve deployment request."""
        request = self.pending_approvals[request_id]

        approval_record = {
            "request_id": request_id,
            "action": "approved",
            "timestamp": datetime.now().isoformat(),
            "approach_id": request.evolutionary_result.approach_id,
            "candidate_type": request.evolutionary_result.candidate_type
        }

        self.approval_responses[request_id] = approval_record
        self._save_approval_history()

        # Remove from pending
        del self.pending_approvals[request_id]

        # Remove from queue
        request_file = self.approval_queue / f"{request_id}.json"
        if request_file.exists():
            request_file.unlink()

        return {
            "action": "approved",
            "request_id": request_id,
            "message": f"✅ Evolution {request.evolutionary_result.approach_id} approved for deployment",
            "ready_for_deployment": True
        }

    def _decline_request(self, request_id: str) -> Dict[str, Any]:
        """Decline deployment request."""
        request = self.pending_approvals[request_id]

        approval_record = {
            "request_id": request_id,
            "action": "declined",
            "timestamp": datetime.now().isoformat(),
            "approach_id": request.evolutionary_result.approach_id,
            "candidate_type": request.evolutionary_result.candidate_type
        }

        self.approval_responses[request_id] = approval_record
        self._save_approval_history()

        # Remove from pending
        del self.pending_approvals[request_id]

        # Remove from queue
        request_file = self.approval_queue / f"{request_id}.json"
        if request_file.exists():
            request_file.unlink()

        return {
            "action": "declined",
            "request_id": request_id,
            "message": f"❌ Evolution {request.evolutionary_result.approach_id} declined",
            "ready_for_deployment": False
        }

    def _provide_details(self, request_id: str) -> Dict[str, Any]:
        """Provide detailed information about approval request."""
        request = self.pending_approvals[request_id]
        result = request.evolutionary_result

        detailed_info = f"""
**DETAILED EVOLUTION ANALYSIS: {result.approach_id}**

**Technical Metrics:**
• Performance Score: {result.performance_score:.3f}
• Baseline Improvement: {result.improvement_over_baseline:.3f}
• Success Rate: {result.success_rate:.3f}
• Average Response Time: {result.response_time:.3f}s
• Generation: {result.generation}

**Empirical Test Data:**
{json.dumps(result.empirical_data, indent=2)}

**Complete Code Implementation:**
```python
{result.code_preview}
```

**Deployment Details:**
{request.deployment_impact}

**Safety Analysis:**
{request.safety_assessment}

**Rollback Strategy:**
{request.rollback_plan}

**Final Recommendation:**
{request.recommended_action}

Ready to approve or decline?
"""

        return {
            "action": "details_provided",
            "request_id": request_id,
            "detailed_info": detailed_info
        }

    def get_pending_approvals(self) -> List[str]:
        """Get list of pending approval request IDs."""
        return list(self.pending_approvals.keys())

    def has_pending_approvals(self) -> bool:
        """Check if there are pending approvals."""
        return len(self.pending_approvals) > 0

def main():
    """Test the approval system."""
    print("=== Testing Evolutionary Approval System ===")

    # Create test evolutionary result
    test_result = EvolutionaryResult(
        approach_id="memory_wrapper_v1_performance",
        candidate_type="memory_context_integration",
        generation=2,
        performance_score=0.923,
        improvement_over_baseline=0.087,
        response_time=0.342,
        success_rate=0.95,
        empirical_data={
            "successful_tests": 3,
            "total_tests": 3,
            "context_relevance": 0.89,
            "response_latency": 0.81
        },
        approach_description="Performance-optimized memory integration with caching",
        code_preview="def memory_enhanced_chat_wrapper(self, message: str):\\n    # Enhanced with caching...",
        timestamp="2025-01-06T12:00:00"
    )

    # Create approval interface
    approval_interface = EvolutionaryApprovalInterface()

    # Create approval request
    request = approval_interface.create_approval_request(test_result)
    print(f"Created approval request: {request.request_id}")

    # Present to KLoROS
    presentation = approval_interface.present_approval_request_to_kloros(request)
    print("\n--- KLoROS Presentation ---")
    print(presentation)

    # Test approval response
    test_response = f"APPROVE EVOLUTION {request.request_id}"
    result = approval_interface.process_approval_response(test_response)
    print(f"\nApproval result: {result}")

    print("\n=== Approval System Test Complete ===")

if __name__ == "__main__":
    main()