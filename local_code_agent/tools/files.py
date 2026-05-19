from __future__ import annotations

from pathlib import Path

from local_code_agent.config import DEFAULT_IGNORE_DIRS, AgentConfig


TEXT_EXTENSIONS = {
    ".c",
    ".cc",
    ".cfg",
    ".conf",
    ".cpp",
    ".cs",
    ".css",
    ".env",
    ".go",
    ".h",
    ".html",
    ".ini",
    ".java",
    ".js",
    ".json",
    ".jsx",
    ".kt",
    ".lock",
    ".md",
    ".mjs",
    ".php",
    ".ps1",
    ".py",
    ".rb",
    ".rs",
    ".sh",
    ".sql",
    ".svelte",
    ".toml",
    ".ts",
    ".tsx",
    ".txt",
    ".vue",
    ".xml",
    ".yaml",
    ".yml",
}


def resolve_workspace_path(config: AgentConfig, user_path: str) -> Path:
    path = (config.workspace / user_path).resolve()
    if path != config.workspace and config.workspace not in path.parents:
        raise ValueError(f"Path is outside workspace: {user_path}")
    return path


def read_file(config: AgentConfig, user_path: str) -> str:
    path = resolve_workspace_path(config, user_path)
    if not path.exists():
        return f"File not found: {user_path}"
    if not path.is_file():
        return f"Not a file: {user_path}"

    try:
        content = path.read_text(encoding="utf-8", errors="replace")
    except OSError as exc:
        return f"Could not read {user_path}: {exc}"

    truncated = content[: config.max_file_chars]
    if len(content) > config.max_file_chars:
        truncated += "\n\n[truncated]"
    return truncated


def project_tree(config: AgentConfig, max_entries: int = 250) -> str:
    entries: list[str] = []
    root = config.workspace

    for path in sorted(root.rglob("*")):
        rel = path.relative_to(root)
        if any(part in DEFAULT_IGNORE_DIRS for part in rel.parts):
            continue
        depth = len(rel.parts) - 1
        if depth > 5:
            continue
        marker = "/" if path.is_dir() else ""
        entries.append(f"{'  ' * depth}{rel.name}{marker}")
        if len(entries) >= max_entries:
            entries.append("[truncated]")
            break

    return "\n".join(entries) if entries else "(empty workspace)"


def is_probably_text_file(path: Path) -> bool:
    return path.suffix.lower() in TEXT_EXTENSIONS or path.name in {
        ".gitignore",
        "Dockerfile",
        "Makefile",
        "README",
    }
