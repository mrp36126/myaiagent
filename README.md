# My Local AI Coding Agent

A free, local-first coding assistant that talks to Ollama, reads your codebase, searches files, shows project structure, and can run local developer commands from an interactive CLI.

## Requirements

- Python 3.10+
- [Ollama](https://ollama.com/)
- A local coding model, for example:

```powershell
ollama pull qwen2.5-coder:3b
```

If you have more RAM/VRAM, try the larger 7B model:

```powershell
ollama pull qwen2.5-coder:7b
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
/patch README.md :: improve the usage section
/apply                 Apply the currently proposed patch
/discard               Discard the currently proposed patch
/clear                 Clear conversation context
/exit                  Quit
```

Anything else is sent to the local model as a normal chat message.

## Configuration

Environment variables:

```text
LOCAL_AGENT_MODEL=qwen2.5-coder:3b
LOCAL_AGENT_OLLAMA_URL=http://localhost:11434
LOCAL_AGENT_WORKSPACE=.
```

## Safety Model

This first version is intentionally conservative:

- It only reads files inside the configured workspace.
- It skips common heavy/private directories like `.git`, `node_modules`, `.venv`, and `dist`.
- It proposes file edits as diffs before writing anything.
- It only writes a proposed patch when you run `/apply`.
- It refuses to apply a patch if the file changed after the proposal was created.
- `/run` executes commands locally, so use it the same way you would use a terminal.

## Safe Editing

Use `/patch` with a file path, then `::`, then the change you want:

```text
/patch README.md :: add a short troubleshooting section for Ollama PATH issues
```

The agent asks the local model for a complete replacement file, compares it to the current file, and prints a unified diff. Nothing is written yet.

If the diff looks good:

```text
/apply
```

If it looks wrong:

```text
/discard
```

This workflow is intentionally cautious because small local models can occasionally produce messy edits.
