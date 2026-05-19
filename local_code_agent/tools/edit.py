from __future__ import annotations

import difflib
import re
from dataclasses import dataclass

from local_code_agent.config import AgentConfig
from local_code_agent.llm import OllamaClient
from local_code_agent.tools.files import read_file_full, write_file


EDIT_PROMPT = """You are editing one file for a local coding agent.

Return the complete replacement file, and nothing else.
Wrap the replacement exactly like this:

<replacement>
...full file content...
</replacement>

Rules:
- Preserve unrelated code.
- Keep the existing style.
- Do not include explanations outside the replacement tags.
- Do not use Markdown fences.
"""


@dataclass
class PendingEdit:
    path: str
    original: str
    replacement: str
    diff: str


def propose_edit(
    config: AgentConfig,
    client: OllamaClient,
    path: str,
    instruction: str,
) -> PendingEdit:
    original = read_file_full(config, path)
    response = client.chat(
        [
            {"role": "system", "content": EDIT_PROMPT},
            {
                "role": "user",
                "content": (
                    f"File path: {path}\n\n"
                    f"Instruction:\n{instruction}\n\n"
                    f"Current file:\n<current_file>\n{original}\n</current_file>"
                ),
            },
        ]
    )
    replacement = extract_replacement(response)
    diff = build_diff(path, original, replacement)
    return PendingEdit(path=path, original=original, replacement=replacement, diff=diff)


def extract_replacement(response: str) -> str:
    match = re.search(r"<replacement>\s*(.*?)\s*</replacement>", response, re.DOTALL)
    if not match:
        raise ValueError("Model did not return a <replacement>...</replacement> block.")
    return match.group(1)


def build_diff(path: str, original: str, replacement: str) -> str:
    original_lines = original.splitlines(keepends=True)
    replacement_lines = replacement.splitlines(keepends=True)
    diff = difflib.unified_diff(
        original_lines,
        replacement_lines,
        fromfile=f"{path} (current)",
        tofile=f"{path} (proposed)",
    )
    text = "".join(diff)
    return text or "No changes proposed."


def apply_edit(config: AgentConfig, edit: PendingEdit) -> None:
    current = read_file_full(config, edit.path)
    if current != edit.original:
        raise RuntimeError(
            "File changed after the patch was proposed. Discard this patch and create a new one."
        )
    write_file(config, edit.path, edit.replacement)
