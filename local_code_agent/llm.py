from __future__ import annotations

import json
import urllib.error
import urllib.request
from dataclasses import dataclass
from typing import Iterable

from .config import AgentConfig


Message = dict[str, str]


class OllamaError(RuntimeError):
    """Raised when Ollama cannot satisfy a chat request."""


@dataclass
class OllamaClient:
    config: AgentConfig

    def chat(self, messages: Iterable[Message]) -> str:
        payload = {
            "model": self.config.model,
            "messages": list(messages),
            "stream": False,
        }
        data = json.dumps(payload).encode("utf-8")
        request = urllib.request.Request(
            f"{self.config.ollama_url}/api/chat",
            data=data,
            headers={"Content-Type": "application/json"},
            method="POST",
        )

        try:
            with urllib.request.urlopen(
                request,
                timeout=self.config.request_timeout_seconds,
            ) as response:
                body = response.read().decode("utf-8")
        except urllib.error.URLError as exc:
            raise OllamaError(
                "Could not reach Ollama. Start it with `ollama serve` or open the Ollama app."
            ) from exc

        parsed = json.loads(body)
        message = parsed.get("message", {})
        content = message.get("content")
        if not isinstance(content, str):
            raise OllamaError(f"Unexpected Ollama response: {body[:500]}")
        return content.strip()
