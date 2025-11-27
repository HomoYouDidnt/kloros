#!/usr/bin/env python3
"""
Systemd Service Investigator - Deep analysis of systemd unit files.

Purpose:
    When a question arises about a systemd service (e.g., "What does this service do?"),
    this system reads the unit file, parses its configuration, and uses LLM
    to understand its purpose and recommend enable/disable decisions.

    Think: System auditor examining unit configurations to understand system health.

Architecture:
    1. Read systemd unit files from /lib/systemd/system and /etc/systemd/system
    2. Parse: ExecStart, Description, Documentation, Dependencies, Type
    3. Check if binary exists and is executable
    4. Use LLM for semantic analysis (similar to ModuleInvestigator)
    5. Return structured result with confidence and recommendation

Integration:
    - Called by investigation_consumer when systemd_audit_* questions are received
    - Uses Ollama LLM for configuration analysis
    - Results written to curiosity_investigations.jsonl
"""

import os
import stat
import logging
import requests
from pathlib import Path
from typing import Dict, Any, List, Optional
from datetime import datetime

logger = logging.getLogger(__name__)


class SystemdServiceInvestigator:
    """
    Deep analysis engine for understanding systemd services.

    Reads unit files and uses LLM to determine what services do and their importance.
    """

    def __init__(self, ollama_host: Optional[str] = None, model: str = "qwen2.5-coder:7b"):
        """
        Initialize investigator.

        Args:
            ollama_host: Ollama server URL (automatic failover to gaming rig or local)
            model: Model to use for analysis
        """
        if ollama_host:
            self.ollama_host = ollama_host
        else:
            from config.models_config import get_ollama_url
            self.ollama_host = get_ollama_url()

        self.model = os.getenv("OLLAMA_MODEL", model)

        if not self.ollama_host.startswith("http"):
            self.ollama_host = f"http://{self.ollama_host}"

        logger.info(f"[systemd_investigator] Initialized with {self.model} at {self.ollama_host}")

    def investigate_service(self, service_name: str, unit_type: str = "service") -> Dict[str, Any]:
        """
        Deeply investigate a systemd service to understand its purpose and importance.

        Main entry point for service analysis.

        Args:
            service_name: Name of the service (without .service suffix)
            unit_type: Type of unit (service, socket, timer, etc.) - default "service"

        Returns:
            Investigation results dictionary with confidence and recommendations
        """
        logger.info(f"[systemd_investigator] Investigating {service_name}.{unit_type}")

        investigation = {
            "timestamp": datetime.now().isoformat(),
            "service_name": service_name,
            "unit_type": unit_type,
            "files_examined": [],
            "unit_content": {},
            "parsed_config": {},
            "evidence": [],
            "llm_analysis": {},
            "recommendation": None,
            "confidence": 0.0,
            "success": False,
            "error": None
        }

        try:
            unit_filename = f"{service_name}.{unit_type}"

            unit_file = self._find_unit_file(unit_filename)
            if not unit_file:
                investigation["error"] = f"Unit file {unit_filename} not found in systemd directories"
                logger.warning(f"[systemd_investigator] {investigation['error']}")
                return investigation

            investigation["files_examined"].append(str(unit_file))
            logger.info(f"[systemd_investigator] Found unit file at {unit_file}")

            unit_content = unit_file.read_text(errors='ignore')
            investigation["unit_content"]["path"] = str(unit_file)
            investigation["unit_content"]["content"] = unit_content

            parsed = self._parse_unit_file(unit_content)
            investigation["parsed_config"] = parsed
            logger.info(f"[systemd_investigator] Parsed unit config: Description='{parsed.get('Description', 'N/A')}' Type='{parsed.get('Type', 'simple')}'")

            evidence = self._gather_evidence(parsed, unit_file)
            investigation["evidence"] = evidence

            logger.info(f"[systemd_investigator] Gathered {len(evidence)} evidence items")

            llm_analysis = self._llm_analyze_service(
                service_name=service_name,
                unit_type=unit_type,
                parsed_config=parsed,
                evidence=evidence
            )

            if llm_analysis:
                investigation["llm_analysis"] = llm_analysis
                investigation["recommendation"] = llm_analysis.get("recommendation")
                investigation["confidence"] = llm_analysis.get("confidence", 0.0)
                investigation["success"] = True

                logger.info(
                    f"[systemd_investigator] ✓ Analysis complete: "
                    f"recommendation='{investigation['recommendation']}' "
                    f"confidence={investigation['confidence']:.2f}"
                )
            else:
                investigation["error"] = "LLM analysis failed"
                logger.warning("[systemd_investigator] LLM analysis failed")

        except Exception as e:
            investigation["error"] = str(e)
            logger.error(f"[systemd_investigator] Investigation failed: {e}", exc_info=True)

        return investigation

    def _find_unit_file(self, unit_filename: str) -> Optional[Path]:
        """
        Find unit file in systemd directories.

        Searches in order:
        1. /etc/systemd/system/{filename} (local/user overrides)
        2. /lib/systemd/system/{filename} (system default)
        3. /usr/lib/systemd/system/{filename} (older systems)

        Args:
            unit_filename: Unit file name with extension (e.g., "nginx.service")

        Returns:
            Path to unit file or None if not found
        """
        search_paths = [
            Path("/etc/systemd/system") / unit_filename,
            Path("/lib/systemd/system") / unit_filename,
            Path("/usr/lib/systemd/system") / unit_filename,
        ]

        for path in search_paths:
            if path.exists():
                return path

        return None

    def _parse_unit_file(self, content: str) -> Dict[str, Any]:
        """
        Parse systemd unit file content.

        Extracts key fields that help understand the service.

        Args:
            content: Unit file content

        Returns:
            Dict with parsed fields: Description, Type, ExecStart, ExecReload, etc.
        """
        config = {}
        current_section = None

        for line in content.split('\n'):
            line = line.strip()

            if not line or line.startswith('#') or line.startswith(';'):
                continue

            if line.startswith('[') and line.endswith(']'):
                current_section = line[1:-1]
                continue

            if '=' in line:
                key, value = line.split('=', 1)
                key = key.strip()
                value = value.strip()

                if key in ['ExecStart', 'ExecStartPre', 'ExecStartPost', 'ExecReload', 'ExecStop',
                          'Description', 'Documentation', 'Type', 'Restart', 'After', 'Before',
                          'Requires', 'Wants', 'Conflicts', 'PartOf']:
                    full_key = f"{key}_{current_section}" if current_section else key
                    config[key] = value

        return config

    def _gather_evidence(self, parsed_config: Dict[str, str], unit_file: Path) -> List[Dict[str, str]]:
        """
        Gather evidence about the service.

        Checks if binaries exist, examines unit configuration, etc.

        Args:
            parsed_config: Parsed unit configuration
            unit_file: Path to unit file

        Returns:
            List of evidence dicts with type and value
        """
        evidence = []

        if "Description" in parsed_config:
            evidence.append({
                "type": "description",
                "value": parsed_config["Description"]
            })

        if "Type" in parsed_config:
            evidence.append({
                "type": "service_type",
                "value": parsed_config["Type"]
            })

        if "Documentation" in parsed_config:
            evidence.append({
                "type": "documentation",
                "value": parsed_config["Documentation"]
            })

        if "ExecStart" in parsed_config:
            exec_start = parsed_config["ExecStart"]
            evidence.append({
                "type": "exec_start",
                "value": exec_start
            })

            binary_path = self._extract_binary_path(exec_start)
            if binary_path:
                binary_exists = Path(binary_path).exists()
                is_executable = False
                if binary_exists:
                    is_executable = bool(os.access(binary_path, os.X_OK))

                evidence.append({
                    "type": "binary_status",
                    "value": f"{binary_path}: exists={binary_exists}, executable={is_executable}"
                })

        dependencies = []
        for key in ['After', 'Before', 'Requires', 'Wants']:
            if key in parsed_config:
                dependencies.append(f"{key}={parsed_config[key]}")

        if dependencies:
            evidence.append({
                "type": "dependencies",
                "value": "; ".join(dependencies)
            })

        restart_setting = parsed_config.get("Restart", "no")
        evidence.append({
            "type": "restart_policy",
            "value": restart_setting
        })

        return evidence

    def _extract_binary_path(self, exec_start: str) -> Optional[str]:
        """
        Extract binary path from ExecStart line.

        Handles prefixes like -, @, + and arguments.

        Args:
            exec_start: ExecStart value from unit file

        Returns:
            Path to binary or None
        """
        cleaned = exec_start.lstrip('+-@').strip()
        parts = cleaned.split()
        if parts:
            return parts[0]
        return None

    def _llm_analyze_service(
        self,
        service_name: str,
        unit_type: str,
        parsed_config: Dict[str, str],
        evidence: List[Dict[str, str]]
    ) -> Optional[Dict[str, Any]]:
        """
        Use LLM to analyze the service configuration.

        Provides semantic understanding of what the service does and its importance.

        Args:
            service_name: Service name
            unit_type: Unit type
            parsed_config: Parsed unit configuration
            evidence: Gathered evidence about the service

        Returns:
            LLM analysis dict or None if failed
        """
        evidence_text = "\n".join([
            f"- {ev['type']}: {ev['value']}"
            for ev in evidence
        ])

        prompt = f"""You are a system administrator analyzing a systemd unit file for KLoROS (Knowledge-based Logic & Reasoning Operating System).

Service: {service_name}
Unit Type: {unit_type}

Configuration Details:
{evidence_text}

Based on this systemd unit configuration, provide analysis in JSON format:

{{
  "purpose": "Brief description of what this service does (1-2 sentences)",
  "key_functionality": [
    "What the service does",
    "Key responsibility or feature"
  ],
  "importance_for_ai_system": "Is this important for an AI operating system? Explain why or why not.",
  "is_critical": true/false,
  "recommendation": "enable" / "disable" / "monitor",
  "reasoning": "Explanation for the recommendation",
  "confidence": 0.0-1.0
}}

Consider:
- Critical services: system core, device drivers, networking, storage
- Important services: logging, monitoring, security
- Optional services: user applications, experimental features
- Disabled services: check if intentionally disabled

For KLoROS specifically:
- Services critical to AI operation: model serving, embeddings, memory management
- Services important for stability: journaling, resource management
- Services not needed: GUI, display managers, bluetooth (unless needed for IoT)

Output ONLY valid JSON, no markdown or explanations."""

        try:
            logger.info(f"[systemd_investigator] Sending service analysis to LLM")

            urls_to_try = [self.ollama_host]
            if self.ollama_host != "http://127.0.0.1:11434":
                urls_to_try.append("http://127.0.0.1:11434")

            response = None
            last_error = None

            for url in urls_to_try:
                from config.models_config import select_best_model_for_task
                model = select_best_model_for_task('code', url)
                try:
                    logger.info(f"[systemd_investigator] Trying {url} with {model}")
                    response = requests.post(
                        f"{url}/api/generate",
                        json={
                            "model": model,
                            "prompt": prompt,
                            "stream": True,
                            "options": {
                                "temperature": 0.3,
                                "num_predict": 1024
                            }
                        },
                        timeout=(5, 600),
                        stream=True
                    )
                    response.raise_for_status()
                    logger.info(f"[systemd_investigator] Successfully connected to {url}")
                    break
                except (requests.exceptions.Timeout, requests.exceptions.ConnectionError) as e:
                    logger.warning(f"[systemd_investigator] Failed to connect to {url}: {e}")
                    last_error = e
                    continue

            if response is None:
                raise last_error or Exception("All Ollama endpoints failed")

            import json
            llm_output = ""
            for line in response.iter_lines():
                if line:
                    try:
                        chunk = json.loads(line)
                        llm_output += chunk.get("response", "")
                        if chunk.get("done", False):
                            break
                    except json.JSONDecodeError:
                        continue

            llm_output = llm_output.strip()

            if not llm_output:
                logger.error("[systemd_investigator] LLM returned empty response")
                return None

            if llm_output.startswith("```json"):
                llm_output = llm_output.split("```json")[1].split("```")[0].strip()
            elif llm_output.startswith("```"):
                llm_output = llm_output.split("```")[1].split("```")[0].strip()

            analysis = json.loads(llm_output)

            logger.info(f"[systemd_investigator] ✓ LLM analysis complete (confidence: {analysis.get('confidence', 0)})")

            return analysis

        except requests.exceptions.RequestException as e:
            logger.error(f"[systemd_investigator] LLM request failed: {e}")
            return None

        except json.JSONDecodeError as e:
            logger.error(f"[systemd_investigator] Failed to parse LLM response as JSON: {e}")
            logger.debug(f"[systemd_investigator] LLM output was: {llm_output[:500]}")
            return None

        except Exception as e:
            logger.error(f"[systemd_investigator] LLM analysis failed: {e}", exc_info=True)
            return None


_systemd_investigator = None


def get_systemd_investigator(ollama_host: Optional[str] = None, model: str = "qwen2.5-coder:7b"):
    """Get singleton systemd investigator instance."""
    global _systemd_investigator
    if _systemd_investigator is None:
        _systemd_investigator = SystemdServiceInvestigator(ollama_host, model)
    return _systemd_investigator
