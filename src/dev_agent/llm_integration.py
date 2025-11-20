"""
LLM Integration for Coding Agent

Connects coding agent to Ollama models:
- qwen2.5-coder:7b for CODE mode
- Configurable endpoints and models
- Prompt formatting and response parsing
"""
import os
import json
import requests
from typing import Optional, Dict
from pathlib import Path

class OllamaLLM:
    """
    Ollama LLM client for coding agent.

    Uses qwen2.5-coder:7b by default for fast, specialized code generation.
    """

    def __init__(
        self,
        model: Optional[str] = None,
        base_url: Optional[str] = None,
        timeout: int = 120
    ):
        """
        Initialize Ollama LLM client.

        Args:
            model: Model name (default: from env or SSOT config code mode)
            base_url: Ollama API URL (default: from env or SSOT config code mode)
            timeout: Request timeout in seconds
        """
        # Get defaults from SSOT config for code mode
        from src.config.models_config import get_ollama_url_for_mode, get_ollama_model_for_mode
        default_url = get_ollama_url_for_mode("code")
        default_model = get_ollama_model_for_mode("code")

        self.model = model or os.getenv("OLLAMA_CODE_MODEL", default_model)
        self.base_url = base_url or os.getenv("OLLAMA_CODE_URL", default_url)
        self.timeout = timeout

        # Ensure base_url doesn't have trailing slash
        self.base_url = self.base_url.rstrip('/')

    def __call__(self, prompt: str, max_tokens: int = 2000) -> str:
        """
        Call LLM with prompt.

        Args:
            prompt: Input prompt
            max_tokens: Maximum tokens to generate

        Returns:
            Generated response text
        """
        url = f"{self.base_url}/api/generate"

        payload = {
            "model": self.model,
            "prompt": prompt,
            "stream": False,
            "options": {
                "num_predict": max_tokens,
                "temperature": 0.2,  # Low temp for code generation
                "top_p": 0.95
            }
        }

        try:
            response = requests.post(
                url,
                json=payload,
                timeout=self.timeout
            )

            response.raise_for_status()

            data = response.json()
            return data.get("response", "")

        except requests.exceptions.Timeout:
            raise RuntimeError(f"LLM request timed out after {self.timeout}s")
        except requests.exceptions.RequestException as e:
            raise RuntimeError(f"LLM request failed: {e}")
        except json.JSONDecodeError as e:
            raise RuntimeError(f"Failed to parse LLM response: {e}")

    def test_connection(self) -> bool:
        """
        Test connection to Ollama API.

        Returns:
            True if connection successful
        """
        try:
            url = f"{self.base_url}/api/tags"
            response = requests.get(url, timeout=5)
            response.raise_for_status()

            data = response.json()
            models = data.get("models", [])
            model_names = [m.get("name") for m in models]

            if self.model in model_names:
                print(f"✓ Model {self.model} available")
                return True
            else:
                print(f"⚠ Model {self.model} not found. Available: {model_names}")
                return False

        except Exception as e:
            print(f"✗ Connection test failed: {e}")
            return False

def create_llm_callable(
    model: Optional[str] = None,
    base_url: Optional[str] = None
) -> callable:
    """
    Create LLM callable for coding agent.

    Args:
        model: Model name (optional)
        base_url: Ollama API URL (optional)

    Returns:
        Callable that takes prompt and returns response
    """
    llm = OllamaLLM(model=model, base_url=base_url)
    return llm

# Test function
def test_llm_integration():
    """Test LLM integration with simple prompt."""
    print("=== Testing LLM Integration ===\n")

    llm = OllamaLLM()

    # Test connection
    print("Testing connection...")
    if not llm.test_connection():
        return False

    # Test simple prompt
    print("\nTesting simple prompt...")
    prompt = """Write a Python function to add two numbers.

Output ONLY the code in ```python ... ``` format."""

    response = llm(prompt, max_tokens=200)

    print(f"Response:\n{response}\n")

    # Check if response contains code
    if "def " in response or "```python" in response:
        print("✓ Response contains code")
        return True
    else:
        print("✗ Response does not contain code")
        return False

if __name__ == "__main__":
    success = test_llm_integration()
    exit(0 if success else 1)
