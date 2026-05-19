from __future__ import annotations

import subprocess

from local_code_agent.config import AgentConfig


def run_command(config: AgentConfig, command: str) -> str:
    if not command.strip():
        return "Command cannot be empty."

    try:
        result = subprocess.run(
            command,
            capture_output=True,
            text=True,
            timeout=120,
            cwd=config.workspace,
            shell=True,
        )
    except subprocess.TimeoutExpired:
        return "Command timed out after 120 seconds."
    except OSError as exc:
        return f"Could not run command: {exc}"

    output = []
    output.append(f"exit_code: {result.returncode}")
    if result.stdout:
        output.append("\nstdout:\n" + result.stdout)
    if result.stderr:
        output.append("\nstderr:\n" + result.stderr)

    return "\n".join(output)[: config.max_tool_output_chars]
