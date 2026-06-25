from __future__ import annotations

from typing import Protocol

import httpx


class LlmProvider(Protocol):
    def generate(self, prompt: str) -> str:
        ...


class OllamaProvider:
    def __init__(self, base_url: str, model: str, timeout: float = 120.0):
        self.base_url = base_url.rstrip("/")
        self.model = model
        self.timeout = timeout

    def generate(self, prompt: str) -> str:
        response = httpx.post(
            f"{self.base_url}/api/generate",
            json={"model": self.model, "prompt": prompt, "stream": False},
            timeout=self.timeout,
        )
        response.raise_for_status()
        return str(response.json().get("response", ""))


class MockProvider:
    def __init__(self, response: str = "mock answer"):
        self.response = response

    def generate(self, prompt: str) -> str:
        return self.response
