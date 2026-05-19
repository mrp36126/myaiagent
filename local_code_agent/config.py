from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path


DEFAULT_MODEL = "qwen2.5-coder:3b"
DEFAULT_OLLAMA_URL = "http://localhost:11434"

DEFAULT_IGNORE_DIRS = {
    ".git",
    ".hg",
    ".idea",
    ".mypy_cache",
    ".next",
    ".pytest_cache",
    ".ruff_cache",
    ".tox",
    ".venv",
    "__pycache__",
    "build",
    "coverage",
    "dist",
    "node_modules",
    "target",
}


@dataclass(frozen=True)
class AgentConfig:
    model: str
    ollama_url: str
    workspace: Path
    max_file_chars: int = 24_000
    max_tool_output_chars: int = 24_000
    request_timeout_seconds: int = 180


def load_config() -> AgentConfig:
    workspace = Path(os.getenv("LOCAL_AGENT_WORKSPACE", ".")).resolve()
    return AgentConfig(
        model=os.getenv("LOCAL_AGENT_MODEL", DEFAULT_MODEL),
        ollama_url=os.getenv("LOCAL_AGENT_OLLAMA_URL", DEFAULT_OLLAMA_URL).rstrip("/"),
        workspace=workspace,
    )
