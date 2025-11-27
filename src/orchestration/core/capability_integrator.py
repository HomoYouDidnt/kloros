#!/usr/bin/env python3
"""
Capability Integrator - Processes investigation results and updates capability registry.

Purpose:
    Bridge the gap between curiosity-driven module discovery and capability registry integration.
    Analyzes investigation probe results and automatically registers discovered modules.

Workflow:
    1. Read curiosity_investigations.jsonl for unprocessed investigations
    2. Analyze probe results and module structure
    3. Generate capability entry with appropriate metadata
    4. Update capabilities.yaml
    5. Mark investigation as integrated

This completes the discovery-to-integration loop:
    Discovery → Investigation → 🔗 Integration → Capability Awareness
"""

import json
import logging
import subprocess
import yaml
import shutil
from pathlib import Path
from datetime import datetime
from typing import Dict, Any, List, Optional, Tuple

try:
    from src.cognition.mind.cognition.semantic_analysis import ArchitecturalReasoner, ArchitecturalPattern
    SEMANTIC_ANALYSIS_AVAILABLE = True
except ImportError:
    SEMANTIC_ANALYSIS_AVAILABLE = False

logger = logging.getLogger(__name__)

INVESTIGATIONS_LOG = Path("/home/kloros/.kloros/curiosity_investigations.jsonl")
INTEGRATED_LOG = Path("/home/kloros/.kloros/integrated_capabilities.jsonl")
CAPABILITIES_YAML = Path("/home/kloros/src/registry/capabilities.yaml")
LAST_PROCESSED_TIMESTAMP = Path("/home/kloros/.kloros/capability_integrator_last_processed.txt")


