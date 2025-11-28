"""
Storage system for synthesized tools in KLoROS.

Manages persistent storage and retrieval of dynamically created tools.
"""

import json
import os
import sqlite3
import hashlib
from datetime import datetime
from typing import Dict, List, Optional, Tuple
from pathlib import Path


class SynthesizedToolStorage:
    """Storage manager for synthesized tools."""

    def __init__(self, storage_dir: str = "/home/kloros/.kloros/synthesized_tools"):
        self.storage_dir = Path(storage_dir)
        self.storage_dir.mkdir(parents=True, exist_ok=True)

        self.db_path = self.storage_dir / "tools.db"
        self.code_dir = self.storage_dir / "code"
        self.code_dir.mkdir(exist_ok=True)

        self._initialize_database()

    def _initialize_database(self):
        """Initialize SQLite database for tool metadata."""

        with sqlite3.connect(self.db_path) as conn:
            conn.execute('''
                CREATE TABLE IF NOT EXISTS synthesized_tools (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    tool_name TEXT UNIQUE NOT NULL,
                    code_hash TEXT NOT NULL,
                    created_at TEXT NOT NULL,
                    last_used TEXT,
                    use_count INTEGER DEFAULT 0,
                    analysis_data TEXT,
                    validation_report TEXT,
                    status TEXT DEFAULT 'active',
                    performance_metrics TEXT
                )
            ''')

            conn.execute('''
                CREATE TABLE IF NOT EXISTS tool_usage_log (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    tool_name TEXT NOT NULL,
                    used_at TEXT NOT NULL,
                    execution_time_ms INTEGER,
                    success BOOLEAN,
                    error_message TEXT,
                    context TEXT
                )
            ''')

            # Create indexes separately to avoid "one statement at a time" error
            conn.execute('CREATE INDEX IF NOT EXISTS idx_tool_name ON synthesized_tools(tool_name)')
            conn.execute('CREATE INDEX IF NOT EXISTS idx_created_at ON synthesized_tools(created_at)')
            conn.execute('CREATE INDEX IF NOT EXISTS idx_status ON synthesized_tools(status)')
            conn.execute('CREATE INDEX IF NOT EXISTS idx_usage_tool ON tool_usage_log(tool_name)')
            conn.execute('CREATE INDEX IF NOT EXISTS idx_usage_time ON tool_usage_log(used_at)')

    def save_tool(self, tool_name: str, tool_code: str, analysis: Dict,
                  validation_report: Optional[Dict] = None) -> bool:
        """
        Save a synthesized tool with metadata.

        Args:
            tool_name: Name of the tool
            tool_code: Python code for the tool
            analysis: Analysis data from synthesis
            validation_report: Validation results

        Returns:
            True if saved successfully, False otherwise
        """
        try:
            # Generate code hash for integrity checking
            code_hash = hashlib.sha256(tool_code.encode()).hexdigest()

            # Save code to file
            code_file = self.code_dir / f"{tool_name}.py"
            with open(code_file, 'w') as f:
                f.write(tool_code)

            # Save metadata to database
            with sqlite3.connect(self.db_path) as conn:
                conn.execute('''
                    INSERT OR REPLACE INTO synthesized_tools
                    (tool_name, code_hash, created_at, analysis_data, validation_report)
                    VALUES (?, ?, ?, ?, ?)
                ''', (
                    tool_name,
                    code_hash,
                    datetime.now().isoformat(),
                    json.dumps(analysis),
                    json.dumps(validation_report) if validation_report else None
                ))

            return True

        except Exception as e:
            print(f"Error saving tool {tool_name}: {e}")
            return False

    def load_tool(self, tool_name: str) -> Optional[Tuple[str, Dict]]:
        """
        Load a synthesized tool by name.

        Args:
            tool_name: Name of the tool to load

        Returns:
            Tuple of (code, metadata) if found, None otherwise
        """
        try:
            # Get metadata from database
            with sqlite3.connect(self.db_path) as conn:
                cursor = conn.execute('''
                    SELECT code_hash, analysis_data, validation_report, status
                    FROM synthesized_tools
                    WHERE tool_name = ? AND status = 'active'
                ''', (tool_name,))

                row = cursor.fetchone()
                if not row:
                    return None

                code_hash, analysis_json, validation_json, status = row

            # Load code from file
            code_file = self.code_dir / f"{tool_name}.py"
            if not code_file.exists():
                return None

            with open(code_file, 'r') as f:
                tool_code = f.read()

            # Verify code integrity
            actual_hash = hashlib.sha256(tool_code.encode()).hexdigest()
            if actual_hash != code_hash:
                print(f"Warning: Code hash mismatch for tool {tool_name}")
                return None

            # Parse metadata
            metadata = {
                'analysis': json.loads(analysis_json) if analysis_json else {},
                'validation_report': json.loads(validation_json) if validation_json else {},
                'status': status
            }

            return tool_code, metadata

        except Exception as e:
            print(f"Error loading tool {tool_name}: {e}")
            return None

    def list_tools(self, status: str = 'active') -> List[Dict]:
        """
        List all synthesized tools with their metadata.

        Args:
            status: Filter by status ('active', 'disabled', 'all')

        Returns:
            List of tool metadata dictionaries
        """
        try:
            with sqlite3.connect(self.db_path) as conn:
                if status == 'all':
                    cursor = conn.execute('''
                        SELECT tool_name, created_at, last_used, use_count,
                               analysis_data, status
                        FROM synthesized_tools
                        ORDER BY created_at DESC
                    ''')
                else:
                    cursor = conn.execute('''
                        SELECT tool_name, created_at, last_used, use_count,
                               analysis_data, status
                        FROM synthesized_tools
                        WHERE status = ?
                        ORDER BY created_at DESC
                    ''', (status,))

                tools = []
                for row in cursor.fetchall():
                    tool_name, created_at, last_used, use_count, analysis_json, tool_status = row

                    tool_info = {
                        'name': tool_name,
                        'created_at': created_at,
                        'last_used': last_used,
                        'use_count': use_count,
                        'status': tool_status,
                        'analysis': json.loads(analysis_json) if analysis_json else {}
                    }
                    tools.append(tool_info)

                return tools

        except Exception as e:
            print(f"Error listing tools: {e}")
            return []

    def record_tool_usage(self, tool_name: str, execution_time_ms: int,
                         success: bool, error_message: str = None,
                         context: str = None):
        """
        Record tool usage for analytics.

        Args:
            tool_name: Name of the tool used
            execution_time_ms: Execution time in milliseconds
            success: Whether execution was successful
            error_message: Error message if failed
            context: Context in which tool was used
        """
        try:
            with sqlite3.connect(self.db_path) as conn:
                # Record usage log
                conn.execute('''
                    INSERT INTO tool_usage_log
                    (tool_name, used_at, execution_time_ms, success, error_message, context)
                    VALUES (?, ?, ?, ?, ?, ?)
                ''', (
                    tool_name,
                    datetime.now().isoformat(),
                    execution_time_ms,
                    success,
                    error_message,
                    context
                ))

                # Update tool statistics
                conn.execute('''
                    UPDATE synthesized_tools
                    SET last_used = ?, use_count = use_count + 1
                    WHERE tool_name = ?
                ''', (datetime.now().isoformat(), tool_name))

        except Exception as e:
            print(f"Error recording tool usage: {e}")

    def disable_tool(self, tool_name: str, reason: str = None) -> bool:
        """
        Disable a tool (mark as inactive).

        Args:
            tool_name: Name of the tool to disable
            reason: Reason for disabling

        Returns:
            True if disabled successfully, False otherwise
        """
        try:
            with sqlite3.connect(self.db_path) as conn:
                conn.execute('''
                    UPDATE synthesized_tools
                    SET status = 'disabled'
                    WHERE tool_name = ?
                ''', (tool_name,))

                # Log the disable action
                if reason:
                    self.record_tool_usage(tool_name, 0, False, f"Disabled: {reason}")

            return True

        except Exception as e:
            print(f"Error disabling tool {tool_name}: {e}")
            return False

    def enable_tool(self, tool_name: str) -> bool:
        """
        Re-enable a disabled tool.

        Args:
            tool_name: Name of the tool to enable

        Returns:
            True if enabled successfully, False otherwise
        """
        try:
            with sqlite3.connect(self.db_path) as conn:
                conn.execute('''
                    UPDATE synthesized_tools
                    SET status = 'active'
                    WHERE tool_name = ?
                ''', (tool_name,))

            return True

        except Exception as e:
            print(f"Error enabling tool {tool_name}: {e}")
            return False

    def delete_tool(self, tool_name: str) -> bool:
        """
        Permanently delete a tool.

        Args:
            tool_name: Name of the tool to delete

        Returns:
            True if deleted successfully, False otherwise
        """
        try:
            # Delete code file
            code_file = self.code_dir / f"{tool_name}.py"
            if code_file.exists():
                code_file.unlink()

            # Delete from database
            with sqlite3.connect(self.db_path) as conn:
                conn.execute('''
                    DELETE FROM synthesized_tools WHERE tool_name = ?
                ''', (tool_name,))

                conn.execute('''
                    DELETE FROM tool_usage_log WHERE tool_name = ?
                ''', (tool_name,))

            return True

        except Exception as e:
            print(f"Error deleting tool {tool_name}: {e}")
            return False

    def get_tool_analytics(self, tool_name: str = None) -> Dict:
        """
        Get analytics data for tools.

        Args:
            tool_name: Specific tool name, or None for all tools

        Returns:
            Analytics data dictionary
        """
        try:
            with sqlite3.connect(self.db_path) as conn:
                if tool_name:
                    # Analytics for specific tool
                    cursor = conn.execute('''
                        SELECT COUNT(*) as total_uses,
                               AVG(execution_time_ms) as avg_execution_time,
                               COUNT(CASE WHEN success = 1 THEN 1 END) as successful_uses,
                               COUNT(CASE WHEN success = 0 THEN 1 END) as failed_uses
                        FROM tool_usage_log
                        WHERE tool_name = ?
                    ''', (tool_name,))

                    row = cursor.fetchone()
                    return {
                        'tool_name': tool_name,
                        'total_uses': row[0] or 0,
                        'avg_execution_time_ms': row[1] or 0,
                        'successful_uses': row[2] or 0,
                        'failed_uses': row[3] or 0,
                        'success_rate': (row[2] or 0) / max(row[0] or 1, 1) * 100
                    }
                else:
                    # Overall analytics
                    cursor = conn.execute('''
                        SELECT COUNT(DISTINCT tool_name) as unique_tools,
                               COUNT(*) as total_uses,
                               AVG(execution_time_ms) as avg_execution_time,
                               COUNT(CASE WHEN success = 1 THEN 1 END) as successful_uses
                        FROM tool_usage_log
                    ''')

                    row = cursor.fetchone()

                    # Get tool count by status
                    cursor = conn.execute('''
                        SELECT status, COUNT(*)
                        FROM synthesized_tools
                        GROUP BY status
                    ''')

                    status_counts = dict(cursor.fetchall())

                    return {
                        'unique_tools': row[0] or 0,
                        'total_uses': row[1] or 0,
                        'avg_execution_time_ms': row[2] or 0,
                        'successful_uses': row[3] or 0,
                        'success_rate': (row[3] or 0) / max(row[1] or 1, 1) * 100,
                        'tools_by_status': status_counts
                    }

        except Exception as e:
            print(f"Error getting analytics: {e}")
            return {}

    def get_stats(self) -> Dict:
        """Get storage system statistics."""

        try:
            stats = {
                'storage_directory': str(self.storage_dir),
                'database_size_bytes': self.db_path.stat().st_size if self.db_path.exists() else 0,
                'code_files_count': len(list(self.code_dir.glob('*.py'))),
                'total_storage_bytes': sum(f.stat().st_size for f in self.storage_dir.rglob('*') if f.is_file())
            }

            # Add tool counts
            with sqlite3.connect(self.db_path) as conn:
                cursor = conn.execute('SELECT COUNT(*) FROM synthesized_tools')
                stats['total_tools'] = cursor.fetchone()[0]

                cursor = conn.execute('SELECT COUNT(*) FROM synthesized_tools WHERE status = "active"')
                stats['active_tools'] = cursor.fetchone()[0]

                cursor = conn.execute('SELECT COUNT(*) FROM tool_usage_log')
                stats['total_usage_records'] = cursor.fetchone()[0]

            return stats

        except Exception as e:
            return {'error': str(e)}

    def cleanup_old_tools(self, days_unused: int = 30) -> int:
        """
        Clean up tools that haven't been used in specified days.

        Args:
            days_unused: Number of days without usage before cleanup

        Returns:
            Number of tools cleaned up
        """
        try:
            cutoff_date = datetime.now().replace(microsecond=0) - \
                         datetime.timedelta(days=days_unused)

            with sqlite3.connect(self.db_path) as conn:
                # Find unused tools
                cursor = conn.execute('''
                    SELECT tool_name FROM synthesized_tools
                    WHERE (last_used IS NULL OR last_used < ?)
                    AND status = 'active'
                ''', (cutoff_date.isoformat(),))

                unused_tools = [row[0] for row in cursor.fetchall()]

                # Disable unused tools instead of deleting
                for tool_name in unused_tools:
                    self.disable_tool(tool_name, f"Unused for {days_unused} days")

                return len(unused_tools)

        except Exception as e:
            print(f"Error during cleanup: {e}")
            return 0