from __future__ import annotations

import shutil
import subprocess

from local_code_agent.config import DEFAULT_IGNORE_DIRS, AgentConfig
from local_code_agent.tools.files import is_probably_text_file


def search_code(config: AgentConfig, query: str) -> str:
    if not query.strip():
        return "Search query cannot be empty."

    if shutil.which("rg"):
        return _search_with_ripgrep(config, query)
    return _search_with_python(config, query)


def _search_with_ripgrep(config: AgentConfig, query: str) -> str:
    command = [
        "rg",
        "--line-number",
        "--hidden",
        "--glob",
        "!**/.git/**",
        query,
        str(config.workspace),
    ]
    for ignored in sorted(DEFAULT_IGNORE_DIRS - {".git"}):
        command.extend(["--glob", f"!**/{ignored}/**"])

    try:
        result = subprocess.run(
            command,
            capture_output=True,
            text=True,
            timeout=30,
            cwd=config.workspace,
        )
    except subprocess.TimeoutExpired:
        return "Search timed out."

    if result.returncode not in {0, 1}:
        return result.stderr[: config.max_tool_output_chars]
    return (result.stdout or "No matches found.")[: config.max_tool_output_chars]


def _search_with_python(config: AgentConfig, query: str) -> str:
    matches: list[str] = []
    lowered_query = query.lower()

    for path in config.workspace.rglob("*"):
        rel = path.relative_to(config.workspace)
        if any(part in DEFAULT_IGNORE_DIRS for part in rel.parts):
            continue
        if not path.is_file() or not is_probably_text_file(path):
            continue

        try:
            lines = path.read_text(encoding="utf-8", errors="replace").splitlines()
        except OSError:
            continue

        for line_no, line in enumerate(lines, start=1):
            if lowered_query in line.lower():
                matches.append(f"{rel}:{line_no}:{line}")
                if len("\n".join(matches)) >= config.max_tool_output_chars:
                    matches.append("[truncated]")
                    return "\n".join(matches)

    return "\n".join(matches) if matches else "No matches found."