class CapabilityIntegrator:
    """Processes investigation results and updates capability registry."""

    def __init__(self):
        """Initialize integrator."""
        self.integrated_ids = self._load_integrated_ids()
        self.last_processed_timestamp = self._load_last_processed_timestamp()

        if SEMANTIC_ANALYSIS_AVAILABLE:
            self.semantic_reasoner = ArchitecturalReasoner(base_path="/home/kloros/src")
            logger.info("[integrator] Semantic analysis enabled for phantom detection")
        else:
            self.semantic_reasoner = None
            logger.warning("[integrator] Semantic analysis not available, using filesystem validation only")

    def _load_integrated_ids(self) -> set:
        """Load set of already integrated investigation IDs."""
        if not INTEGRATED_LOG.exists():
            return set()

        integrated = set()
        try:
            with open(INTEGRATED_LOG, 'r') as f:
                for line in f:
                    if not line.strip():
                        continue
                    entry = json.loads(line)
                    if 'capability' in entry:
                        integrated.add(entry['capability'])
        except Exception as e:
            logger.warning(f"Error loading integrated IDs: {e}")

        return integrated

    def _load_last_processed_timestamp(self) -> str:
        """Load the timestamp of the last processed investigation."""
        if not LAST_PROCESSED_TIMESTAMP.exists():
            return ""

        try:
            with open(LAST_PROCESSED_TIMESTAMP, 'r') as f:
                return f.read().strip()
        except Exception as e:
            logger.warning(f"Error loading last processed timestamp: {e}")
            return ""

    def _save_last_processed_timestamp(self, timestamp: str):
        """Save the timestamp of the last processed investigation."""
        try:
            LAST_PROCESSED_TIMESTAMP.parent.mkdir(parents=True, exist_ok=True)
            with open(LAST_PROCESSED_TIMESTAMP, 'w') as f:
                f.write(timestamp)
        except Exception as e:
            logger.error(f"Failed to save last processed timestamp: {e}")

    def _mark_integrated(self, capability_key: str, investigation: Dict[str, Any]):
        """Mark an investigation as integrated."""
        INTEGRATED_LOG.parent.mkdir(parents=True, exist_ok=True)

        entry = {
            "capability": capability_key,
            "integrated_at": datetime.now().isoformat(),
            "module_path": self._extract_module_path(investigation),
            "question": investigation.get("question", ""),
        }

        try:
            with open(INTEGRATED_LOG, 'a') as f:
                f.write(json.dumps(entry) + '\n')
            logger.info(f"[integrator] Marked {capability_key} as integrated")
        except Exception as e:
            logger.error(f"[integrator] Failed to mark integrated: {e}")

    def _extract_module_path(self, investigation: Dict[str, Any]) -> Optional[str]:
        """Extract module path from investigation evidence."""
        evidence = investigation.get("evidence", [])
        for ev in evidence:
            if ev.startswith("path:"):
                path = ev.split(":", 1)[1]
                # Convert /home/kloros/src/audio to src.audio
                if "/src/" in path:
                    module_path = path.split("/src/", 1)[1].replace("/", ".")
                    return module_path
        return None

    def _extract_module_info(self, investigation: Dict[str, Any]) -> Dict[str, Any]:
        """Extract module info from investigation evidence."""
        evidence = investigation.get("evidence", [])
        info = {
            "path": None,
            "has_init": False,
            "py_files": 0,
            "has_docs": False,
            "age_days": 0
        }

        for ev in evidence:
            if ":" in ev:
                key, value = ev.split(":", 1)
                if key == "path":
                    info["path"] = value
                elif key == "has_init":
                    info["has_init"] = value.lower() == "true"
                elif key == "py_files":
                    info["py_files"] = int(value)
                elif key == "has_docs":
                    info["has_docs"] = value.lower() == "true"
                elif key == "age_days":
                    info["age_days"] = int(value)

        return info

    def _infer_capability_description(
        self,
        module_name: str,
        module_info: Dict[str, Any],
        probe_results: List[Dict[str, Any]]
    ) -> str:
        """Infer capability description from module name and probe results."""
        # Common module name patterns
        descriptions = {
            "audio": "Audio processing and device management",
            "tts": "Text-to-speech synthesis",
            "stt": "Speech-to-text recognition",
            "memory": "Memory and storage systems",
            "reasoning": "Reasoning and inference backends",
            "tool_synthesis": "Dynamic tool generation and synthesis",
            "orchestration": "Autonomous workflow orchestration",
            "dream": "Evolutionary optimization system",
            "brainmods": "Advanced reasoning modules",
            "agentflow": "Agent workflow management",
            "browser_agent": "Browser automation",
            "dev_agent": "Development tools",
            "scholar": "Research and citation tools",
            "xai": "Explainable AI and decision tracking",
            "selfcoder": "Self-modification capabilities",
            "registry": "Capability registry and introspection"
        }

        # Try exact match first
        if module_name in descriptions:
            return descriptions[module_name]

        # Try partial matches
        for key, desc in descriptions.items():
            if key in module_name.lower():
                return desc

        # Generic description based on file count
        py_count = module_info.get("py_files", 0)
        if py_count > 10:
            return f"Complex module with {py_count} Python files"
        elif py_count > 5:
            return f"Module with {py_count} Python files"
        else:
            return f"Module component ({py_count} files)"

    def _validate_discovery_against_filesystem(self, module_path: str) -> Tuple[bool, str]:
        """
        Verify module directory exists with Python files (proof of real module).

        Prevents phantom modules from being added to capability registry by requiring
        evidence that the module directory actually exists with code in it.

        Args:
            module_path: Filesystem path to module (e.g., "/home/kloros/src/inference")

        Returns:
            (is_valid: bool, reason: str)
            - (True, "filesystem_verified_N_files") if directory exists with .py files
            - (False, "directory_not_found_phantom") if directory doesn't exist
            - (False, "no_python_files_phantom") if directory exists but has no .py files
        """
        try:
            from pathlib import Path

            module_dir = Path(module_path)

            # Check if directory exists
            if not module_dir.exists():
                logger.warning(
                    f"[integrator] ✗ Filesystem validation failed for {module_path}: "
                    f"Directory does not exist (phantom module)"
                )
                return False, "directory_not_found_phantom"

            if not module_dir.is_dir():
                logger.warning(
                    f"[integrator] ✗ Filesystem validation failed for {module_path}: "
                    f"Path exists but is not a directory"
                )
                return False, "not_a_directory"

            # Check for Python files in the directory
            py_files = list(module_dir.glob("*.py"))
            if not py_files:
                logger.warning(
                    f"[integrator] ✗ Filesystem validation failed for {module_path}: "
                    f"Directory exists but contains no .py files (phantom module)"
                )
                return False, "no_python_files_phantom"

            logger.info(
                f"[integrator] ✓ Filesystem validation passed for {module_path}: "
                f"Found {len(py_files)} Python files"
            )
            return True, f"filesystem_verified_{len(py_files)}_files"

        except Exception as e:
            logger.error(f"[integrator] Filesystem validation error for {module_path}: {e}")
            return False, f"filesystem_check_failed_{e.__class__.__name__}"

    def _validate_semantic_pattern(self, capability_key: str, module_info: Dict[str, Any]) -> Tuple[bool, str]:
        """
        Validate module using semantic analysis to detect phantoms and distributed patterns.

        Returns:
            (is_valid: bool, reason: str)
            - (True, "semantic_validated") if module represents real gap
            - (False, "phantom_distributed_pattern") if functionality is distributed
            - (False, "phantom_no_evidence") if only mentioned in comments/strings
        """
        if not self.semantic_reasoner:
            return True, "semantic_analysis_unavailable"

        module_name = capability_key.replace("module.", "")

        try:
            analysis = self.semantic_reasoner.analyze_gap_hypothesis(
                term=module_name,
                max_files=50
            )

            logger.info(
                f"[integrator] Semantic analysis for {capability_key}: "
                f"pattern={analysis.pattern.value}, "
                f"is_real_gap={analysis.is_real_gap}, "
                f"confidence={analysis.confidence}"
            )

            if analysis.is_real_gap:
                logger.info(
                    f"[integrator] ✓ Semantic validation passed for {capability_key}: "
                    f"{analysis.explanation}"
                )
                return True, "semantic_validated_real_gap"

            if analysis.pattern == ArchitecturalPattern.DISTRIBUTED_PATTERN:
                logger.warning(
                    f"[integrator] ✗ Semantic validation failed for {capability_key}: "
                    f"{analysis.explanation}. "
                    f"Rejecting phantom - functionality is intentionally distributed."
                )
                return False, f"phantom_distributed_pattern_{len(analysis.implementing_files)}_files"

            if analysis.pattern == ArchitecturalPattern.PHANTOM:
                logger.warning(
                    f"[integrator] ✗ Semantic validation failed for {capability_key}: "
                    f"{analysis.explanation}. "
                    f"Rejecting phantom - only mentioned in comments/strings, not actual dependency."
                )
                return False, "phantom_no_evidence"

            if analysis.pattern == ArchitecturalPattern.UNIFIED_MODULE:
                logger.info(
                    f"[integrator] ✓ Semantic validation passed for {capability_key}: "
                    f"Unified implementation found"
                )
                return True, "semantic_validated_unified"

            logger.warning(
                f"[integrator] ✗ Semantic validation uncertain for {capability_key}: "
                f"{analysis.explanation}. "
                f"Rejecting out of caution (confidence={analysis.confidence})."
            )
            return False, f"phantom_uncertain_confidence_{int(analysis.confidence*100)}"

        except Exception as e:
            logger.error(f"[integrator] Semantic validation error for {capability_key}: {e}")
            return True, f"semantic_check_failed_{e.__class__.__name__}"

    def _should_integrate(self, investigation: Dict[str, Any]) -> Tuple[bool, str]:
        """
        Determine if a module should be integrated based on investigation results.

        Returns:
            Tuple of (should_integrate: bool, reason: str)
        """
        capability_key = investigation.get("capability", "")

        # Skip if already integrated
        if capability_key in self.integrated_ids:
            return False, "already_integrated"

        # Must be an undiscovered module question
        hypothesis = investigation.get("hypothesis", "")
        if not hypothesis.startswith("UNDISCOVERED_MODULE_"):
            return False, "not_undiscovered_module"

        # Must have successful probe results or valid module structure
        probe_results = investigation.get("probe_results", [])
        module_info = self._extract_module_info(investigation)

        # NOTE: We no longer reject modules without __init__.py
        # The integrator now auto-creates __init__.py files during integration

        # Must have at least one Python file
        if module_info.get("py_files", 0) < 1:
            return False, "insufficient_files"

        # Must have a valid path
        if not module_info.get("path"):
            return False, "missing_path"

        # CRITICAL: Validate against filesystem to prevent phantom modules
        # Modules must actually exist as directories with Python files
        module_path = module_info.get("path")
        fs_valid, fs_reason = self._validate_discovery_against_filesystem(module_path)
        if not fs_valid:
            logger.warning(
                f"[integrator] Rejecting {capability_key}: {fs_reason}. "
                f"Module directory does not exist or has no code (phantom discovery)."
            )
            return False, fs_reason

        # SEMANTIC VALIDATION: Analyze architectural patterns to detect phantoms
        # Even if filesystem checks pass, module might be phantom if:
        # - Functionality is intentionally distributed across existing modules
        # - Only mentioned in comments/strings, not actual dependency
        semantic_valid, semantic_reason = self._validate_semantic_pattern(capability_key, module_info)
        if not semantic_valid:
            logger.warning(
                f"[integrator] Rejecting {capability_key}: {semantic_reason}. "
                f"Semantic analysis indicates phantom module."
            )
            return False, semantic_reason

        return True, "integration_criteria_met"

    def _ensure_module_init(
        self,
        module_path: str,
        module_name: str,
        module_info: Dict[str, Any]
    ) -> Tuple[bool, str]:
        """
        Ensure module has __init__.py file for proper Python module structure.
        Creates __init__.py if missing to enable capability integration.

        Args:
            module_path: Module dotted path (e.g., "src.registry")
            module_name: Simple module name (e.g., "registry")
            module_info: Module metadata from investigation

        Returns:
            Tuple of (success: bool, message: str)
        """
        fs_path = module_info.get("path")
        if not fs_path:
            return False, "no_filesystem_path"

        init_file = Path(fs_path) / "__init__.py"

        if init_file.exists():
            return True, "already_exists"

        description = self._infer_capability_description(module_name, module_info, [])

        docstring = f'''"""
{module_name.replace("_", " ").title()} Module - {description}

Auto-generated module initialization file.
Created by KLoROS capability integrator to enable module discovery and integration.
"""

__all__ = []
'''

        try:
            init_file.write_text(docstring)
            logger.info(f"[integrator] Created __init__.py for {module_name} at {init_file}")
            return True, "created"
        except Exception as e:
            logger.error(f"[integrator] Failed to create __init__.py for {module_name}: {e}")
            return False, f"error: {e}"

    def _generate_capability_entry(
        self,
        module_name: str,
        module_path: str,
        module_info: Dict[str, Any],
        probe_results: List[Dict[str, Any]]
    ) -> Dict[str, Any]:
        """Generate capability entry for capabilities.yaml."""
        description = self._infer_capability_description(
            module_name, module_info, probe_results
        )

        entry = {
            "module": module_path,
            "enabled": True,  # Auto-discovered modules start enabled
            "description": description,
            "auto_discovered": True,
            "discovered_at": datetime.now().isoformat(),
            "py_files": module_info.get("py_files", 0)
        }

        return entry

    def _update_capabilities_yaml(
        self,
        module_name: str,
        capability_entry: Dict[str, Any]
    ) -> Tuple[bool, str]:
        """
        Update capabilities.yaml with new capability.

        Returns:
            Tuple of (success: bool, reason: str)
            - (True, "added") = successfully added new module
            - (False, "already_exists") = module already in registry (not an error)
            - (False, "error") = actual error occurred
        """
        try:
            # Load existing capabilities
            with open(CAPABILITIES_YAML, 'r') as f:
                capabilities = yaml.safe_load(f) or {}

            # Skip if module already exists
            if module_name in capabilities:
                logger.info(f"[integrator] Module {module_name} already exists in capabilities.yaml, skipping")
                return False, "already_exists"

            # Backup existing file before modification
            backup_path = CAPABILITIES_YAML.with_suffix('.yaml.backup')
            shutil.copy2(CAPABILITIES_YAML, backup_path)
            logger.info(f"[integrator] Backed up capabilities.yaml to {backup_path}")

            # Add new capability
            capabilities[module_name] = capability_entry

            # Write back with preserved formatting
            with open(CAPABILITIES_YAML, 'w') as f:
                f.write("# KLoROS Capability Registry\n")
                f.write("# Single source of truth for all modules, packs, and tools\n\n")
                yaml.dump(
                    capabilities,
                    f,
                    default_flow_style=False,
                    sort_keys=False,
                    allow_unicode=True
                )

            logger.info(f"[integrator] Added {module_name} to capabilities.yaml")
            return True, "added"

        except Exception as e:
            logger.error(f"[integrator] Failed to update capabilities.yaml: {e}")
            # Restore backup
            if backup_path.exists():
                shutil.copy2(backup_path, CAPABILITIES_YAML)
                logger.info("[integrator] Restored capabilities.yaml from backup")
            return False, "error"

    def process_investigations(self, max_integrations: int = 10) -> Dict[str, Any]:
        """
        Process unintegrated investigations and update capability registry.

        Args:
            max_integrations: Maximum number of modules to integrate in one run

        Returns:
            Summary dict with integration statistics
        """
        if not INVESTIGATIONS_LOG.exists():
            logger.warning("[integrator] No investigations log found")
            return {
                "processed": 0,
                "integrated": 0,
                "skipped": 0,
                "errors": 0
            }

        stats = {
            "processed": 0,
            "integrated": 0,
            "skipped": 0,
            "errors": 0,
            "skipped_reasons": {}
        }

        try:
            with open(INVESTIGATIONS_LOG, 'r') as f:
                all_investigations = [json.loads(line) for line in f if line.strip()]

        except Exception as e:
            logger.error(f"[integrator] Failed to load investigations: {e}")
            return stats

        # Filter to only new investigations (timestamp > last_processed_timestamp)
        if self.last_processed_timestamp:
            investigations = [
                inv for inv in all_investigations
                if str(inv.get('timestamp', '')) > str(self.last_processed_timestamp)
            ]
            logger.info(f"[integrator] Found {len(investigations)} new investigations (total: {len(all_investigations)}, last processed: {self.last_processed_timestamp})")
        else:
            investigations = all_investigations
            logger.info(f"[integrator] First run - processing all {len(investigations)} investigations")

        if not investigations:
            logger.info("[integrator] No new investigations to process")
            return stats

        # Track newest timestamp seen for saving at end
        newest_timestamp = self.last_processed_timestamp

        # Semantic evidence enrichment is now handled by semantic_dedup_consumer_daemon.py

        # CAPABILITY REGISTRY INTEGRATION: Add modules to capability registry
        for investigation in investigations:
            if stats["integrated"] >= max_integrations:
                logger.info(f"[integrator] Reached max integrations limit ({max_integrations})")
                break

            stats["processed"] += 1
            capability_key = investigation.get("capability", "unknown")

            # Track newest timestamp
            inv_timestamp = str(investigation.get('timestamp', ''))
            if inv_timestamp and inv_timestamp > str(newest_timestamp):
                newest_timestamp = inv_timestamp

            # Determine if should integrate
            should_integrate, reason = self._should_integrate(investigation)

            if not should_integrate:
                stats["skipped"] += 1
                stats["skipped_reasons"][reason] = stats["skipped_reasons"].get(reason, 0) + 1
                logger.debug(f"[integrator] Skipping {capability_key}: {reason}")
                continue

            # Extract module information
            module_path = self._extract_module_path(investigation)
            if not module_path:
                stats["skipped"] += 1
                stats["skipped_reasons"]["no_module_path"] = stats["skipped_reasons"].get("no_module_path", 0) + 1
                continue

            module_name = module_path.split(".")[-1]  # e.g., "src.audio" -> "audio"
            module_info = self._extract_module_info(investigation)
            probe_results = investigation.get("probe_results", [])

            # Ensure module has __init__.py for proper Python module structure
            init_success, init_reason = self._ensure_module_init(module_path, module_name, module_info)
            if init_reason == "created":
                logger.info(f"[integrator] 📝 Created __init__.py for {module_name}")
            elif not init_success and init_reason != "already_exists":
                logger.warning(f"[integrator] Could not ensure __init__.py for {module_name}: {init_reason}")

            # Generate capability entry
            capability_entry = self._generate_capability_entry(
                module_name, module_path, module_info, probe_results
            )

            # Update capabilities.yaml
            success, reason = self._update_capabilities_yaml(module_name, capability_entry)

            if success:
                stats["integrated"] += 1
                self._mark_integrated(capability_key, investigation)
                # Reload integrated IDs to prevent duplicate processing in same run
                self.integrated_ids.add(capability_key)
                logger.info(f"[integrator] ✅ Integrated {module_name} ({module_path})")
            elif reason == "already_exists":
                # Not an error - module already in registry
                stats["skipped"] += 1
                stats["skipped_reasons"]["already_in_capabilities_yaml"] = stats["skipped_reasons"].get("already_in_capabilities_yaml", 0) + 1
                logger.debug(f"[integrator] Skipping {module_name}: already in capabilities.yaml")
            else:
                # Actual error occurred
                stats["errors"] += 1
                logger.error(f"[integrator] ❌ Failed to integrate {module_name}")

        # Save newest timestamp for next run
        if newest_timestamp and newest_timestamp != self.last_processed_timestamp:
            self._save_last_processed_timestamp(newest_timestamp)
            logger.info(f"[integrator] Updated last processed timestamp to {newest_timestamp}")

        logger.info(f"[integrator] Integration complete: {stats}")
        return stats


def integrate_capabilities(max_integrations: int = 10) -> Dict[str, Any]:
    """
    Standalone function to integrate discovered capabilities.

    Args:
        max_integrations: Maximum number of modules to integrate

    Returns:
        Integration statistics
    """
    integrator = CapabilityIntegrator()
    return integrator.process_investigations(max_integrations)


if __name__ == "__main__":
    # Self-test and manual integration trigger
    logging.basicConfig(
        level=logging.INFO,
        format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
    )

    print("=== Capability Integrator ===\n")

    integrator = CapabilityIntegrator()
    stats = integrator.process_investigations(max_integrations=5)

    print(f"\n=== Integration Summary ===")
    print(f"Processed: {stats['processed']}")
    print(f"Integrated: {stats['integrated']}")
    print(f"Skipped: {stats['skipped']}")
    print(f"Errors: {stats['errors']}")

    if stats['skipped_reasons']:
        print(f"\nSkip reasons:")
        for reason, count in stats['skipped_reasons'].items():
            print(f"  {reason}: {count}")
