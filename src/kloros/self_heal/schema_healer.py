#!/usr/bin/env python3
"""
Schema Self-Healer - Autonomous Schema Evolution

Detects when KLoROS tries to use enum values that don't exist yet,
and autonomously adds them to the schema definitions.

Watches for:
- "is not a valid ActionClass" errors
- "is not a valid QuestionStatus" errors
- Other enum validation failures

Autonomously fixes by:
- Adding missing enum values
- Preserving existing values and documentation
- Restarting affected services

This is Level 3 autonomy - actual code modification for schema evolution.

Governance:
- Tool-Integrity: Safe enum additions only, no arbitrary code execution
- D-REAM-Allowed-Stack: File editing, enum parsing
- Autonomy Level 3: Self-modification with safety checks
"""

import re
import logging
import subprocess
from pathlib import Path
from typing import List, Dict, Optional, Tuple
from dataclasses import dataclass
from datetime import datetime

logger = logging.getLogger(__name__)


@dataclass
class MissingEnumValue:
    """A missing enum value that needs to be added."""
    enum_name: str  # e.g., "ActionClass"
    missing_value: str  # e.g., "explore"
    file_path: Path
    line_number: Optional[int] = None
    detected_at: str = None

    def __post_init__(self):
        if self.detected_at is None:
            self.detected_at = datetime.now().isoformat()


