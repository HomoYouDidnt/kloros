#!/usr/bin/env python3
"""
Generic Investigation Handler - Adaptive investigation system for any question type.

Purpose:
    Handle ANY curiosity question through adaptive investigation workflow:
    - LLM-based intent classification
    - Extensible evidence gathering plugins
    - Introspective stopping criteria
    - Recognition of when to analyze vs experiment

Architecture:
    1. Classify question intent and required evidence sources
    2. Iteratively gather evidence using plugins
    3. After each iteration:
       - Analyze current understanding
       - Identify explicit gaps
       - Assess diminishing returns
       - Introspect on investigation progress
    4. Stop when: no gaps, low value, or introspection says stop
    5. Switch to experimentation if static analysis hits limits

Integration:
    - Called by investigation_consumer_daemon for non-module questions
    - Uses Ollama LLM for classification and analysis
    - Pluggable evidence gathering framework
"""

import logging
import requests
import json
from typing import Dict, Any, List, Optional
from datetime import datetime

from .evidence_plugins import (
    EvidencePlugin,
    Evidence,
    CodeStructurePlugin,
    RuntimeLogsPlugin,
    SystemMetricsPlugin,
    IntegrationPlugin,
    ExperimentationPlugin,
    DocumentationPlugin,
)

# Import RTFM system
try:
    from kloros.introspection.doc_reader import rtfm_check
    RTFM_AVAILABLE = True
except ImportError:
    logger.warning("[generic_investigation] RTFM system not available")
    RTFM_AVAILABLE = False
    rtfm_check = None

logger = logging.getLogger(__name__)


