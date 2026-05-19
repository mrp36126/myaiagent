# My Local AI Coding Agent

A free, local-first coding assistant that talks to Ollama, reads your codebase, searches files, shows project structure, and can run local developer commands from an interactive CLI.

## Requirements

- Python 3.10+
- [Ollama](https://ollama.com/)
- A local coding model, for example:

```powershell
ollama pull qwen2.5-coder:7b
```

For a weaker machine:

```powershell
ollama pull qwen2.5-coder:3b
```

Optional but recommended for fast code search:

```powershell
winget install BurntSushi.ripgrep.MSVC
```

## Quick Start

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m local_code_agent
```

If you want to use a different model:

```powershell
$env:LOCAL_AGENT_MODEL = "qwen2.5-coder:3b"
python -m local_code_agent
```

## Commands

Inside the agent:

```text
/help                  Show commands
/model                 Show current model and Ollama URL
/read README.md        Load a file into the chat context
/search functionName   Search the workspace using ripgrep if available
/tree                  Show a compact project tree
/run pytest            Run a local command and load output into context
/clear                 Clear conversation context
/exit                  Quit
```

Anything else is sent to the local model as a normal chat message.

## Configuration

Environment variables:

```text
LOCAL_AGENT_MODEL=qwen2.5-coder:7b
LOCAL_AGENT_OLLAMA_URL=http://localhost:11434
LOCAL_AGENT_WORKSPACE=.
```

## Safety Model

This first version is intentionally conservative:

- It only reads files inside the configured workspace.
- It skips common heavy/private directories like `.git`, `node_modules`, `.venv`, and `dist`.
- It does not auto-edit files yet.
- `/run` executes commands locally, so use it the same way you would use a terminal.

Next recommended feature: add patch proposal and reviewed patch application.
