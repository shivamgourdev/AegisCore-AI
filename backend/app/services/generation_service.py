"""LLM generation service with Gemini-first, Ollama fallback.

Supports two generation paths:
1. Google Gemini API (if API key configured)
2. Ollama local LLM (phi3.5:3.8b)

Falls back gracefully when one provider is unavailable. Never claims
generation succeeded unless a real model call was made.
"""

import logging
from typing import Any

import httpx

from app.core.config import settings

logger = logging.getLogger(__name__)


class GenerationService:
    """LLM generation with Gemini-first, Ollama fallback.

    Attempts Gemini first (if API key configured), then falls back to
    local Ollama model. Never claims generation succeeded unless a real
    model call was made.
    """

    def __init__(self) -> None:
        self.gemini_api_key = settings.cloud_ai_api_key
        self.gemini_base_url = settings.cloud_ai_base_url.rstrip("/")
        self.gemini_model = settings.cloud_ai_model
        self.ollama_base_url = settings.ollama_base_url.rstrip("/")
        self.ollama_model = settings.rag_llm_model
        self._gemini_available: Optional[bool] = None
        self._ollama_available: Optional[bool] = None

    def _client(self) -> httpx.Client:
        """Create an httpx client with appropriate timeout."""
        return httpx.Client(timeout=httpx.Timeout(180.0))

    def generate(
        self,
        system_prompt: str,
        user_prompt: str,
        temperature: float = 0.3,
    ) -> str:
        """Generate text using the best available model.

        Tries Gemini first, falls back to Ollama, raises on failure.

        Args:
            system_prompt: System instructions.
            user_prompt: User query/context.
            temperature: Sampling temperature (0.0-1.0).

        Returns:
            Generated text response.

        Raises:
            RuntimeError: If both Gemini and Ollama are unavailable.
        """
        # Try Gemini first
        if self.gemini_api_key:
            try:
                return self._generate_gemini(system_prompt, user_prompt, temperature)
            except Exception as e:
                logger.warning(f"Gemini generation failed: {e}. Falling back to Ollama.")

        # Fall back to Ollama
        try:
            return self._generate_ollama(system_prompt, user_prompt, temperature)
        except Exception as e:
            raise RuntimeError(
                f"LLM generation failed. Gemini: unavailable, Ollama: {e}"
            ) from e

    def _generate_gemini(
        self,
        system_prompt: str,
        user_prompt: str,
        temperature: float,
    ) -> str:
        """Generate using Gemini API."""
        url = f"{self.gemini_base_url}/models/{self.gemini_model}:generateContent"
        headers = {"Content-Type": "application/json"}
        params = {"key": self.gemini_api_key}

        # Gemini uses a different prompt structure
        contents = [
            {
                "role": "user",
                "parts": [
                    {"text": f"{system_prompt}\n\n{user_prompt}"}
                ],
            }
        ]

        payload = {
            "contents": contents,
            "generationConfig": {
                "temperature": temperature,
                "maxOutputTokens": 2048,
            },
        }

        response = self._client().post(url, headers=headers, params=params, json=payload)
        if response.status_code != 200:
            raise RuntimeError(f"Gemini API error: HTTP {response.status_code}: {response.text[:200]}")

        data = response.json()
        candidates = data.get("candidates", [])
        if not candidates:
            raise RuntimeError(f"Gemini returned no candidates: {data}")

        content = candidates[0].get("content", {})
        parts = content.get("parts", [])
        if not parts:
            raise RuntimeError(f"Gemini response has no parts: {data}")

        text = parts[0].get("text", "")
        if not text:
            raise RuntimeError(f"Gemini response has no text: {data}")

        return text

    def _generate_ollama(
        self,
        system_prompt: str,
        user_prompt: str,
        temperature: float,
    ) -> str:
        """Generate using Ollama local model."""
        url = f"{self.ollama_base_url}/api/generate"
        payload = {
            "model": self.ollama_model,
            "prompt": f"{system_prompt}\n\n{user_prompt}",
            "temperature": temperature,
            "stream": False,
        }

        response = self._client().post(url, json=payload)
        if response.status_code != 200:
            raise RuntimeError(
                f"Ollama API error: HTTP {response.status_code}: {response.text[:200]}"
            )

        data = response.json()
        text = data.get("response", "")
        if not text:
            raise RuntimeError(f"Ollama response has no text: {data}")

        return text

    def is_available(self) -> bool:
        """Check if at least one generation provider is available."""
        # Check Ollama first (no credentials needed)
        try:
            self._generate_ollama("You are a test.", "Hello", 0.0)
            return True
        except Exception:
            pass

        # Check Gemini if key configured
        if self.gemini_api_key:
            try:
                self._generate_gemini("You are a test.", "Hello", 0.0)
                return True
            except Exception:
                pass

        return False

    def gemini_available(self) -> bool:
        """Check if Gemini API is configured and reachable."""
        if not self.gemini_api_key:
            return False
        try:
            self._generate_gemini("You are a test.", "Hello", 0.0)
            return True
        except Exception:
            return False

    def ollama_available(self) -> bool:
        """Check if Ollama model is reachable."""
        try:
            self._generate_ollama("You are a test.", "Hello", 0.0)
            return True
        except Exception:
            return False