class GenericInvestigationHandler:
    """
    Adaptive investigation handler for any question type.

    Uses D-with-extra-steps approach:
    - Introspection as primary stopping mechanism
    - Hard limits (iterations/time/tokens) as safety backstop
    """

    def __init__(self, ollama_host: str = "http://127.0.0.1:11434", model: str = "qwen2.5-coder:7b"):
        """
        Initialize handler.

        Args:
            ollama_host: Ollama server URL
            model: Model to use for analysis
        """
        self.ollama_host = ollama_host
        self.model = model

        self.evidence_plugins: List[EvidencePlugin] = [
            CodeStructurePlugin(),
            RuntimeLogsPlugin(),
            SystemMetricsPlugin(),
            IntegrationPlugin(),
            ExperimentationPlugin(),
            DocumentationPlugin(),
        ]

        self.max_iterations = 8
        self.max_time_seconds = 600
        self.max_tokens = 50000

        # Metrics tracking for performance analysis
        self.total_tokens_used = 0
        self.total_prompt_tokens = 0
        self.models_used = []

        logger.info(f"[generic_investigation] Initialized with {len(self.evidence_plugins)} plugins")

    def investigate(self, question: str, question_id: str, initial_evidence: List[str] = None) -> Dict[str, Any]:
        """
        Investigate any question adaptively.

        Args:
            question: The question to investigate
            question_id: Unique question identifier
            initial_evidence: Optional list of initial evidence strings from question

        Returns:
            Investigation results dictionary
        """
        start_time = datetime.now()

        # Reset metrics for this investigation
        self.total_tokens_used = 0
        self.total_prompt_tokens = 0
        self.models_used = []

        investigation = {
            "question": question,
            "question_id": question_id,
            "timestamp": start_time.isoformat(),
            "investigation_type": None,
            "evidence": [],
            "iterations": 0,
            "analysis": {},
            "confidence": 0.0,
            "success": False,
            "error": None,
            "stopping_reason": None,
            "rtfm_check": None
        }

        # RTFM CHECK: Read documentation BEFORE investigating!
        if RTFM_AVAILABLE and rtfm_check:
            try:
                logger.info(f"[generic_investigation] 📚 RTFM check for: {question[:100]}")
                rtfm_result = rtfm_check(question)
                investigation["rtfm_check"] = rtfm_result

                if rtfm_result.get("should_read_docs_first"):
                    suggested_docs = rtfm_result.get("suggested_docs", [])
                    logger.info(f"[generic_investigation] ✓ Found {len(suggested_docs)} relevant docs - reading first!")

                    # Add doc content as evidence
                    if rtfm_result.get("relevant_content"):
                        for doc_path, doc_data in rtfm_result["relevant_content"].items():
                            investigation["evidence"].append({
                                "source": "documentation",
                                "type": "rtfm",
                                "doc_path": doc_path,
                                "title": doc_data["title"],
                                "summary": doc_data["summary"],
                                "content": doc_data["full_content"],
                                "timestamp": datetime.now().isoformat()
                            })

                    # Check if docs fully answer the question
                    if len(suggested_docs) > 0:
                        # Quick analysis: does doc content answer the question?
                        doc_content = "\n\n".join([
                            f"# {d['title']}\n{d.get('summary', '')}"
                            for d in rtfm_result.get("relevant_content", {}).values()
                        ])

                        if len(doc_content) > 100:  # We have substantial doc content
                            logger.info(f"[generic_investigation] 🎯 Documentation found - analyzing for actionable guidance")

                            # Analyze documentation to determine if it provides actionable solution
                            action_analysis = self._analyze_documentation_for_action(question, doc_content, question_id)

                            if action_analysis.get("provides_solution"):
                                # Documentation provides clear guidance - investigation complete with action recommended
                                investigation["stopping_reason"] = "documentation_provides_solution"
                                investigation["success"] = True
                                investigation["confidence"] = action_analysis.get("confidence", 0.8)
                                investigation["analysis"] = {
                                    "summary": f"Documentation provides solution: {', '.join(d['title'] for d in suggested_docs[:3])}",
                                    "recommendation": action_analysis.get("recommendation", "Apply solution from documentation"),
                                    "actionable": True,
                                    "action_type": action_analysis.get("action_type", "apply_documented_solution")
                                }
                                return investigation
                            else:
                                # Documentation exists but doesn't fully answer - continue investigation
                                logger.info(f"[generic_investigation] Documentation found but doesn't provide complete solution - continuing investigation")
                                investigation["rtfm_partial"] = True
                else:
                    logger.info(f"[generic_investigation] No relevant docs found - proceeding with investigation")

            except Exception as e:
                logger.warning(f"[generic_investigation] RTFM check failed: {e}")

        try:
            intent = self._classify_intent(question)
            investigation["investigation_type"] = intent.get("investigation_type", "unknown")

            if intent.get("is_meta_question"):
                return self._handle_meta_question(question, question_id, intent)

            evidence_list = []

            # Parse initial evidence strings into Evidence objects
            if initial_evidence:
                evidence_list.extend(self._parse_initial_evidence(initial_evidence))
                logger.info(f"[generic_investigation] Parsed {len(evidence_list)} initial evidence items")

            iteration = 0

            while iteration < self.max_iterations:
                elapsed = (datetime.now() - start_time).total_seconds()
                if elapsed > self.max_time_seconds:
                    investigation["stopping_reason"] = "time_limit"
                    break

                new_evidence = self._gather_evidence_batch(
                    question, intent, evidence_list, iteration
                )

                evidence_list.extend(new_evidence)

                if not new_evidence:
                    investigation["stopping_reason"] = "no_more_evidence"
                    break

                analysis = self._analyze_evidence(question, evidence_list, intent)

                gaps = self._identify_gaps(question, evidence_list, analysis)
                value = self._assess_value(new_evidence, analysis, iteration)
                introspection = self._introspect_progress(
                    question, evidence_list, analysis, iteration
                )

                if introspection["decision"] == "stop_with_findings":
                    investigation["stopping_reason"] = "introspection_stop"
                    investigation["analysis"] = analysis
                    break

                elif introspection["decision"] == "switch_to_experimentation":
                    exp_plugin = next(p for p in self.evidence_plugins if p.name == "experimentation")
                    exp_evidence = exp_plugin.gather(question, {
                        "investigation_type": intent["investigation_type"],
                        "intent": intent,
                        "existing_evidence": evidence_list,
                        "iteration": iteration
                    })
                    evidence_list.extend(exp_evidence)
                    investigation["stopping_reason"] = "experimentation_complete"
                    investigation["analysis"] = self._analyze_evidence(question, evidence_list, intent)
                    break

                elif not gaps and value == "low":
                    investigation["stopping_reason"] = "no_gaps_low_value"
                    investigation["analysis"] = analysis
                    break

                iteration += 1

            # Ensure stopping_reason is set if we exited the loop without one
            if not investigation.get("stopping_reason"):
                investigation["stopping_reason"] = "max_iterations_reached"
                investigation["analysis"] = analysis if analysis else {"summary": "Investigation reached maximum iterations"}

            investigation["evidence"] = [self._serialize_evidence(ev) for ev in evidence_list]
            investigation["iterations"] = iteration
            investigation["confidence"] = investigation.get("analysis", {}).get("confidence", 0.0)
            investigation["success"] = len(evidence_list) > 0

            # Add performance metrics
            investigation["model_used"] = self.models_used[0] if self.models_used else "unknown"
            investigation["tokens_used"] = self.total_tokens_used
            investigation["prompt_tokens"] = self.total_prompt_tokens

            logger.info(f"[generic_investigation] Complete: {iteration} iterations, {len(evidence_list)} evidence, reason: {investigation['stopping_reason']}, model: {investigation['model_used']}, tokens: {investigation['tokens_used']}")

        except Exception as e:
            investigation["error"] = str(e)
            investigation["model_used"] = "unknown"
            investigation["tokens_used"] = 0
            investigation["prompt_tokens"] = 0
            logger.error(f"[generic_investigation] Investigation failed: {e}", exc_info=True)

        return investigation

    def _classify_intent(self, question: str) -> Dict[str, Any]:
        """
        Use LLM to classify question intent and required evidence sources.
        """
        prompt = f"""Analyze this curiosity question and classify its investigation requirements.

Question: {question}

Provide a structured JSON response:
{{
  "investigation_type": "code_behavior|system_state|integration_analysis|performance|capability_discovery|error_analysis",
  "is_meta_question": false,
  "required_evidence_sources": ["code_structure", "runtime_logs", "system_metrics", "integration", "experimentation"],
  "estimated_complexity": "simple|moderate|complex",
  "suggested_approach": "Brief description of investigation approach"
}}

Output ONLY valid JSON, no markdown or explanations."""

        try:
            response = self._llm_query(prompt, max_tokens=500, temperature=0.2)
            if response:
                if response.startswith("```json"):
                    response = response.split("```json")[1].split("```")[0].strip()
                elif response.startswith("```"):
                    response = response.split("```")[1].split("```")[0].strip()

                return json.loads(response)

        except Exception as e:
            logger.warning(f"[generic_investigation] Intent classification failed: {e}")

        return {
            "investigation_type": "unknown",
            "is_meta_question": False,
            "required_evidence_sources": ["code_structure"],
            "estimated_complexity": "moderate",
            "suggested_approach": "Gather code structure and analyze"
        }

    def _handle_meta_question(self, question: str, question_id: str, intent: Dict[str, Any]) -> Dict[str, Any]:
        """
        Handle meta-questions about how to investigate something.
        """
        prompt = f"""This is a meta-question about investigation methodology.

Question: {question}

Provide investigation guidance:
1. What evidence sources should be examined?
2. What tools/methods should be used?
3. What are the key steps?
4. What pitfalls to avoid?

Be concise and practical."""

        try:
            response = self._llm_query(prompt, max_tokens=1000, temperature=0.3)

            return {
                "question": question,
                "question_id": question_id,
                "timestamp": datetime.now().isoformat(),
                "investigation_type": "meta_question",
                "methodology": response,
                "success": True,
                "model_used": self.models_used[0] if self.models_used else "unknown",
                "tokens_used": self.total_tokens_used,
                "prompt_tokens": self.total_prompt_tokens
            }

        except Exception as e:
            logger.error(f"[generic_investigation] Meta-question handling failed: {e}")
            return {
                "question": question,
                "question_id": question_id,
                "success": False,
                "error": str(e),
                "model_used": "unknown",
                "tokens_used": 0,
                "prompt_tokens": 0
            }

    def _gather_evidence_batch(
        self,
        question: str,
        intent: Dict[str, Any],
        existing_evidence: List[Evidence],
        iteration: int
    ) -> List[Evidence]:
        """
        Gather a batch of evidence from applicable plugins.
        """
        evidence = []

        investigation_type = intent.get("investigation_type", "unknown")

        sorted_plugins = sorted(
            self.evidence_plugins,
            key=lambda p: p.priority(investigation_type),
            reverse=True
        )

        context = {
            "investigation_type": investigation_type,
            "intent": intent,
            "existing_evidence": existing_evidence,
            "iteration": iteration
        }

        for plugin in sorted_plugins:
            try:
                if plugin.can_gather(investigation_type, question, context):
                    plugin_evidence = plugin.gather(question, context)
                    evidence.extend(plugin_evidence)
                    logger.debug(f"[generic_investigation] {plugin.name} gathered {len(plugin_evidence)} evidence")

            except Exception as e:
                logger.warning(f"[generic_investigation] Plugin {plugin.name} failed: {e}")

        return evidence

    def _analyze_documentation_for_action(
        self,
        question: str,
        doc_content: str,
        question_id: str
    ) -> Dict[str, Any]:
        """
        Analyze documentation to determine if it provides actionable solution.

        Args:
            question: The original question
            doc_content: Documentation content
            question_id: Question identifier

        Returns:
            Analysis dict with provides_solution, recommendation, action_type, confidence
        """
        prompt = f"""Analyze if this documentation provides an actionable solution to the question.

Question: {question}

Documentation excerpt:
{doc_content[:2000]}

Determine:
1. Does the documentation provide a clear, actionable solution?
2. What specific action should be taken?
3. Is this a code fix, configuration change, or architectural guidance?

Provide JSON analysis:
{{
  "provides_solution": true/false,
  "recommendation": "Specific action to take",
  "action_type": "code_fix|config_change|architecture_guidance|consolidation|refactoring",
  "confidence": 0.0-1.0,
  "reasoning": "Why this is or isn't actionable"
}}

Output ONLY valid JSON."""

        try:
            response = self._llm_query(prompt, max_tokens=500, temperature=0.2)
            if response.startswith("```json"):
                response = response.split("```json")[1].split("```")[0].strip()
            elif response.startswith("```"):
                response = response.split("```")[1].split("```")[0].strip()

            result = json.loads(response)
            logger.info(f"[generic_investigation] Doc analysis for {question_id}: provides_solution={result.get('provides_solution')}")
            return result

        except Exception as e:
            logger.warning(f"[generic_investigation] Documentation analysis failed: {e}")
            return {
                "provides_solution": False,
                "recommendation": "Unable to analyze documentation",
                "action_type": "unknown",
                "confidence": 0.0,
                "reasoning": f"Analysis error: {e}"
            }

    def _analyze_evidence(
        self,
        question: str,
        evidence: List[Evidence],
        intent: Dict[str, Any]
    ) -> Dict[str, Any]:
        """
        Use LLM to analyze gathered evidence and synthesize understanding.
        """
        evidence_summary = self._summarize_evidence(evidence)

        prompt = f"""Analyze the gathered evidence and provide understanding of this question.

Question: {question}

Evidence Summary:
{evidence_summary}

Provide JSON analysis:
{{
  "understanding": "What we now understand about the question",
  "key_findings": ["finding 1", "finding 2"],
  "confidence": 0.0-1.0,
  "remaining_uncertainties": ["uncertainty 1", "uncertainty 2"]
}}

Output ONLY valid JSON."""

        try:
            response = self._llm_query(prompt, max_tokens=1000, temperature=0.3)
            if response.startswith("```json"):
                response = response.split("```json")[1].split("```")[0].strip()
            elif response.startswith("```"):
                response = response.split("```")[1].split("```")[0].strip()

            return json.loads(response)

        except Exception as e:
            logger.warning(f"[generic_investigation] Evidence analysis failed: {e}")
            return {
                "understanding": "Analysis failed",
                "key_findings": [],
                "confidence": 0.0,
                "remaining_uncertainties": []
            }

    def _identify_gaps(
        self,
        question: str,
        evidence: List[Evidence],
        analysis: Dict[str, Any]
    ) -> List[str]:
        """
        Explicitly identify what information is still missing.
        """
        uncertainties = analysis.get("remaining_uncertainties", [])
        return uncertainties

    def _assess_value(
        self,
        new_evidence: List[Evidence],
        analysis: Dict[str, Any],
        iteration: int
    ) -> str:
        """
        Assess if new evidence added value (high/medium/low).
        """
        if iteration == 0:
            return "high"

        if not new_evidence:
            return "low"

        confidence = analysis.get("confidence", 0.0)
        if confidence > 0.8:
            return "low"
        elif confidence > 0.5:
            return "medium"
        else:
            return "high"

    def _introspect_progress(
        self,
        question: str,
        evidence: List[Evidence],
        analysis: Dict[str, Any],
        iteration: int
    ) -> Dict[str, Any]:
        """
        LLM introspects on investigation progress and decides next action.
        """
        evidence_summary = self._summarize_evidence(evidence)

        prompt = f"""Investigation Progress Check (Iteration {iteration}):

Question: {question}

Evidence gathered so far:
{evidence_summary}

Current understanding:
{analysis.get('understanding', 'Unknown')}

Confidence: {analysis.get('confidence', 0.0)}

Meta-cognitive evaluation - decide if I should STOP or continue:

STOP WITH FINDINGS if any of these are true:
- I've reached a conclusion (even if it's "this isn't needed" or "no action required")
- Adding more evidence won't change my understanding
- I'm repeating the same analysis with the same conclusion
- The question has been answered (positively OR negatively)
- I have enough evidence to make a recommendation

CONTINUE GATHERING if:
- I need specific missing information that I know how to obtain
- Current evidence is contradictory and more data will resolve it
- I'm making clear progress toward an answer

CRITICAL: A negative conclusion ("no change needed", "not beneficial", "already working")
is STILL a conclusion and should trigger stop_with_findings.

Provide JSON decision:
{{
  "decision": "continue_gathering|switch_to_experimentation|stop_with_findings",
  "reasoning": "Brief explanation of decision",
  "progress_assessment": "productive|diminishing_returns|spinning_wheels"
}}

Output ONLY valid JSON."""

        try:
            response = self._llm_query(prompt, max_tokens=500, temperature=0.3)
            if response.startswith("```json"):
                response = response.split("```json")[1].split("```")[0].strip()
            elif response.startswith("```"):
                response = response.split("```")[1].split("```")[0].strip()

            result = json.loads(response)
            logger.info(f"[generic_investigation] Introspection: {result['decision']} - {result['reasoning']}")
            return result

        except Exception as e:
            logger.warning(f"[generic_investigation] Introspection failed: {e}")
            return {
                "decision": "continue_gathering" if iteration < 3 else "stop_with_findings",
                "reasoning": "Introspection failed, using fallback logic",
                "progress_assessment": "unknown"
            }

    def _summarize_evidence(self, evidence: List[Evidence]) -> str:
        """
        Create concise summary of evidence for LLM context.
        """
        if not evidence:
            return "No evidence gathered yet."

        summary_parts = []
        evidence_by_type = {}

        for ev in evidence:
            if ev.evidence_type not in evidence_by_type:
                evidence_by_type[ev.evidence_type] = []
            evidence_by_type[ev.evidence_type].append(ev)

        for ev_type, ev_list in evidence_by_type.items():
            summary_parts.append(f"\n{ev_type.upper()} ({len(ev_list)} items):")
            for ev in ev_list[:3]:
                content_str = str(ev.content)[:200]
                summary_parts.append(f"  - {content_str}")

        return "\n".join(summary_parts)

    def _parse_initial_evidence(self, evidence_strings: List[str]) -> List[Evidence]:
        """
        Parse initial evidence strings from question into Evidence objects.

        Handles formats like:
        - "Produced in: /path/to/file.py"
        - "No consumers found in codebase"
        - "Channel type: queue/list"
        """
        import re
        from datetime import datetime

        evidence_objects = []

        for ev_str in evidence_strings:
            # Extract file paths from "Produced in: /path/to/file.py, /path/to/other.py"
            if "Produced in:" in ev_str or "produced in:" in ev_str.lower():
                # Extract all file paths
                path_pattern = r'(/[\w/\-\.]+\.py)'
                file_paths = re.findall(path_pattern, ev_str)

                if file_paths:
                    evidence_objects.append(Evidence(
                        source="question",
                        evidence_type="file_path",
                        content=file_paths,
                        metadata={"paths": file_paths, "primary_path": file_paths[0]},
                        timestamp=datetime.now().isoformat(),
                        confidence=1.0
                    ))

            # Generic text evidence
            else:
                evidence_objects.append(Evidence(
                    source="question",
                    evidence_type="context",
                    content=ev_str,
                    metadata={},
                    timestamp=datetime.now().isoformat(),
                    confidence=0.8
                ))

        return evidence_objects

    def _serialize_evidence(self, evidence: Evidence) -> Dict[str, Any]:
        """
        Convert Evidence object to JSON-serializable dict.
        """
        return {
            "source": evidence.source,
            "evidence_type": evidence.evidence_type,
            "content": evidence.content,
            "metadata": evidence.metadata,
            "timestamp": evidence.timestamp,
            "confidence": evidence.confidence
        }

    def _llm_query(self, prompt: str, max_tokens: int = 1000, temperature: float = 0.3) -> Optional[str]:
        """
        Query Ollama LLM with automatic failover and intelligent model selection.
        Tracks metrics (model, tokens) for performance analysis.
        """
        from config.models_config import select_best_model_for_task

        urls_to_try = [self.ollama_host]
        if self.ollama_host != "http://127.0.0.1:11434":
            urls_to_try.append("http://127.0.0.1:11434")

        last_error = None

        for url in urls_to_try:
            # Query API to select best available model for this endpoint
            model = select_best_model_for_task('code', url)
            try:
                logger.debug(f"[generic_investigation] Trying {url} with {model}")
                response = requests.post(
                    f"{url}/api/generate",
                    json={
                        "model": model,
                        "prompt": prompt,
                        "stream": True,
                        "options": {
                            "temperature": temperature,
                            "num_predict": max_tokens
                        }
                    },
                    timeout=(5, 600),
                    stream=True
                )
                response.raise_for_status()

                llm_output = ""
                eval_count = 0
                prompt_eval_count = 0

                for line in response.iter_lines():
                    if line:
                        try:
                            chunk = json.loads(line)
                            llm_output += chunk.get("response", "")
                            if chunk.get("done", False):
                                # Extract token counts from final chunk
                                eval_count = chunk.get("eval_count", 0)
                                prompt_eval_count = chunk.get("prompt_eval_count", 0)
                                break
                        except json.JSONDecodeError:
                            continue

                # Accumulate metrics
                self.models_used.append(model)
                self.total_tokens_used += eval_count
                self.total_prompt_tokens += prompt_eval_count

                logger.debug(f"[generic_investigation] Successfully connected to {url}, tokens: {eval_count}")
                return llm_output.strip()

            except (requests.exceptions.Timeout, requests.exceptions.ConnectionError, requests.exceptions.HTTPError) as e:
                logger.debug(f"[generic_investigation] Failed to connect to {url}: {e}")
                last_error = e
                continue

        logger.error(f"[generic_investigation] All Ollama endpoints failed: {last_error}")
        return None


def investigate_generic(question: str, question_id: str) -> Dict[str, Any]:
    """
    Standalone function to investigate any question.

    Args:
        question: Question to investigate
        question_id: Unique identifier

    Returns:
        Investigation results
    """
    handler = GenericInvestigationHandler()
    return handler.investigate(question, question_id)
