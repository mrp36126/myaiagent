from __future__ import annotations

import json
import sys
import traceback
from dataclasses import dataclass
from typing import Any

from .config import AgentConfig, load_config
from .llm import OllamaClient
from .prompts import SYSTEM_PROMPT
from .tools.edit import PendingEdit, apply_edit, propose_edit
from .tools.files import project_tree, read_file
from .tools.search import search_code
from .tools.shell import run_command


@dataclass
class ServerState:
    config: AgentConfig
    client: OllamaClient
    messages: list[dict[str, str]]
    pending_edit: PendingEdit | None = None


def new_state() -> ServerState:
    config = load_config()
    return ServerState(
        config=config,
        client=OllamaClient(config),
        messages=[{"role": "system", "content": SYSTEM_PROMPT}],
    )


def add_context(state: ServerState, title: str, content: str) -> None:
    state.messages.append(
        {
            "role": "user",
            "content": f"{title}\n\n```text\n{content}\n```",
        }
    )


def handle_request(state: ServerState, request: dict[str, Any]) -> dict[str, Any]:
    action = request.get("action")
    request_id = request.get("id")

    if action == "status":
        return {
            "id": request_id,
            "ok": True,
            "data": {
                "model": state.config.model,
                "ollamaUrl": state.config.ollama_url,
                "workspace": str(state.config.workspace),
                "hasPendingPatch": state.pending_edit is not None,
            },
        }

    if action == "clear":
        state.messages = [{"role": "system", "content": SYSTEM_PROMPT}]
        state.pending_edit = None
        return {"id": request_id, "ok": True, "data": {"message": "Context cleared."}}

    if action == "tree":
        content = project_tree(state.config)
        add_context(state, "Project tree:", content)
        return {"id": request_id, "ok": True, "data": {"content": content}}

    if action == "read":
        path = require_string(request, "path")
        content = read_file(state.config, path)
        add_context(state, f"File `{path}`:", content)
        return {"id": request_id, "ok": True, "data": {"content": content}}

    if action == "search":
        query = require_string(request, "query")
        content = search_code(state.config, query)
        add_context(state, f"Search results for `{query}`:", content)
        return {"id": request_id, "ok": True, "data": {"content": content}}

    if action == "run":
        command = require_string(request, "command")
        content = run_command(state.config, command)
        add_context(state, f"Command output for `{command}`:", content)
        return {"id": request_id, "ok": True, "data": {"content": content}}

    if action == "chat":
        message = require_string(request, "message")
        state.messages.append({"role": "user", "content": message})
        answer = state.client.chat(state.messages)
        state.messages.append({"role": "assistant", "content": answer})
        return {"id": request_id, "ok": True, "data": {"content": answer}}

    if action == "patch":
        path = require_string(request, "path")
        instruction = require_string(request, "instruction")
        edit = propose_edit(state.config, state.client, path, instruction)
        state.pending_edit = edit
        return {
            "id": request_id,
            "ok": True,
            "data": {
                "path": edit.path,
                "diff": edit.diff,
                "hasChanges": edit.diff != "No changes proposed.",
            },
        }

    if action == "apply":
        if state.pending_edit is None:
            raise ValueError("No pending patch.")
        path = state.pending_edit.path
        diff = state.pending_edit.diff
        apply_edit(state.config, state.pending_edit)
        add_context(state, f"Applied patch to `{path}`:", diff)
        state.pending_edit = None
        return {"id": request_id, "ok": True, "data": {"message": f"Applied patch: {path}"}}

    if action == "discard":
        if state.pending_edit is None:
            return {"id": request_id, "ok": True, "data": {"message": "No pending patch."}}
        path = state.pending_edit.path
        state.pending_edit = None
        return {"id": request_id, "ok": True, "data": {"message": f"Discarded patch: {path}"}}

    raise ValueError(f"Unknown action: {action}")


def require_string(request: dict[str, Any], key: str) -> str:
    value = request.get(key)
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"Missing required string: {key}")
    return value.strip()


def write_response(response: dict[str, Any]) -> None:
    print(json.dumps(response), flush=True)


def main() -> int:
    state = new_state()
    for line in sys.stdin:
        try:
            request = json.loads(line)
            write_response(handle_request(state, request))
        except Exception as exc:
            request_id = None
            try:
                request_id = json.loads(line).get("id")
            except Exception:
                pass
            write_response(
                {
                    "id": request_id,
                    "ok": False,
                    "error": str(exc),
                    "trace": traceback.format_exc(limit=3),
                }
            )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
