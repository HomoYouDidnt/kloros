import os
import logging
import requests
from pathlib import Path
from typing import Optional, List

logger = logging.getLogger(__name__)


class LLMCodeGenerator:
    def __init__(
        self,
        ollama_host: Optional[str] = None,
        model: str = "qwen2.5:72b",
        temperature: float = 0.2,
        max_tokens: int = 8192
    ):
        self.ollama_host = ollama_host or os.getenv("OLLAMA_HOST", "http://100.67.244.66:11434")
        self.model = os.getenv("OLLAMA_MODEL", model)
        self.temperature = temperature
        self.max_tokens = max_tokens

        if not self.ollama_host.startswith("http"):
            self.ollama_host = f"http://{self.ollama_host}"

    def generate_fix_patch(
        self,
        question: str,
        hypothesis: str,
        evidence: List[str],
        report_path: Optional[Path],
        target_file: Path
    ) -> Optional[str]:
        if not target_file.exists():
            logger.error(f"Target file does not exist: {target_file}")
            return None

        try:
            file_content = target_file.read_text()
        except Exception as e:
            logger.error(f"Failed to read target file {target_file}: {e}")
            return None

        report_content = ""
        if report_path and report_path.exists():
            try:
                report_content = report_path.read_text()
            except Exception as e:
                logger.warning(f"Failed to read report {report_path}: {e}")

        evidence_text = "\n".join(f"- {e}" for e in evidence)

        prompt = f"""You are fixing an integration issue in KLoROS.

Issue: {question}
Hypothesis: {hypothesis}
Evidence:
{evidence_text}

Analysis Report:
{report_content}

Target File: {target_file}
Current Code:
```python
{file_content}
```

Generate a code patch that fixes this issue.
Output ONLY the complete patched file, no explanations or markdown.
"""

        try:
            response = requests.post(
                f"{self.ollama_host}/api/generate",
                json={
                    "model": self.model,
                    "prompt": prompt,
                    "stream": False,
                    "options": {
                        "temperature": self.temperature,
                        "num_predict": self.max_tokens
                    }
                },
                timeout=600
            )
            response.raise_for_status()
            result = response.json()
            patch = result.get("response", "").strip()

            if not patch:
                logger.error("LLM returned empty response")
                return None

            logger.info(f"Generated patch for {target_file} ({len(patch)} chars)")
            return patch

        except requests.exceptions.RequestException as e:
            logger.error(f"LLM request failed: {e}")
            return None
        except Exception as e:
            logger.error(f"Unexpected error generating patch: {e}")
            return None
