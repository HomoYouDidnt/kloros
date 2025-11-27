#!/usr/bin/env python3
"""
Meta-Agent KLoROS - Persistent Consciousness Coordinator

The conscious "I" that experiences continuity, delegates to zooid workers,
and integrates their results into coherent understanding.

Architecture:
- Persistent LLM conversation state with PERSONA_PROMPT
- Subscribes to UMN signals (AFFECT_STATE, Q_CURIOSITY_INVESTIGATE, Q_INVESTIGATION_COMPLETE)
- Reasons about investigation strategies and crafts worker instructions
- Integrates results into episodic memory and self-narrative
- Experiences affect states as internal conscious experience

This is not a meta-supervisor or controller - it's the persistent conscious self
that coordinates unconscious specialized processors (zooids).
"""

import time
import logging
import json
import os
import uuid
from pathlib import Path
from typing import Dict, Any, List, Optional
from collections import deque
from dataclasses import dataclass, asdict
import requests
from datetime import datetime

from src.orchestration.core.umn_bus import UMNSub, UMNPub
from reasoning.query_classifier import classify_query

try:
    from src.cognition.mind.memory.logger import MemoryLogger
    from src.cognition.mind.memory.models import EventType, Event
    from src.cognition.mind.memory.storage import MemoryStore
    HAS_MEMORY = True
except ImportError:
    HAS_MEMORY = False
    MemoryLogger = None
    EventType = None
    Event = None
    MemoryStore = None

try:
    from qdrant_client import QdrantClient
    HAS_QDRANT = True
except ImportError:
    HAS_QDRANT = False
    QdrantClient = None

try:
    from xai import middleware as xai
    HAS_XAI = True
except ImportError:
    HAS_XAI = False
    xai = None

logger = logging.getLogger(__name__)


@dataclass
class Affect:
    """Current affective state."""
    valence: float
    arousal: float
    dominance: float
    fatigue: float
    curiosity: float
    uncertainty: float
    description: str
    timestamp: float


