#!/usr/bin/env python3
"""
Session Management Service for KLoROS Voice System (Phase 5)

Responsibility:
- Conversation history management
- Context window truncation strategies
- Session state persistence (filesystem + TOON snapshots)
- Session metadata tracking

UMN Signals:
- Emits:   VOICE.SESSION.UPDATED         (session_id, message_count, context_size)
- Emits:   VOICE.SESSION.SNAPSHOT.SAVED  (file_path, compression_ratio)
- Listens: VOICE.STT.TRANSCRIPTION       (append user utterance)
- Listens: VOICE.LLM.RESPONSE            (append assistant response)

Dependencies:
- Filesystem persistence
- Optional: TOON compression library

Fail-Safe:
- If this service is down, orchestrator operates in stateless mode (no conversation memory)
"""

import os
import sys
import time
import json
import signal
import uuid
from pathlib import Path
from typing import List, Dict, Any, Optional
from datetime import datetime

from src.orchestration.core.umn_bus import UMNPub, UMNSub


class SessionService:
    """Session Management service - conversation history, state persistence, context truncation."""

    def __init__(self):
        self.service_name = "kloros-voice-session"
        self.niche = "voice.session"

        # Session state
        self.session_id = str(uuid.uuid4())
        self.conversation_history: List[Dict[str, str]] = []
        self.max_history_entries = int(os.getenv("KLR_SESSION_MAX_ENTRIES", "100"))
        self.session_start_time = time.time()

        # Persistence configuration
        self.persist_enabled = os.getenv("KLR_SESSION_PERSIST", "1") == "1"
        self.persist_dir = Path(os.getenv("KLR_SESSION_PERSIST_DIR", str(Path.home() / "KLoROS")))
        self.persist_file = self.persist_dir / "kloros_voice_session.json"
        self.auto_save_interval = int(os.getenv("KLR_SESSION_AUTOSAVE_INTERVAL", "300"))  # 5 minutes
        self.last_save_time = time.time()

        # Statistics
        self.stats = {
            "total_messages": 0,
            "user_messages": 0,
            "assistant_messages": 0,
            "truncations": 0,
            "saves": 0,
            "loads": 0,
            "snapshots": 0
        }

        # UMN publishers/subscribers (initialized in start())
        self.chem_pub: Optional[UMNPub] = None
        self.stt_sub: Optional[UMNSub] = None
        self.llm_sub: Optional[UMNSub] = None

        # Running state
        self.running = False

        print(f"[session] SessionService initialized (session_id={self.session_id}, max_entries={self.max_history_entries})")

    def start(self):
        """Initialize UMN connections and load persisted state."""
        print("[session] Starting Session Management service...")

        # Initialize UMN publisher
        try:
            self.chem_pub = UMNPub()
            print("[session] UMN publisher initialized")
        except Exception as e:
            print(f"[session] CRITICAL: Failed to initialize UMNPub: {e}")
            sys.exit(1)

        # Load persisted session state
        if self.persist_enabled:
            self._load_session_state()

        # Subscribe to VOICE.STT.TRANSCRIPTION
        try:
            self.stt_sub = UMNSub(
                "VOICE.STT.TRANSCRIPTION",
                self._on_stt_transcription,
                zooid_name=self.service_name,
                niche=self.niche
            )
            print("[session] Subscribed to VOICE.STT.TRANSCRIPTION")
        except Exception as e:
            print(f"[session] ERROR: Failed to subscribe to VOICE.STT.TRANSCRIPTION: {e}")
            sys.exit(1)

        # Subscribe to VOICE.LLM.RESPONSE
        try:
            self.llm_sub = UMNSub(
                "VOICE.LLM.RESPONSE",
                self._on_llm_response,
                zooid_name=self.service_name,
                niche=self.niche
            )
            print("[session] Subscribed to VOICE.LLM.RESPONSE")
        except Exception as e:
            print(f"[session] ERROR: Failed to subscribe to VOICE.LLM.RESPONSE: {e}")
            sys.exit(1)

        # Emit ready signal
        self.chem_pub.emit(
            "VOICE.SESSION.READY",
            ecosystem="voice",
            intensity=1.0,
            facts={
                "session_id": self.session_id,
                "max_entries": self.max_history_entries,
                "persist_enabled": self.persist_enabled,
                "message_count": len(self.conversation_history)
            },
            incident_id=f"session-ready-{int(time.time())}"
        )

        self.running = True
        print("[session] Session Management service ready")

    def _on_stt_transcription(self, event: dict) -> None:
        """Handle VOICE.STT.TRANSCRIPTION signal - append user utterance to session."""
        facts = event.get("facts", {})
        text = facts.get("text", "")
        confidence = facts.get("confidence", 0.0)
        timestamp = facts.get("timestamp", time.time())

        if not text:
            print("[session] WARNING: Received empty transcription, skipping")
            return

        # Append user message to conversation history
        message = {
            "role": "user",
            "content": text,
            "timestamp": timestamp,
            "confidence": confidence
        }

        self.conversation_history.append(message)
        self.stats["total_messages"] += 1
        self.stats["user_messages"] += 1

        # Trim history if needed
        self._trim_conversation_history()

        # Emit session updated signal
        self._emit_session_updated()

        # Auto-save if interval elapsed
        self._maybe_auto_save()

        print(f"[session] Appended user message ({len(text)} chars, confidence={confidence:.2f})")

    def _on_llm_response(self, event: dict) -> None:
        """Handle VOICE.LLM.RESPONSE signal - append assistant response to session."""
        facts = event.get("facts", {})
        response = facts.get("response", "")
        model = facts.get("model", "unknown")
        backend = facts.get("backend", "unknown")
        timestamp = facts.get("timestamp", time.time())

        if not response:
            print("[session] WARNING: Received empty LLM response, skipping")
            return

        # Append assistant message to conversation history
        message = {
            "role": "assistant",
            "content": response,
            "timestamp": timestamp,
            "model": model,
            "backend": backend
        }

        self.conversation_history.append(message)
        self.stats["total_messages"] += 1
        self.stats["assistant_messages"] += 1

        # Trim history if needed
        self._trim_conversation_history()

        # Emit session updated signal
        self._emit_session_updated()

        # Auto-save if interval elapsed
        self._maybe_auto_save()

        print(f"[session] Appended assistant message ({len(response)} chars, model={model})")

    def _trim_conversation_history(self) -> None:
        """Keep only the most recent conversation entries to prevent unbounded memory growth."""
        if len(self.conversation_history) > self.max_history_entries:
            trimmed_count = len(self.conversation_history) - self.max_history_entries
            self.conversation_history = self.conversation_history[-self.max_history_entries:]
            self.stats["truncations"] += 1
            print(f"[session] Trimmed conversation history: removed {trimmed_count} old entries, kept {self.max_history_entries}")

    def _emit_session_updated(self) -> None:
        """Emit VOICE.SESSION.UPDATED signal with current session metadata."""
        context_size = sum(len(msg.get("content", "")) for msg in self.conversation_history)

        self.chem_pub.emit(
            "VOICE.SESSION.UPDATED",
            ecosystem="voice",
            intensity=0.5,
            facts={
                "session_id": self.session_id,
                "message_count": len(self.conversation_history),
                "user_messages": self.stats["user_messages"],
                "assistant_messages": self.stats["assistant_messages"],
                "context_size": context_size,
                "timestamp": time.time()
            },
            incident_id=f"session-update-{int(time.time())}"
        )

    def _maybe_auto_save(self) -> None:
        """Auto-save session state if auto_save_interval has elapsed."""
        if not self.persist_enabled:
            return

        elapsed = time.time() - self.last_save_time
        if elapsed >= self.auto_save_interval:
            self._save_session_state()

    def _save_session_state(self) -> None:
        """Save session state to filesystem (JSON)."""
        if not self.persist_enabled:
            return

        try:
            # Ensure persist directory exists
            self.persist_dir.mkdir(parents=True, exist_ok=True)

            # Build session state document
            state = {
                "session_id": self.session_id,
                "session_start_time": self.session_start_time,
                "conversations": self.conversation_history,
                "stats": self.stats,
                "last_save_time": time.time()
            }

            # Write to disk with atomic rename
            temp_file = self.persist_file.with_suffix(".tmp")
            with open(temp_file, 'w') as f:
                json.dump(state, f, indent=2)

            temp_file.replace(self.persist_file)

            self.last_save_time = time.time()
            self.stats["saves"] += 1

            print(f"[session] Saved session state ({len(self.conversation_history)} messages, {self.persist_file})")

        except Exception as e:
            print(f"[session] ERROR: Failed to save session state: {e}")

    def _load_session_state(self) -> None:
        """Load session state from filesystem (JSON)."""
        if not self.persist_file.exists():
            print("[session] No persisted session state found, starting fresh")
            return

        try:
            with open(self.persist_file, 'r') as f:
                data = json.load(f)

            # Restore session ID
            self.session_id = data.get("session_id", self.session_id)
            self.session_start_time = data.get("session_start_time", self.session_start_time)

            # Restore conversation history (limit to max_history_entries)
            conversations = data.get("conversations", [])
            if len(conversations) > self.max_history_entries:
                print(f"[session] Trimmed loaded history: {len(conversations)} → {self.max_history_entries} entries")
                self.conversation_history = conversations[-self.max_history_entries:]
            else:
                self.conversation_history = conversations

            # Restore stats
            self.stats = data.get("stats", self.stats)
            self.stats["loads"] += 1

            print(f"[session] Loaded session state (session_id={self.session_id}, {len(self.conversation_history)} messages)")

        except Exception as e:
            print(f"[session] ERROR: Failed to load session state: {e}")
            print("[session] Starting with fresh session")

    def get_session_info(self) -> Dict[str, Any]:
        """Get current session information (for health checks)."""
        context_size = sum(len(msg.get("content", "")) for msg in self.conversation_history)

        return {
            "session_id": self.session_id,
            "message_count": len(self.conversation_history),
            "context_size": context_size,
            "session_duration": time.time() - self.session_start_time,
            "stats": self.stats
        }

    def shutdown(self):
        """Shutdown session service gracefully."""
        print("[session] Shutting down Session Management service...")

        # Save final state
        if self.persist_enabled:
            self._save_session_state()

        # Emit shutdown signal
        if self.chem_pub:
            self.chem_pub.emit(
                "VOICE.SESSION.SHUTDOWN",
                ecosystem="voice",
                intensity=1.0,
                facts={
                    "session_id": self.session_id,
                    "message_count": len(self.conversation_history),
                    "stats": self.stats
                },
                incident_id=f"session-shutdown-{int(time.time())}"
            )

        self.running = False
        print("[session] Session Management service stopped")


def main():
    """Main entry point for Session Management service."""
    service = sessionService()

    # Signal handlers for graceful shutdown
    def handle_shutdown(signum, frame):
        print(f"\n[session] Received signal {signum}, shutting down...")
        service.shutdown()
        sys.exit(0)

    signal.signal(signal.SIGTERM, handle_shutdown)
    signal.signal(signal.SIGINT, handle_shutdown)

    # Start service
    service.start()

    # Keep alive
    try:
        while service.running:
            time.sleep(1.0)
    except KeyboardInterrupt:
        print("\n[session] Keyboard interrupt received")
        service.shutdown()


if __name__ == "__main__":
    main()
