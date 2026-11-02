"""Provider-agnostic, opt-in LLM integration for TITAN EVOLVE.

Uses the OpenAI-compatible Chat Completions protocol and Python stdlib only.
No API key is stored in source code or the project ZIP.
"""
from __future__ import annotations

import json
import os
import re
import urllib.error
import urllib.request
from dataclasses import dataclass
from typing import Any, Mapping
from urllib.parse import urlsplit


@dataclass(frozen=True)
class LLMConfig:
    base_url: str
    model: str
    api_key: str
    timeout_seconds: float = 30.0
    max_response_bytes: int = 1_000_000


class LLMProviderError(RuntimeError):
    """Raised when an LLM provider cannot return a valid response."""


class OpenAICompatibleProvider:
    """Minimal OpenAI-compatible chat provider with bounded requests."""

    def __init__(self, config: LLMConfig) -> None:
        parsed = urlsplit(config.base_url)
        local_http = parsed.scheme == "http" and parsed.hostname in {"localhost", "127.0.0.1", "::1"}
        if parsed.scheme != "https" and not local_http:
            raise ValueError("LLM endpoint must use HTTPS (HTTP is allowed only for localhost).")
        if not parsed.hostname or parsed.username or parsed.password:
            raise ValueError("LLM endpoint must have a hostname and no embedded credentials.")
        if parsed.port not in (None, 443) and not local_http:
            raise ValueError("Remote LLM endpoints must use standard HTTPS port 443.")
        if not config.model.strip():
            raise ValueError("An explicit LLM model name is required.")
        if not config.api_key.strip() and not local_http:
            raise ValueError("An API key is required for remote LLM endpoints.")
        if not 1 <= config.timeout_seconds <= 120:
            raise ValueError("timeout_seconds must be between 1 and 120.")
        if not 1024 <= config.max_response_bytes <= 5_000_000:
            raise ValueError("max_response_bytes must be between 1KB and 5MB.")
        self.config = config
        self.endpoint = config.base_url.rstrip("/")
        if not self.endpoint.endswith("/chat/completions"):
            self.endpoint += "/chat/completions"

    @classmethod
    def from_environment(cls) -> "OpenAICompatibleProvider | None":
        api_key = os.getenv("TITAN_LLM_API_KEY") or os.getenv("OPENAI_API_KEY")
        base_url = os.getenv("TITAN_LLM_BASE_URL", "https://api.openai.com/v1")
        model = os.getenv("TITAN_LLM_MODEL", "gpt-4.1-mini")
        parsed = urlsplit(base_url)
        local_http = parsed.scheme == "http" and parsed.hostname in {"localhost", "127.0.0.1", "::1"}
        if not api_key and not local_http:
            return None
        return cls(LLMConfig(base_url=base_url, model=model, api_key=api_key or "",
                             timeout_seconds=float(os.getenv("TITAN_LLM_TIMEOUT", "30"))))

    def complete_json(self, system_prompt: str, user_prompt: str,
                      max_tokens: int = 1200) -> dict[str, Any]:
        if not system_prompt.strip() or not user_prompt.strip():
            raise ValueError("Both system_prompt and user_prompt are required.")
        if not 64 <= max_tokens <= 8000:
            raise ValueError("max_tokens must be between 64 and 8000.")
        payload = {
            "model": self.config.model,
            "temperature": 0.2,
            "max_tokens": max_tokens,
            "response_format": {"type": "json_object"},
            "messages": [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt[:100_000]},
            ],
        }
        headers = {"Content-Type": "application/json", "Accept": "application/json"}
        if self.config.api_key:
            headers["Authorization"] = f"Bearer {self.config.api_key}"
        request = urllib.request.Request(
            self.endpoint, data=json.dumps(payload).encode("utf-8"),
            headers=headers, method="POST")
        try:
            with urllib.request.urlopen(request, timeout=self.config.timeout_seconds) as response:
                raw = response.read(self.config.max_response_bytes + 1)
        except (urllib.error.URLError, TimeoutError, OSError) as exc:
            raise LLMProviderError(f"LLM provider request failed: {type(exc).__name__}") from exc
        if len(raw) > self.config.max_response_bytes:
            raise LLMProviderError("LLM provider response exceeded configured size limit.")
        try:
            envelope = json.loads(raw.decode("utf-8"))
            content = envelope["choices"][0]["message"]["content"]
            if isinstance(content, list):
                content = "".join(part.get("text", "") for part in content if isinstance(part, Mapping))
            if not isinstance(content, str):
                raise ValueError("message content is not text")
            content = re.sub(r"^\s*```(?:json)?\s*|\s*```\s*$", "", content.strip(), flags=re.I)
            result = json.loads(content)
            if not isinstance(result, dict):
                raise ValueError("JSON response must be an object")
            return result
        except (KeyError, IndexError, TypeError, ValueError, UnicodeDecodeError) as exc:
            raise LLMProviderError("LLM provider returned an invalid JSON chat response.") from exc