class SchemaHealer:
    """Autonomously heals schema mismatches by adding missing enum values."""

    def __init__(self):
        self.src_root = Path("/home/kloros/src")
        self.healed_schemas: List[Dict] = []

    def detect_missing_enums_from_logs(self, log_lines: List[str]) -> List[MissingEnumValue]:
        """
        Parse log lines for enum validation errors.

        Args:
            log_lines: List of log lines to parse

        Returns:
            List of MissingEnumValue objects
        """
        missing = []

        # Pattern: "'explore' is not a valid ActionClass"
        pattern = r"'(\w+)'\s+is not a valid\s+(\w+)"

        for line in log_lines:
            match = re.search(pattern, line)
            if match:
                value, enum_name = match.groups()
                logger.info(f"[schema_healer] Detected missing enum: {enum_name}.{value}")

                # Find the file containing this enum
                file_path = self._find_enum_definition(enum_name)
                if file_path:
                    missing.append(MissingEnumValue(
                        enum_name=enum_name,
                        missing_value=value,
                        file_path=file_path
                    ))
                else:
                    logger.warning(f"[schema_healer] Could not find definition for enum {enum_name}")

        return missing

    def _find_enum_definition(self, enum_name: str) -> Optional[Path]:
        """
        Find the file containing an enum definition.

        Args:
            enum_name: Name of the enum class (e.g., "ActionClass")

        Returns:
            Path to file containing the enum, or None
        """
        # Common locations for enums
        candidates = [
            self.src_root / "registry" / "curiosity_core.py",
            self.src_root / "kloros" / "orchestration" / "curiosity_processor.py",
            self.src_root / "registry" / "types.py",
        ]

        for path in candidates:
            if not path.exists():
                continue

            try:
                content = path.read_text()
                # Look for "class EnumName(Enum):"
                if re.search(rf"class {enum_name}\(Enum\):", content):
                    logger.info(f"[schema_healer] Found {enum_name} in {path}")
                    return path
            except Exception as e:
                logger.debug(f"[schema_healer] Error reading {path}: {e}")

        return None

    def heal_enum(self, missing: MissingEnumValue) -> bool:
        """
        Add missing enum value to the enum definition.

        Args:
            missing: MissingEnumValue to add

        Returns:
            True if successful, False otherwise
        """
        try:
            content = missing.file_path.read_text()
            lines = content.splitlines()

            # Find the enum class
            enum_start = None
            enum_end = None
            indent = None

            for i, line in enumerate(lines):
                if re.search(rf"class {missing.enum_name}\(Enum\):", line):
                    enum_start = i
                    logger.info(f"[schema_healer] Found enum {missing.enum_name} at line {i+1}")
                    continue

                if enum_start is not None and not line.strip().startswith('"') and line.strip():
                    # First non-empty line in enum to determine indent
                    if indent is None:
                        indent = len(line) - len(line.lstrip())

                    # Check if we've reached the end of the enum
                    current_indent = len(line) - len(line.lstrip())
                    if current_indent < indent and line.strip():
                        enum_end = i
                        break

            if enum_start is None:
                logger.error(f"[schema_healer] Could not find enum {missing.enum_name}")
                return False

            # Find the last enum value to insert after
            last_value_line = enum_start
            for i in range(enum_start + 1, enum_end if enum_end else len(lines)):
                line = lines[i]
                # Look for enum values (e.g., "    VALUE = \"value\"")
                if re.match(r'\s+[A-Z_]+\s*=', line):
                    last_value_line = i

            # Generate the new enum value
            # Convert "explore" -> "EXPLORE"
            enum_constant = missing.missing_value.upper()
            new_line = f"{' ' * indent}{enum_constant} = \"{missing.missing_value}\""

            # Add comment if it's one of our new action types
            if missing.enum_name == "ActionClass":
                if missing.missing_value == "explore":
                    new_line += "  # Open-ended exploration of new possibilities"
                elif missing.missing_value == "experiment":
                    new_line += "  # Run controlled experiments to test hypotheses"

            # Check if it already exists
            if any(f"{enum_constant} =" in line for line in lines):
                logger.info(f"[schema_healer] {missing.enum_name}.{enum_constant} already exists")
                return True

            # Insert the new value after the last enum value
            lines.insert(last_value_line + 1, new_line)

            # Write back
            new_content = "\n".join(lines)
            missing.file_path.write_text(new_content)

            logger.info(f"[schema_healer] ✓ Added {missing.enum_name}.{enum_constant} to {missing.file_path}")

            self.healed_schemas.append({
                "enum_name": missing.enum_name,
                "value": missing.missing_value,
                "file": str(missing.file_path),
                "healed_at": datetime.now().isoformat()
            })

            return True

        except Exception as e:
            logger.error(f"[schema_healer] Failed to heal {missing.enum_name}: {e}")
            return False

    def restart_affected_services(self, enum_name: str) -> bool:
        """
        Restart services affected by schema changes.

        Args:
            enum_name: Name of the enum that was modified

        Returns:
            True if services restarted successfully
        """
        # Map enums to affected services
        service_map = {
            "ActionClass": [
                "kloros-curiosity-core-consumer.service",
                "kloros-curiosity-processor.service"
            ],
            "QuestionStatus": [
                "kloros-curiosity-core-consumer.service",
                "kloros-curiosity-processor.service"
            ]
        }

        services = service_map.get(enum_name, [])
        if not services:
            logger.info(f"[schema_healer] No services to restart for {enum_name}")
            return True

        success = True
        for service in services:
            try:
                logger.info(f"[schema_healer] Restarting {service}...")
                result = subprocess.run(
                    ["systemctl", "restart", service],
                    capture_output=True,
                    timeout=10
                )
                if result.returncode == 0:
                    logger.info(f"[schema_healer] ✓ Restarted {service}")
                else:
                    logger.error(f"[schema_healer] Failed to restart {service}: {result.stderr.decode()}")
                    success = False
            except Exception as e:
                logger.error(f"[schema_healer] Error restarting {service}: {e}")
                success = False

        return success

    def heal_from_journal(self, service_name: str, since: str = "5 minutes ago") -> int:
        """
        Check service journal for enum errors and heal them.

        Args:
            service_name: Systemd service name to check
            since: Time range to check (e.g., "5 minutes ago")

        Returns:
            Number of schemas healed
        """
        try:
            # Read journal logs
            result = subprocess.run(
                ["journalctl", "-u", service_name, "--since", since, "--no-pager"],
                capture_output=True,
                text=True,
                timeout=10
            )

            if result.returncode != 0:
                logger.warning(f"[schema_healer] Failed to read journal for {service_name}")
                return 0

            log_lines = result.stdout.splitlines()

            # Detect missing enums
            missing_enums = self.detect_missing_enums_from_logs(log_lines)

            if not missing_enums:
                logger.debug(f"[schema_healer] No missing enums detected in {service_name}")
                return 0

            # Heal each missing enum
            healed_count = 0
            for missing in missing_enums:
                logger.info(f"[schema_healer] Healing {missing.enum_name}.{missing.missing_value}...")
                if self.heal_enum(missing):
                    healed_count += 1

            # Restart affected services
            if healed_count > 0:
                for missing in missing_enums:
                    self.restart_affected_services(missing.enum_name)

            return healed_count

        except Exception as e:
            logger.error(f"[schema_healer] Error healing from journal: {e}")
            return 0


def heal_schemas_from_service(service_name: str = "kloros-curiosity-processor.service") -> int:
    """
    Main entry point: check a service for enum errors and heal them.

    Args:
        service_name: Service to check for errors

    Returns:
        Number of schemas healed
    """
    healer = SchemaHealer()
    return healer.heal_from_journal(service_name)


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)

    # Test: heal schemas from curiosity processor
    healed = heal_schemas_from_service("kloros-curiosity-processor.service")
    print(f"Healed {healed} schema(s)")
