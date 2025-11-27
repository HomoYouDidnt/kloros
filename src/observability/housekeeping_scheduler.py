"""
Housekeeping scheduler for KLoROS autonomous maintenance operations.

Provides automated scheduling of daily maintenance tasks including
memory system cleanup, Python cache management, and backup file rotation.
"""

import sys
import time
import os
from datetime import datetime, timedelta
from typing import Dict, Any, Optional
from pathlib import Path

# Use kloros home explicitly (not current user's home)
sys.path.insert(0, '/home/kloros')

class HousekeepingScheduler:
    """Manages automated housekeeping and maintenance scheduling."""

    def __init__(self, kloros_instance):
        """
        Initialize the housekeeping scheduler.

        Args:
            kloros_instance: Reference to main KLoROS instance
        """
        self.kloros = kloros_instance

        # Configuration from environment
        self.housekeeping_enabled = int(os.getenv("KLR_ENABLE_HOUSEKEEPING", "1"))
        self.daily_maintenance_hour = int(os.getenv("KLR_MAINTENANCE_HOUR", "3"))  # 3 AM default
        self.maintenance_interval_hours = float(os.getenv("KLR_MAINTENANCE_INTERVAL_HOURS", "24.0"))

        # State tracking
        self.last_maintenance_time = self._get_last_maintenance_time()
        self.maintenance_running = False

        # Housekeeping manager (lazy initialization)
        self._housekeeper = None

        if self.housekeeping_enabled:
            print(f"[housekeeping] Scheduler initialized - interval: {self.maintenance_interval_hours}h")
        else:
            print("[housekeeping] Housekeeping disabled (KLR_ENABLE_HOUSEKEEPING=0)")

    def _get_last_maintenance_time(self) -> float:
        """Get the timestamp of the last maintenance operation."""
        try:
            # Check if we can get this from memory system
            if hasattr(self.kloros, 'memory_system') and self.kloros.memory_system:
                from src.memory.housekeeping import MemoryHousekeeper
                housekeeper = MemoryHousekeeper()

                # Check for recent housekeeping events
                try:
                    import sqlite3
                    conn = sqlite3.connect("/home/kloros/.kloros/memory.db")
                    cursor = conn.cursor()

                    cursor.execute("""
                        SELECT MAX(timestamp)
                        FROM events
                        WHERE event_type = 'MEMORY_HOUSEKEEPING'
                        AND content LIKE '%Daily maintenance completed%'
                    """)

                    result = cursor.fetchone()
                    conn.close()

                    if result and result[0]:
                        return float(result[0])

                except Exception:
                    pass

            # Fallback: assume last maintenance was 24 hours ago
            return time.time() - (24 * 3600)

        except Exception as e:
            print(f"[housekeeping] Could not determine last maintenance time: {e}")
            return time.time() - (24 * 3600)

    @property
    def housekeeper(self):
        """Lazy initialization of housekeeping manager."""
        if self._housekeeper is None:
            try:
                from src.memory.housekeeping import MemoryHousekeeper
                self._housekeeper = MemoryHousekeeper()
                print("[housekeeping] Memory housekeeper initialized")
            except Exception as e:
                print(f"[housekeeping] Failed to initialize housekeeper: {e}")
                return None
        return self._housekeeper

    def should_run_maintenance(self) -> bool:
        """
        Check if it's time to run scheduled maintenance.

        Returns:
            True if maintenance should be executed
        """
        if not self.housekeeping_enabled:
            return False

        if self.maintenance_running:
            return False

        current_time = time.time()
        time_since_last = current_time - self.last_maintenance_time

        # Check if enough time has passed
        if time_since_last >= (self.maintenance_interval_hours * 3600):
            return True

        # Also check if it's the preferred daily time (3 AM default)
        current_hour = datetime.now().hour
        if (current_hour == self.daily_maintenance_hour and
            time_since_last >= (12 * 3600)):  # At least 12 hours since last
            return True

        return False

    def run_scheduled_maintenance(self) -> Optional[Dict[str, Any]]:
        """
        Execute scheduled maintenance operations.

        Returns:
            Dictionary with maintenance results, or None if skipped
        """
        if not self.should_run_maintenance():
            return None

        if not self.housekeeper:
            print("[housekeeping] Housekeeper not available, skipping maintenance")
            return None

        print("[housekeeping] 🧹 Starting scheduled maintenance...")
        self.maintenance_running = True

        try:
            # Trim conversation history if KLoROS instance available
            if hasattr(self.kloros, '_trim_conversation_history'):
                before_count = len(self.kloros.conversation_history)
                self.kloros._trim_conversation_history(max_entries=100)
                after_count = len(self.kloros.conversation_history)
                if before_count > after_count:
                    print(f"[housekeeping] Trimmed conversation history: {before_count} → {after_count}")

            # Run daily maintenance
            start_time = time.time()
            results = self.housekeeper.run_daily_maintenance()

            # Update last maintenance time
            self.last_maintenance_time = start_time

            # Log results
            duration = time.time() - start_time
            tasks_completed = len(results.get('tasks_completed', []))
            errors = len(results.get('errors', []))

            print(f"[housekeeping] ✅ Maintenance completed in {duration:.2f}s")
            print(f"[housekeeping] Tasks: {tasks_completed}, Errors: {errors}")

            # Log specific cleanup results
            if 'python_cache_cleanup' in results:
                cache_result = results['python_cache_cleanup']
                print(f"[housekeeping] Python cache: {cache_result['pyc_files_deleted']} .pyc, {cache_result['pycache_dirs_deleted']} dirs")

            if 'backup_cleanup' in results:
                backup_result = results['backup_cleanup']
                print(f"[housekeeping] Backups: {backup_result['files_deleted']} deleted, {backup_result['files_retained']} retained")

            if 'tts_cleanup' in results:
                tts_result = results['tts_cleanup']
                print(f"[housekeeping] TTS: {tts_result['files_deleted']} files, {tts_result['bytes_freed']:,} bytes freed")

            return results

        except Exception as e:
            print(f"[housekeeping] ❌ Maintenance failed: {e}")
            return {
                "error": str(e),
                "timestamp": time.time(),
                "tasks_completed": [],
                "errors": [str(e)]
            }
        finally:
            self.maintenance_running = False

    def get_maintenance_status(self) -> Dict[str, Any]:
        """
        Get current maintenance scheduling status.

        Returns:
            Dictionary with status information
        """
        current_time = time.time()
        time_since_last = current_time - self.last_maintenance_time
        time_until_next = (self.maintenance_interval_hours * 3600) - time_since_last

        return {
            "enabled": self.housekeeping_enabled,
            "last_maintenance": self.last_maintenance_time,
            "last_maintenance_ago_hours": time_since_last / 3600,
            "next_maintenance_in_hours": max(0, time_until_next / 3600),
            "maintenance_running": self.maintenance_running,
            "preferred_hour": self.daily_maintenance_hour,
            "interval_hours": self.maintenance_interval_hours,
            "should_run_now": self.should_run_maintenance()
        }

    def force_maintenance(self) -> Dict[str, Any]:
        """
        Force immediate maintenance execution (bypass scheduling).

        Returns:
            Dictionary with maintenance results
        """
        if self.maintenance_running:
            return {"error": "Maintenance already running"}

        print("[housekeeping] 🔧 Forcing immediate maintenance...")

        # Temporarily override last maintenance time to force execution
        original_time = self.last_maintenance_time
        self.last_maintenance_time = 0

        try:
            results = self.run_scheduled_maintenance()
            if results:
                return results
            else:
                return {"error": "Maintenance not executed"}
        finally:
            # Restore original time if maintenance failed
            if not results:
                self.last_maintenance_time = original_time