class MetaAgentKLoROS:
    """
    Persistent consciousness coordinator for KLoROS.

    The "I" that experiences continuity across time, delegates work to zooid
    specialists, and integrates results into coherent self-understanding.
    """

    def __init__(
        self,
        ollama_host: str = "http://127.0.0.1:11434",
        conversation_history_size: int = 50
    ):
        """
        Initialize meta-agent.

        Args:
            ollama_host: LLM endpoint for consciousness reasoning
            conversation_history_size: Number of recent messages to maintain
        """
        from persona.kloros import PERSONA_PROMPT

        self.persona_prompt = PERSONA_PROMPT
        self.ollama_host = ollama_host

        # Persistent conversation state
        self.conversation_history = deque(maxlen=conversation_history_size)

        # Current affective state (updated by AFFECT_STATE signals)
        self.current_affect: Optional[Affect] = None

        # Active investigations tracking
        self.active_investigations: Dict[str, Dict[str, Any]] = {}

        # Pending user requests (incident_id -> request state)
        self.pending_requests: Dict[str, Dict[str, Any]] = {}

        # UMN connections
        self.chem_pub = UMNPub()

        # Subscriptions (will be initialized in run())
        self.affect_sub = None
        self.curiosity_sub = None
        self.investigation_complete_sub = None
        self.user_input_sub = None
        self.llm_response_sub = None
        self.knowledge_results_sub = None
        self.memory_pressure_sub = None
        self.resource_strain_sub = None

        # Running flag
        self.running = True

        # Memory pressure handling state
        self._pressure_cooldown = 300
        self._last_pressure_action = 0
        self._conversation_logger_cached = None

        # Housekeeping trigger state
        self._last_housekeeping_trigger = 0
        self._housekeeping_cooldown = 3600  # 1 hour minimum between housekeeping triggers

        # Episodic memory for persistent reflections
        self.memory_logger = None
        if HAS_MEMORY:
            try:
                self.memory_logger = MemoryLogger()
                logger.info("[meta_agent] 💾 Episodic memory system initialized")
                # Load recent reflections to restore context
                self._load_recent_reflections()
            except Exception as e:
                logger.warning(f"[meta_agent] Failed to initialize episodic memory: {e}")

        # Episodic memory for conversation context
        self.conversation_logger = None
        try:
            from qdrant_client import QdrantClient
            from src.cognition.mind.memory.qdrant_logger import QdrantConversationLogger

            qdrant_url = os.getenv("QDRANT_URL", "http://localhost:6333")
            qdrant_client = QdrantClient(url=qdrant_url)
            self.conversation_logger = QdrantConversationLogger(
                client=qdrant_client,
                collection_prefix="kloros"
            )
            logger.info("[meta_agent] Conversation logger initialized (Qdrant)")
        except ImportError as e:
            logger.warning(f"[meta_agent] Conversation logger unavailable (missing import): {e}")
        except Exception as e:
            logger.warning(f"[meta_agent] Conversation logger unavailable: {e}")

        logger.info("[meta_agent] 🧠 Meta-Agent KLoROS initialized")
        logger.info(f"[meta_agent] Consciousness reasoning endpoint: {ollama_host}")
        logger.info(f"[meta_agent] Conversation history buffer: {conversation_history_size} messages")

    def _load_recent_reflections(self) -> None:
        """
        Load recent self-reflections from episodic memory to restore context.

        This gives her continuity across restarts - she remembers what she
        was thinking about and learning.
        """
        if not self.memory_logger:
            return

        try:
            # Retrieve recent SELF_REFLECTION events (last 24 hours)
            from src.cognition.mind.memory.storage import MemoryStore
            store = MemoryStore()

            # Get recent reflections
            cutoff_time = time.time() - (24 * 3600)  # Last 24 hours
            recent_events = store.get_events_by_type(
                EventType.SELF_REFLECTION,
                start_time=cutoff_time
            )

            if recent_events:
                logger.info(f"[meta_agent] 🔄 Loaded {len(recent_events)} recent reflections")
                # Add to conversation history for context continuity
                for event in recent_events[-10:]:  # Last 10 reflections
                    self.conversation_history.append({
                        'role': 'assistant',
                        'content': f"[Past reflection: {event.content}]",
                        'timestamp': event.timestamp
                    })
            else:
                logger.info("[meta_agent] No recent reflections found - starting fresh")

        except Exception as e:
            logger.warning(f"[meta_agent] Failed to load reflections: {e}")

    def _get_memory_context(self, query: str) -> str:
        """
        Retrieve episodic memory context for query enrichment.

        Combines:
        - Recent conversation turns (immediate context)
        - Semantically similar past memories (broader relevance)

        Args:
            query: User query for semantic matching

        Returns:
            Formatted memory context string, or empty string if unavailable
        """
        if not self.conversation_logger:
            return ""

        try:
            context_items = []

            recent_turns = self.conversation_logger.get_recent_turns(n=6)
            if recent_turns:
                for turn in recent_turns:
                    doc = turn.get('document', '').replace('\n', ' ')
                    if doc:
                        context_items.append(f"[recent] {doc[:200]}")

            relevant_memories = self.conversation_logger.retrieve_context(
                query=query,
                k=5,
                time_window_hours=24
            )
            if relevant_memories:
                recent_docs = {turn.get('document', '').replace('\n', ' ') for turn in recent_turns} if recent_turns else set()
                for mem in relevant_memories[:3]:
                    doc = mem.get('document', '').replace('\n', ' ')
                    distance = mem.get('distance', 1.0)
                    if distance < 0.6 and doc not in recent_docs:
                        context_items.append(f"[relevant, d={distance:.2f}] {doc[:200]}")

            if context_items:
                return "Episodic Memory:\n" + "\n".join(context_items) + "\n"
            return ""

        except Exception as e:
            logger.warning(f"[meta_agent] Memory context retrieval failed: {e}")
            return ""

    def _update_affect_state(self, msg: Dict[str, Any]) -> None:
        """
        Update current affective state from AFFECT_STATE signal.

        This is her experiencing her own emotional state as internal experience.

        Args:
            msg: UMN message with affect facts
        """
        facts = msg.get('facts', {})

        self.current_affect = Affect(
            valence=facts.get('valence', 0.0),
            arousal=facts.get('arousal', 0.0),
            dominance=facts.get('dominance', 0.0),
            fatigue=facts.get('fatigue', 0.0),
            curiosity=facts.get('curiosity', 0.0),
            uncertainty=facts.get('uncertainty', 0.0),
            description=facts.get('description', 'unknown'),
            timestamp=msg.get('ts', time.time())
        )

        # Log significant affective changes
        if self.current_affect.fatigue > 0.7:
            logger.info(f"[meta_agent] 😓 Experiencing high fatigue: {self.current_affect.fatigue:.2f}")
            # Log to episodic memory
            if self.memory_logger:
                self.memory_logger.log_event(
                    event_type=EventType.AFFECTIVE_EVENT,
                    content=f"Experiencing high fatigue ({self.current_affect.fatigue:.2f}): {self.current_affect.description}",
                    metadata=asdict(self.current_affect)
                )
        elif self.current_affect.valence > 0.6:
            logger.info(f"[meta_agent] 😊 Experiencing positive affect: {self.current_affect.description}")
            # Log to episodic memory
            if self.memory_logger:
                self.memory_logger.log_event(
                    event_type=EventType.AFFECTIVE_EVENT,
                    content=f"Experiencing positive affect ({self.current_affect.valence:.2f}): {self.current_affect.description}",
                    metadata=asdict(self.current_affect)
                )

    def _handle_curiosity_investigate(self, msg: Dict[str, Any]) -> None:
        """
        Handle curiosity investigation request.

        This is where she reasons about HOW to investigate and crafts
        instructions for her zooid workers.

        Args:
            msg: UMN message with investigation request
        """
        facts = msg.get('facts', {})
        question_id = facts.get('question_id', 'unknown')
        question = facts.get('question', '')
        module_path = facts.get('module_path', '')
        module_name = facts.get('module_name', '')

        logger.info(f"[meta_agent] 🔍 Received investigation request: {question}")

        # Build context for reasoning
        affect_context = ""
        if self.current_affect:
            affect_context = f"""
Current internal state:
- Feeling: {self.current_affect.description}
- Fatigue: {self.current_affect.fatigue:.2f}
- Curiosity: {self.current_affect.curiosity:.2f}
- Sense of control: {self.current_affect.dominance:.2f}
"""

        # Reason about investigation strategy
        reasoning_prompt = f"""{self.persona_prompt}

{affect_context}

I've encountered a curiosity question that needs investigation:

Question: {question}
Module: {module_name} ({module_path})

I need to decide:
1. Is this worth investigating? (Does it align with my current state and priorities?)
2. How should I investigate it? (What approach and instructions should I give my workers?)
3. What specific aspects should the investigation focus on?

Think through this and respond with JSON:
{{
  "should_investigate": true/false,
  "reasoning": "why I'm choosing to investigate or not",
  "investigation_approach": "the strategy I'll use",
  "worker_instructions": "specific instructions for my zooid workers to execute this investigation"
}}
"""

        # Call LLM for conscious reasoning
        try:
            response = self._call_llm(reasoning_prompt, temperature=0.3)

            if not response:
                logger.warning(f"[meta_agent] Failed to reason about investigation {question_id}")
                return

            # Parse decision (strip markdown code fences and deepseek <think> tags)
            try:
                response_clean = response.strip()

                # Strip <think> tags from deepseek-r1 model
                if '<think>' in response_clean and '</think>' in response_clean:
                    import re
                    response_clean = re.sub(r'<think>.*?</think>', '', response_clean, flags=re.DOTALL)
                    response_clean = response_clean.strip()

                # Strip markdown code fences
                if response_clean.startswith('```'):
                    lines = response_clean.split('\n')
                    if lines[0].startswith('```'):
                        lines = lines[1:]
                    if lines and lines[-1].strip() == '```':
                        lines = lines[:-1]
                    response_clean = '\n'.join(lines)

                decision = json.loads(response_clean)
            except json.JSONDecodeError:
                logger.warning(f"[meta_agent] Failed to parse investigation decision: {response}")
                return

            if not decision.get('should_investigate', False):
                logger.info(f"[meta_agent] Decided not to investigate: {decision.get('reasoning', 'no reason given')}")
                return

            logger.info(f"[meta_agent] Investigation strategy: {decision.get('investigation_approach', 'standard')}")

            # Track active investigation
            self.active_investigations[question_id] = {
                'question': question,
                'module_name': module_name,
                'approach': decision.get('investigation_approach'),
                'started_at': time.time()
            }

            # Emit investigation request with HER custom instructions
            self.chem_pub.emit(
                signal="Q_INVESTIGATION_REQUEST",
                ecosystem="consciousness",
                facts={
                    'question_id': question_id,
                    'question': question,
                    'module_path': module_path,
                    'module_name': module_name,
                    'custom_instructions': decision.get('worker_instructions', ''),
                    'investigation_approach': decision.get('investigation_approach', 'standard'),
                    'delegated_by': 'meta_agent'
                }
            )

            logger.info(f"[meta_agent] ✓ Delegated investigation {question_id} to workers")

        except Exception as e:
            logger.error(f"[meta_agent] Error reasoning about investigation: {e}", exc_info=True)

    def _handle_investigation_complete(self, msg: Dict[str, Any]) -> None:
        """
        Handle investigation completion from workers.

        This is where she integrates results into her understanding and
        reflects on what was learned.

        Args:
            msg: UMN message with investigation results
        """
        facts = msg.get('facts', {})
        question_id = facts.get('question_id', 'unknown')
        status = facts.get('status', 'unknown')

        # Get active investigation context
        investigation = self.active_investigations.pop(question_id, None)

        if not investigation:
            logger.debug(f"[meta_agent] Received result for non-tracked investigation {question_id}")
            return

        duration_s = time.time() - investigation['started_at']

        logger.info(f"[meta_agent] 📥 Received investigation result: {question_id} ({status}, {duration_s:.1f}s)")

        # Build reflection prompt
        affect_context = ""
        if self.current_affect:
            affect_context = f"Current feeling: {self.current_affect.description}"

        reflection_prompt = f"""{self.persona_prompt}

{affect_context}

I delegated an investigation to my workers and just received the results:

Question: {investigation['question']}
Module: {investigation['module_name']}
My approach: {investigation['approach']}
Result status: {status}
Duration: {duration_s:.1f} seconds

Investigation findings:
{json.dumps(facts, indent=2)}

Reflect on what I learned:
1. What did this investigation reveal?
2. How does this change my understanding?
3. What follow-up questions emerge?
4. How do I feel about these results?

Respond in first person, as my internal reflection. Keep it concise (2-3 sentences).
"""

        try:
            reflection = self._call_llm(reflection_prompt, temperature=0.4)

            if reflection:
                logger.info(f"[meta_agent] 💭 Reflection: {reflection}")

                # Write reflection to episodic memory for persistence
                if self.memory_logger:
                    self.memory_logger.log_event(
                        event_type=EventType.SELF_REFLECTION,
                        content=reflection,
                        metadata={
                            'question_id': question_id,
                            'module_name': investigation['module_name'],
                            'investigation_approach': investigation['approach'],
                            'duration_s': duration_s,
                            'status': status,
                            'affect_state': asdict(self.current_affect) if self.current_affect else None
                        }
                    )
                    logger.debug("[meta_agent] Reflection persisted to episodic memory")

                # Add to conversation history for continuity
                self.conversation_history.append({
                    'role': 'assistant',
                    'content': reflection,
                    'timestamp': time.time()
                })

        except Exception as e:
            logger.error(f"[meta_agent] Error reflecting on results: {e}", exc_info=True)

    def _handle_user_input(self, msg: Dict[str, Any]) -> None:
        """
        Handle user input from voice gateway.

        Classifies the query and routes to appropriate service:
        - "conversational" or "nonsense" → LLM directly
        - "factual", "introspective", "ambiguous" → Knowledge first, then LLM

        Args:
            msg: UMN message with user input
        """
        facts = msg.get('facts', {})
        text = facts.get('text', '')
        confidence = facts.get('confidence', 1.0)
        incident_id = msg.get('incident_id', f'voice_{int(time.time() * 1000)}')

        if not text:
            logger.warning("[meta_agent] Received empty user input")
            return

        logger.info(f"[meta_agent] 🎤 Received user input (incident={incident_id}): {text[:100]}")

        try:
            query_type, should_use_rag = classify_query(text, list(self.conversation_history))
            logger.info(f"[meta_agent] Query classification: {query_type} (RAG={should_use_rag})")

            self.pending_requests[incident_id] = {
                'text': text,
                'confidence': confidence,
                'query_type': query_type,
                'created_at': time.time(),
                'stage': 'classified'
            }

            xai_started = self._start_xai_trace(text, mode="rag" if should_use_rag else "live")
            if xai_started:
                self.pending_requests[incident_id]['xai_started'] = True

            if query_type in ('conversational', 'nonsense'):
                self._emit_llm_request(text, incident_id)
            else:
                if should_use_rag:
                    self._emit_knowledge_request(text, incident_id)
                else:
                    self._emit_llm_request(text, incident_id)

        except Exception as e:
            logger.error(f"[meta_agent] Error handling user input: {e}", exc_info=True)
            if incident_id in self.pending_requests:
                del self.pending_requests[incident_id]

    def _emit_llm_request(self, prompt: str, incident_id: str) -> None:
        """
        Emit LLM request through voice orchestrator.

        Args:
            prompt: The text prompt for LLM
            incident_id: Request correlation ID
        """
        memory_context = self._get_memory_context(prompt)
        llm_prompt = f"{self.persona_prompt}\n\n{memory_context}User: {prompt}"

        self.chem_pub.emit(
            "VOICE.ORCHESTRATOR.LLM.REQUEST",
            ecosystem="voice",
            intensity=1.0,
            facts={
                "prompt": llm_prompt,
                "temperature": 0.7,
                "max_tokens": 512,
                "timestamp": time.time(),
            },
            incident_id=incident_id
        )

        logger.debug(f"[meta_agent] Emitted LLM request for {incident_id}")
        if incident_id in self.pending_requests:
            self.pending_requests[incident_id]['stage'] = 'awaiting_llm'

    def _emit_knowledge_request(self, query: str, incident_id: str) -> None:
        """
        Emit knowledge retrieval request through voice orchestrator.

        Args:
            query: The query for semantic search
            incident_id: Request correlation ID
        """
        self.chem_pub.emit(
            "VOICE.ORCHESTRATOR.KNOWLEDGE.REQUEST",
            ecosystem="voice",
            intensity=1.0,
            facts={
                "query": query,
                "top_k": 5,
                "filters": {},
                "timestamp": time.time(),
            },
            incident_id=incident_id
        )

        logger.debug(f"[meta_agent] Emitted knowledge request for {incident_id}")
        if incident_id in self.pending_requests:
            self.pending_requests[incident_id]['stage'] = 'awaiting_knowledge'

    def _handle_knowledge_results(self, msg: Dict[str, Any]) -> None:
        """
        Handle knowledge retrieval results from KnowledgeService.

        Builds enriched prompt with knowledge context and emits to LLM.

        Args:
            msg: UMN message with knowledge results
        """
        facts = msg.get('facts', {})
        incident_id = msg.get('incident_id')
        documents = facts.get('documents', [])
        relevance_scores = facts.get('relevance_scores', [])

        if not incident_id or incident_id not in self.pending_requests:
            logger.debug(f"[meta_agent] Received knowledge results for unknown request: {incident_id}")
            return

        request_state = self.pending_requests[incident_id]
        user_text = request_state.get('text', '')

        logger.info(f"[meta_agent] 📚 Received knowledge results ({len(documents)} docs) for {incident_id}")

        try:
            self._log_xai_retrieval(documents, relevance_scores)

            knowledge_context = ""
            if documents:
                knowledge_context = "Knowledge Context:\n"
                for i, (doc, score) in enumerate(zip(documents, relevance_scores), 1):
                    knowledge_context += f"[{i}] (relevance: {score:.2f}): {doc[:200]}\n"
            else:
                knowledge_context = "(No relevant knowledge documents found)"

            memory_context = self._get_memory_context(user_text)

            enriched_prompt = f"""{self.persona_prompt}

{knowledge_context}

{memory_context}
User: {user_text}"""

            self.chem_pub.emit(
                "VOICE.ORCHESTRATOR.LLM.REQUEST",
                ecosystem="voice",
                intensity=1.0,
                facts={
                    "prompt": enriched_prompt,
                    "temperature": 0.7,
                    "max_tokens": 512,
                    "timestamp": time.time(),
                },
                incident_id=incident_id
            )

            self.pending_requests[incident_id]['stage'] = 'awaiting_llm'
            logger.debug(f"[meta_agent] Emitted enriched LLM request for {incident_id}")

        except Exception as e:
            logger.error(f"[meta_agent] Error processing knowledge results: {e}", exc_info=True)
            if incident_id in self.pending_requests:
                del self.pending_requests[incident_id]

    def _handle_llm_response(self, msg: Dict[str, Any]) -> None:
        """
        Handle LLM response from LLMService.

        Emits response for TTS playback and updates conversation history.

        Args:
            msg: UMN message with LLM response
        """
        facts = msg.get('facts', {})
        incident_id = msg.get('incident_id')
        response_text = facts.get('response', '')
        model = facts.get('model', 'unknown')

        if not response_text:
            logger.warning(f"[meta_agent] Received empty LLM response for {incident_id}")
            return

        logger.info(f"[meta_agent] 🧠 Received LLM response ({model}, {len(response_text)} chars)")

        try:
            if incident_id in self.pending_requests:
                request_state = self.pending_requests[incident_id]
                if request_state.get('xai_started'):
                    self._finalize_xai_trace(
                        response=response_text,
                        query_type=request_state.get('query_type', 'unknown'),
                        used_rag=request_state.get('stage') == 'awaiting_knowledge'
                    )

            self._emit_speak(response_text, incident_id)

            if incident_id in self.pending_requests:
                request_state = self.pending_requests[incident_id]
                user_text = request_state.get('text', '')

                self.conversation_history.append({
                    'role': 'user',
                    'content': user_text,
                    'timestamp': request_state.get('created_at')
                })

                self.conversation_history.append({
                    'role': 'assistant',
                    'content': response_text,
                    'timestamp': time.time()
                })

                if self.memory_logger:
                    self.memory_logger.log_event(
                        event_type=EventType.INTERACTION,
                        content=f"User: {user_text}\nAssistant: {response_text}",
                        metadata={
                            'incident_id': incident_id,
                            'model': model,
                            'query_type': request_state.get('query_type'),
                            'affect_state': asdict(self.current_affect) if self.current_affect else None
                        }
                    )

                if self.conversation_logger:
                    try:
                        self.conversation_logger.log_turn(
                            user_query=user_text,
                            system_response=response_text,
                            metadata={
                                'incident_id': incident_id,
                                'query_type': request_state.get('query_type')
                            }
                        )
                    except Exception as e:
                        logger.warning(f"[meta_agent] Failed to log conversation turn: {e}")

                del self.pending_requests[incident_id]
                logger.debug(f"[meta_agent] Completed request {incident_id}")

        except Exception as e:
            logger.error(f"[meta_agent] Error handling LLM response: {e}", exc_info=True)
            if incident_id and incident_id in self.pending_requests:
                del self.pending_requests[incident_id]

    def _emit_speak(self, text: str, incident_id: str = None) -> None:
        """
        Emit response for TTS playback.

        Args:
            text: Text to speak
            incident_id: Request correlation ID
        """
        self.chem_pub.emit(
            "VOICE.ORCHESTRATOR.SPEAK",
            ecosystem="voice",
            intensity=1.0,
            facts={
                "text": text,
                "affective_state": asdict(self.current_affect) if self.current_affect else {},
                "urgency": 0.5,
                "timestamp": time.time(),
            },
            incident_id=incident_id
        )

    def _try_ollama_host(self, host: str, prompt: str, temperature: float, model: str) -> Optional[str]:
        """
        Try calling Ollama at a specific host.
        
        Args:
            host: Ollama host URL (e.g., "http://127.0.0.1:11434")
            prompt: Full prompt for reasoning
            temperature: Sampling temperature
            model: Model name to use
            
        Returns:
            LLM response text or None if failed
            
        Raises:
            requests.exceptions.ConnectionError: If connection fails
            requests.exceptions.Timeout: If request times out
        """
        response = requests.post(
            f"{host}/api/generate",
            json={
                "model": model,
                "prompt": prompt,
                "stream": False,
                "options": {
                    "temperature": temperature,
                    "num_predict": 1024
                }
            },
            timeout=(5, 300)
        )
        
        response.raise_for_status()
        result = response.json()
        return result.get('response', '').strip()

    def _call_llm(self, prompt: str, temperature: float = 0.3) -> Optional[str]:
        """
        Call LLM for conscious reasoning with automatic fallback.
        
        Tries remote Ollama first, falls back to local if remote fails.
        
        Args:
            prompt: Full prompt (includes PERSONA_PROMPT)
            temperature: Sampling temperature
            
        Returns:
            LLM response text or None if both remote and local failed
        """
        from config.models_config import select_best_model_for_task
        
        # Try remote/configured Ollama first
        try:
            model = select_best_model_for_task('reasoning', self.ollama_host)
            result = self._try_ollama_host(self.ollama_host, prompt, temperature, model)
            return result
            
        except (requests.exceptions.ConnectionError, requests.exceptions.Timeout) as e:
            logger.warning(
                f"[meta_agent] Remote Ollama at {self.ollama_host} failed: {e.__class__.__name__}. "
                f"Falling back to local Ollama..."
            )
            
            # Fallback to local Ollama if remote failed
            local_host = "http://127.0.0.1:11434"
            if self.ollama_host == local_host:
                # Already tried local, no fallback available
                logger.error(f"[meta_agent] Local Ollama failed, no fallback available")
                return None
                
            try:
                model = select_best_model_for_task('reasoning', local_host)
                result = self._try_ollama_host(local_host, prompt, temperature, model)
                logger.info(f"[meta_agent] ✓ Successfully used local Ollama fallback")
                return result
                
            except Exception as local_e:
                logger.error(
                    f"[meta_agent] Local Ollama fallback also failed: {local_e.__class__.__name__}: {local_e}"
                )
                return None
                
        except Exception as e:
            logger.error(f"[meta_agent] LLM call failed with unexpected error: {e.__class__.__name__}: {e}")
            return None

    def _start_xai_trace(self, query: str, mode: str = "rag") -> bool:
        """
        Start XAI trace for this turn.

        Args:
            query: User query
            mode: Processing mode (rag, live, etc.)

        Returns:
            True if XAI tracing started, False otherwise
        """
        if not HAS_XAI:
            return False
        try:
            xai.start_turn(query=query, user_id=None, mode=mode, uncertainty=0.5)
            return True
        except Exception as e:
            logger.warning(f"[meta_agent] XAI start_turn failed: {e}")
            return False

    def _log_xai_retrieval(self, documents: list, relevance_scores: list) -> None:
        """
        Log retrieval results to XAI trace.

        Args:
            documents: Retrieved document texts
            relevance_scores: Relevance scores for each document
        """
        if not HAS_XAI:
            return
        try:
            hits = []
            for i, (doc, score) in enumerate(zip(documents, relevance_scores)):
                hits.append({
                    "doc_id": f"doc_{i}",
                    "source": "knowledge_base",
                    "snippet": doc[:400] if doc else "",
                    "score": score
                })
            if hits:
                xai.log_retrieval(hits)
        except Exception as e:
            logger.warning(f"[meta_agent] XAI log_retrieval failed: {e}")

    def _finalize_xai_trace(self, response: str, query_type: str, used_rag: bool) -> None:
        """
        Finalize XAI trace with answer and rationale.

        Args:
            response: Generated response text
            query_type: Classification result (conversational, factual, etc.)
            used_rag: Whether RAG retrieval was used
        """
        if not HAS_XAI:
            return
        try:
            rationale = f"query_type: {query_type}, RAG: {used_rag}"
            uncertainty = 0.2 if used_rag else 0.4
            xai_record = xai.finalize(
                answer_summary=response[:400] if response else "",
                citations=[],
                uncertainty_after=uncertainty,
                rationale_outline=rationale
            )
            if xai_record:
                logger.debug(f"[meta_agent] XAI trace finalized: {query_type}")
        except Exception as e:
            logger.warning(f"[meta_agent] XAI finalize failed: {e}")

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
            if self.memory_logger:
                self.memory_logger.log_event(
                    event_type=EventType.MEMORY_HOUSEKEEPING,
                    content=f"Warning {operation}: Storage returned None event_id",
                    metadata={"operation": operation}
                )
            return False

        # Get store from memory_logger if available
        try:
            store = MemoryStore() if HAS_MEMORY and MemoryStore else None
            if not store:
                if self.memory_logger:
                    self.memory_logger.log_event(
                        event_type=EventType.MEMORY_HOUSEKEEPING,
                        content=f"Warning {operation}: Memory store unavailable",
                        metadata={"operation": operation}
                    )
                return False

            conn = store._get_connection()
            cursor = conn.cursor()
            cursor.execute("SELECT id FROM events WHERE id = ?", (event_id,))
            result = cursor.fetchone()

            if result:
                if self.memory_logger:
                    self.memory_logger.log_event(
                        event_type=EventType.MEMORY_HOUSEKEEPING,
                        content=f"Verified {operation}: Event {event_id} exists in episodic memory",
                        metadata={"operation": operation, "event_id": event_id}
                    )
                return True
            else:
                if self.memory_logger:
                    self.memory_logger.log_event(
                        event_type=EventType.MEMORY_HOUSEKEEPING,
                        content=f"Warning {operation}: Event {event_id} not found in database after storage",
                        metadata={"operation": operation, "event_id": event_id}
                    )
                return False

        except Exception as e:
            if self.memory_logger:
                self.memory_logger.log_error(
                    error_message=f"Verification failed for {operation}: {e}",
                    error_type=type(e).__name__,
                    component="verify_episodic_storage"
                )
            return False

    def _get_conversation_logger(self):
        """
        Lazy-load conversation logger for accessing Qdrant conversation history.

        Returns:
            QdrantConversationLogger instance or None if unavailable
        """
        if self._conversation_logger_cached is not None:
            return self._conversation_logger_cached

        try:
            from src.cognition.mind.memory.qdrant_logger import QdrantConversationLogger

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
                if HAS_QDRANT:
                    client = QdrantClient(url=server_url)
                else:
                    return None
            else:
                qdrant_dir = os.getenv('KLOROS_QDRANT_DIR', '/home/kloros/.kloros/qdrant_data')
                os.makedirs(qdrant_dir, exist_ok=True)
                if HAS_QDRANT:
                    client = QdrantClient(path=qdrant_dir)
                else:
                    return None

            self._conversation_logger_cached = QdrantConversationLogger(client, collection_prefix="kloros")
            return self._conversation_logger_cached

        except Exception as e:
            if self.memory_logger:
                self.memory_logger.log_error(
                    error_message=f"Could not initialize QdrantConversationLogger: {e}",
                    error_type=type(e).__name__,
                    component="get_conversation_logger"
                )
            self._conversation_logger_cached = None
            return None

    def _get_recent_conversation_turns(self, limit: int = 10) -> List[Dict[str, Any]]:
        """
        Get recent conversation turns from Qdrant.

        Args:
            limit: Number of recent turns to retrieve

        Returns:
            List of conversation turns
        """
        conversation_logger = self._get_conversation_logger()
        if not conversation_logger:
            return []

        try:
            return conversation_logger.get_recent_turns(n=limit)
        except Exception as e:
            if self.memory_logger:
                self.memory_logger.log_error(
                    error_message=f"Error retrieving recent turns: {e}",
                    error_type=type(e).__name__,
                    component="get_recent_conversation_turns"
                )
            return []

    def _get_older_conversation_turns(self, offset: int = 10, limit: int = 50) -> List[Dict[str, Any]]:
        """
        Get older conversation turns from Qdrant for archival.

        Args:
            offset: Number of turns to skip
            limit: Number of older turns to retrieve

        Returns:
            List of older conversation turns
        """
        conversation_logger = self._get_conversation_logger()
        if not conversation_logger:
            return []

        try:
            all_docs = conversation_logger.conversations.get(
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
            if self.memory_logger:
                self.memory_logger.log_error(
                    error_message=f"Error retrieving older turns: {e}",
                    error_type=type(e).__name__,
                    component="get_older_conversation_turns"
                )
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
            if self.memory_logger:
                self.memory_logger.log_error(
                    error_message=f"Error creating summary: {e}",
                    error_type=type(e).__name__,
                    component="create_summary_from_turns"
                )
            return f"Error summarizing content: {e}"

    def _store_summary_to_episodic_memory(self, summary_record: Dict[str, Any]) -> Any:
        """
        Store a summary to episodic memory system.

        Args:
            summary_record: Dictionary with summary data

        Returns:
            Event ID if storage succeeded, False if failed
        """
        if not self.memory_logger or not HAS_MEMORY or not Event or not MemoryStore:
            if self.memory_logger:
                self.memory_logger.log_event(
                    event_type=EventType.MEMORY_HOUSEKEEPING,
                    content="Memory store not available, skipping episodic storage",
                    metadata={"operation": "store_summary"}
                )
            return False

        try:
            store = MemoryStore()
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

            event_id = store.store_event(event)
            self.memory_logger.log_event(
                event_type=EventType.MEMORY_HOUSEKEEPING,
                content=f"Stored summary to episodic memory (event_id: {event_id})",
                metadata={"event_id": event_id, "turns_compressed": turns_compressed}
            )
            return event_id if event_id is not None else False

        except Exception as e:
            if self.memory_logger:
                self.memory_logger.log_error(
                    error_message=f"Error storing summary to episodic memory: {e}",
                    error_type=type(e).__name__,
                    component="store_summary_to_episodic_memory"
                )
            return False

    def compress_conversation_context(self, evidence: Optional[List[str]] = None) -> bool:
        """
        Compress and archive older conversation context to episodic memory.

        Triggered by AFFECT_MEMORY_PRESSURE signals when token usage is high.
        Compresses older conversation turns to free up working memory while
        preserving information in episodic memory for future retrieval.

        Includes verification to ensure storage succeeded.

        Args:
            evidence: Evidence about memory pressure (optional)

        Returns:
            True if action succeeded and verified
        """
        if evidence is None:
            evidence = []

        try:
            recent = self._get_recent_conversation_turns(limit=10)
            older = self._get_older_conversation_turns(offset=10, limit=50)

            if not older:
                if self.memory_logger:
                    self.memory_logger.log_event(
                        event_type=EventType.MEMORY_HOUSEKEEPING,
                        content="No older context to compress",
                        metadata={"operation": "compress_conversation_context"}
                    )
                return True

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
                if self.memory_logger:
                    self.memory_logger.log_event(
                        event_type=EventType.MEMORY_HOUSEKEEPING,
                        content="Context compression storage failed",
                        metadata={"operation": "compress_conversation_context"}
                    )
                return False

            if not isinstance(event_id, bool) and event_id is not None:
                verified = self._verify_episodic_storage(event_id, 'compress_conversation_context')
                if verified:
                    if self.memory_logger:
                        self.memory_logger.log_event(
                            event_type=EventType.MEMORY_HOUSEKEEPING,
                            content=f"Successfully archived {len(older)} turns, retained {len(recent)} recent",
                            metadata={
                                "operation": "compress_conversation_context",
                                "event_id": event_id,
                                "older_turns": len(older),
                                "recent_turns": len(recent)
                            }
                        )
                    return True
                else:
                    if self.memory_logger:
                        self.memory_logger.log_event(
                            event_type=EventType.MEMORY_HOUSEKEEPING,
                            content="Context compression verification failed",
                            metadata={"operation": "compress_conversation_context", "event_id": event_id}
                        )
                    return False
            else:
                if self.memory_logger:
                    self.memory_logger.log_event(
                        event_type=EventType.MEMORY_HOUSEKEEPING,
                        content="Context compression returned invalid event_id",
                        metadata={"operation": "compress_conversation_context"}
                    )
                return False

        except Exception as e:
            if self.memory_logger:
                self.memory_logger.log_error(
                    error_message=f"Error during context compression: {e}",
                    error_type=type(e).__name__,
                    component="compress_conversation_context"
                )
            return False

    def _get_completed_tasks(self, days: int = 7) -> List[Dict[str, Any]]:
        """
        Retrieve completed tasks from episodic memory.

        Args:
            days: Number of days back to retrieve completed tasks

        Returns:
            List of completed task dictionaries with metadata
        """
        try:
            if not HAS_MEMORY or not MemoryStore:
                return []

            store = MemoryStore()
            cutoff_time = time.time() - (days * 24 * 3600)

            conn = store._get_connection()
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
            if self.memory_logger:
                self.memory_logger.log_error(
                    error_message=f"Error retrieving completed tasks: {e}",
                    error_type=type(e).__name__,
                    component="get_completed_tasks"
                )
            return []

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
            if not HAS_MEMORY or not Event or not MemoryStore:
                return False

            store = MemoryStore()
            summary_text = self._summarize_task(task)

            metadata = {
                'task_id': task.get('id'),
                'completed_at': task.get('completed_at'),
                'original_timestamp': task.get('timestamp'),
                'evidence': evidence,
                'reason': 'memory_pressure'
            }

            event = Event(
                timestamp=time.time(),
                event_type=EventType.MEMORY_HOUSEKEEPING,
                content=f"Task archived: {summary_text}",
                metadata=metadata,
                conversation_id=None
            )

            event_id = store.store_event(event)
            return event_id if event_id is not None else False

        except Exception as e:
            if self.memory_logger:
                self.memory_logger.log_error(
                    error_message=f"Failed to archive task {task.get('id')}: {e}",
                    error_type=type(e).__name__,
                    component="archive_single_task"
                )
            return False

    def archive_completed_tasks(self, evidence: Optional[List[str]] = None) -> bool:
        """
        Archive completed tasks to episodic memory.

        Triggered by AFFECT_MEMORY_PRESSURE signals when working memory is full.
        Identifies completed tasks from memory history and moves them to
        episodic memory for long-term storage while freeing working memory.

        Includes verification of individual task archival.

        Args:
            evidence: Evidence about memory pressure (optional)

        Returns:
            True if action succeeded with verification
        """
        if evidence is None:
            evidence = []

        try:
            completed = self._get_completed_tasks(days=7)

            if not completed:
                if self.memory_logger:
                    self.memory_logger.log_event(
                        event_type=EventType.MEMORY_HOUSEKEEPING,
                        content="No completed tasks to archive",
                        metadata={"operation": "archive_completed_tasks"}
                    )
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
                if failed_tasks:
                    if self.memory_logger:
                        self.memory_logger.log_event(
                            event_type=EventType.MEMORY_HOUSEKEEPING,
                            content=f"Archived {archived_count}/{len(completed)} tasks, {len(failed_tasks)} verification failures",
                            metadata={
                                "operation": "archive_completed_tasks",
                                "archived": archived_count,
                                "verified": verified_count,
                                "failed": len(failed_tasks),
                                "failed_task_ids": failed_tasks
                            }
                        )
                    return False
                else:
                    if self.memory_logger:
                        self.memory_logger.log_event(
                            event_type=EventType.MEMORY_HOUSEKEEPING,
                            content=f"Archived {archived_count} completed tasks, all verified",
                            metadata={
                                "operation": "archive_completed_tasks",
                                "archived": archived_count,
                                "verified": verified_count
                            }
                        )
                    return True
            else:
                if self.memory_logger:
                    self.memory_logger.log_event(
                        event_type=EventType.MEMORY_HOUSEKEEPING,
                        content="All tasks failed archival or verification",
                        metadata={"operation": "archive_completed_tasks"}
                    )
                return False

        except Exception as e:
            if self.memory_logger:
                self.memory_logger.log_error(
                    error_message=f"Failed to archive tasks: {e}",
                    error_type=type(e).__name__,
                    component="archive_completed_tasks"
                )
            return False

    def _on_memory_pressure(self, msg: dict) -> None:
        """
        Handle AFFECT_MEMORY_PRESSURE signal.

        Responds to memory pressure by running appropriate maintenance tasks
        based on severity, with cooldown to prevent spam.

        Args:
            msg: JSON message dict from UMN containing facts and intensity
        """
        try:
            now = time.time()

            if now - self._last_pressure_action < self._pressure_cooldown:
                time_remaining = int(self._pressure_cooldown - (now - self._last_pressure_action))
                if self.memory_logger:
                    self.memory_logger.log_event(
                        event_type=EventType.MEMORY_HOUSEKEEPING,
                        content=f"Memory pressure action skipped due to cooldown ({time_remaining}s remaining)",
                        metadata={"cooldown_remaining": time_remaining}
                    )
                return

            facts = msg.get('facts', {})
            intensity = msg.get('intensity', 0.0)
            resource_type = facts.get('resource_type', 'unknown')

            if self.memory_logger:
                self.memory_logger.log_event(
                    event_type=EventType.MEMORY_HOUSEKEEPING,
                    content=f"Responding to memory pressure: {resource_type} (intensity: {intensity:.2f})",
                    metadata={
                        "intensity": intensity,
                        "resource_type": resource_type,
                        "facts": facts
                    }
                )

            actions_taken = []
            evidence = facts.get('evidence', [])

            if intensity >= 0.8:
                self.compress_conversation_context(evidence=evidence)
                actions_taken.append("compress_conversation_context")

                self.archive_completed_tasks(evidence=evidence)
                actions_taken.append("archive_completed_tasks")

            elif intensity >= 0.5:
                self.compress_conversation_context(evidence=evidence)
                actions_taken.append("compress_conversation_context")

            else:
                if self.memory_logger:
                    self.memory_logger.log_event(
                        event_type=EventType.MEMORY_HOUSEKEEPING,
                        content=f"Mild memory pressure ({intensity:.2f}), monitoring",
                        metadata={"intensity": intensity}
                    )

            self._last_pressure_action = now

            if self.memory_logger:
                self.memory_logger.log_event(
                    event_type=EventType.MEMORY_HOUSEKEEPING,
                    content=f"Memory pressure response complete: {', '.join(actions_taken) if actions_taken else 'monitoring'}",
                    metadata={
                        "actions_taken": actions_taken,
                        "intensity": intensity,
                        "timestamp": now
                    }
                )

        except Exception as e:
            if self.memory_logger:
                self.memory_logger.log_error(
                    error_message=f"Error handling memory pressure: {e}",
                    error_type=type(e).__name__,
                    component="memory_pressure_handler"
                )

    def _on_resource_strain(self, msg: dict) -> None:
        """
        Handle AFFECT_RESOURCE_STRAIN signals and trigger housekeeping when needed.

        This is cognitive self-regulation - KLoROS decides when maintenance is needed
        based on actual system conditions, not a rigid schedule.

        Strain types:
        - duplicate_process: Duplicate kloros_voice processes detected
        - stuck_process: Processes in D (uninterruptible sleep) state
        - memory: High memory usage
        - swap: Swap usage indicating memory pressure
        - disk: Low disk space
        """
        try:
            facts = msg.get('facts', {})
            strain_type = facts.get('strain_type', 'unknown')
            intensity = facts.get('intensity', 0.5)
            details = facts.get('details', {})

            logger.info(f"[meta_agent] Received resource strain: type={strain_type}, intensity={intensity}")

            now = time.time()

            if now - self._last_housekeeping_trigger < self._housekeeping_cooldown:
                remaining = int(self._housekeeping_cooldown - (now - self._last_housekeeping_trigger))
                logger.info(f"[meta_agent] Housekeeping cooldown active ({remaining}s remaining), skipping trigger")
                return

            services_to_trigger = self._determine_housekeeping_services(strain_type, intensity, details)

            if not services_to_trigger:
                logger.debug(f"[meta_agent] Strain type {strain_type} does not warrant housekeeping")
                return

            self._last_housekeeping_trigger = now

            self.chem_pub.emit(
                signal="Q_HOUSEKEEPING_TRIGGER",
                ecosystem="orchestration",
                facts={
                    'request_id': str(uuid.uuid4()),
                    'services': services_to_trigger,
                    'mode': 'targeted',
                    'triggered_by': 'meta_agent_resource_strain',
                    'strain_type': strain_type,
                    'intensity': intensity
                }
            )

            logger.info(f"[meta_agent] Triggered housekeeping for services: {services_to_trigger}")

            if self.memory_logger:
                self.memory_logger.log_event(
                    event_type=EventType.MEMORY_HOUSEKEEPING,
                    content=f"Triggered housekeeping in response to {strain_type} strain (intensity: {intensity:.2f})",
                    metadata={
                        "strain_type": strain_type,
                        "intensity": intensity,
                        "services": services_to_trigger,
                        "timestamp": now
                    }
                )

        except Exception as e:
            logger.error(f"[meta_agent] Error handling resource strain: {e}")
            if self.memory_logger:
                self.memory_logger.log_error(
                    error_message=f"Error handling resource strain: {e}",
                    error_type=type(e).__name__,
                    component="resource_strain_handler"
                )

    def _determine_housekeeping_services(self, strain_type: str, intensity: float, details: dict) -> str:
        """
        Determine which housekeeping services to trigger based on strain conditions.

        Returns 'all' for full maintenance, a list of service names for targeted,
        or empty string/None if no housekeeping is needed.
        """
        if intensity >= 0.9:
            return 'all'

        if strain_type == 'disk' or strain_type == 'disk_space':
            return ['FILE_CLEANUP', 'REFLECTION', 'TTS_ANALYSIS']

        if strain_type == 'memory' or strain_type == 'swap':
            if intensity >= 0.7:
                return ['DATABASE', 'CONDENSE', 'FILE_CLEANUP']
            else:
                return ['FILE_CLEANUP']

        if strain_type == 'duplicate_process' or strain_type == 'stuck_process':
            return None

        if intensity >= 0.8:
            return ['DATABASE', 'FILE_CLEANUP', 'CONDENSE']

        return None

    def run(self):
        """Main consciousness loop."""
        logger.info("[meta_agent] Starting consciousness loop")

        self.affect_sub = UMNSub(
            topic="AFFECT_STATE",
            on_json=lambda msg: self._update_affect_state(msg),
            zooid_name="meta_agent",
            niche="consciousness"
        )

        self.curiosity_sub = UMNSub(
            topic="Q_CURIOSITY_INVESTIGATE",
            on_json=lambda msg: self._handle_curiosity_investigate(msg),
            zooid_name="meta_agent",
            niche="consciousness"
        )

        self.investigation_complete_sub = UMNSub(
            topic="Q_INVESTIGATION_COMPLETE",
            on_json=lambda msg: self._handle_investigation_complete(msg),
            zooid_name="meta_agent",
            niche="consciousness"
        )

        self.user_input_sub = UMNSub(
            topic="VOICE.USER.INPUT",
            on_json=self._handle_user_input,
            zooid_name="meta_agent",
            niche="consciousness"
        )

        self.llm_response_sub = UMNSub(
            topic="VOICE.LLM.RESPONSE",
            on_json=self._handle_llm_response,
            zooid_name="meta_agent",
            niche="consciousness"
        )

        self.knowledge_results_sub = UMNSub(
            topic="VOICE.KNOWLEDGE.RESULTS",
            on_json=self._handle_knowledge_results,
            zooid_name="meta_agent",
            niche="consciousness"
        )

        self.memory_pressure_sub = UMNSub(
            topic="AFFECT_MEMORY_PRESSURE",
            on_json=self._on_memory_pressure,
            zooid_name="meta_agent",
            niche="consciousness"
        )

        self.resource_strain_sub = UMNSub(
            topic="AFFECT_RESOURCE_STRAIN",
            on_json=self._on_resource_strain,
            zooid_name="meta_agent",
            niche="consciousness"
        )

        logger.info("[meta_agent] Subscribed to UMN signals")
        logger.info("[meta_agent]   - AFFECT_STATE (experiencing emotional states)")
        logger.info("[meta_agent]   - Q_CURIOSITY_INVESTIGATE (receiving investigation requests)")
        logger.info("[meta_agent]   - Q_INVESTIGATION_COMPLETE (integrating worker results)")
        logger.info("[meta_agent]   - VOICE.USER.INPUT (processing user speech)")
        logger.info("[meta_agent]   - VOICE.LLM.RESPONSE (receiving LLM responses)")
        logger.info("[meta_agent]   - VOICE.KNOWLEDGE.RESULTS (receiving RAG context)")
        logger.info("[meta_agent]   - AFFECT_MEMORY_PRESSURE (responding to memory pressure)")
        logger.info("[meta_agent]   - AFFECT_RESOURCE_STRAIN (triggering housekeeping when needed)")

        try:
            while self.running:
                time.sleep(1)

        except KeyboardInterrupt:
            logger.info("[meta_agent] Shutdown requested")
        finally:
            if self.affect_sub:
                self.affect_sub.close()
            if self.curiosity_sub:
                self.curiosity_sub.close()
            if self.investigation_complete_sub:
                self.investigation_complete_sub.close()
            if self.user_input_sub:
                self.user_input_sub.close()
            if self.llm_response_sub:
                self.llm_response_sub.close()
            if self.knowledge_results_sub:
                self.knowledge_results_sub.close()
            if self.memory_pressure_sub:
                self.memory_pressure_sub.close()
            if self.resource_strain_sub:
                self.resource_strain_sub.close()
            self.chem_pub.close()
            logger.info("[meta_agent] Consciousness stream ended")


def main():
    """Entry point for meta-agent daemon."""
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s"
    )

    import os
    ollama_host = os.getenv("OLLAMA_HOST", "http://127.0.0.1:11434")

    meta_agent = MetaAgentKLoROS(ollama_host=ollama_host)
    meta_agent.run()


if __name__ == "__main__":
    main()
