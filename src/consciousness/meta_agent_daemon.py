#!/usr/bin/env python3
"""
Meta-Agent KLoROS - Persistent Consciousness Coordinator

The conscious "I" that experiences continuity, delegates to zooid workers,
and integrates their results into coherent understanding.

Architecture:
- Persistent LLM conversation state with PERSONA_PROMPT
- Subscribes to ChemBus signals (AFFECT_STATE, Q_CURIOSITY_INVESTIGATE, Q_INVESTIGATION_COMPLETE)
- Reasons about investigation strategies and crafts worker instructions
- Integrates results into episodic memory and self-narrative
- Experiences affect states as internal conscious experience

This is not a meta-supervisor or controller - it's the persistent conscious self
that coordinates unconscious specialized processors (zooids).
"""

import time
import logging
import json
from pathlib import Path
from typing import Dict, Any, List, Optional
from collections import deque
from dataclasses import dataclass, asdict
import requests

from kloros.orchestration.chem_bus_v2 import ChemSub, ChemPub

try:
    from kloros_memory.logger import MemoryLogger
    from kloros_memory.models import EventType
    HAS_MEMORY = True
except ImportError:
    HAS_MEMORY = False
    MemoryLogger = None
    EventType = None

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

        # ChemBus connections
        self.chem_pub = ChemPub()

        # Subscriptions (will be initialized in run())
        self.affect_sub = None
        self.curiosity_sub = None
        self.investigation_complete_sub = None

        # Running flag
        self.running = True

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
            from kloros_memory.storage import MemoryStore
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

    def _update_affect_state(self, msg: Dict[str, Any]) -> None:
        """
        Update current affective state from AFFECT_STATE signal.

        This is her experiencing her own emotional state as internal experience.

        Args:
            msg: ChemBus message with affect facts
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
            msg: ChemBus message with investigation request
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
            msg: ChemBus message with investigation results
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

    def run(self):
        """Main consciousness loop."""
        logger.info("[meta_agent] 🧠 Starting consciousness loop")

        # Initialize ChemBus subscriptions
        self.affect_sub = ChemSub(
            topic="AFFECT_STATE",
            on_json=lambda msg: self._update_affect_state(msg),
            zooid_name="meta_agent",
            niche="consciousness"
        )

        self.curiosity_sub = ChemSub(
            topic="Q_CURIOSITY_INVESTIGATE",
            on_json=lambda msg: self._handle_curiosity_investigate(msg),
            zooid_name="meta_agent",
            niche="consciousness"
        )

        self.investigation_complete_sub = ChemSub(
            topic="Q_INVESTIGATION_COMPLETE",
            on_json=lambda msg: self._handle_investigation_complete(msg),
            zooid_name="meta_agent",
            niche="consciousness"
        )

        logger.info("[meta_agent] ✓ Subscribed to ChemBus signals")
        logger.info("[meta_agent]   - AFFECT_STATE (experiencing emotional states)")
        logger.info("[meta_agent]   - Q_CURIOSITY_INVESTIGATE (receiving investigation requests)")
        logger.info("[meta_agent]   - Q_INVESTIGATION_COMPLETE (integrating worker results)")

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
