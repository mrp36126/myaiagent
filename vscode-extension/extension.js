const vscode = require('vscode');
const cp = require('child_process');
const readline = require('readline');

class AgentBackend {
  constructor(context) {
    this.context = context;
    this.nextId = 1;
    this.pending = new Map();
    this.process = undefined;
    this.reader = undefined;
  }

  start() {
    if (this.process) {
      return;
    }

    const workspace = getWorkspaceFolder();
    const config = vscode.workspace.getConfiguration('myLocalAgent');
    const pythonPath = config.get('pythonPath') || 'python';
    const extensionRoot = this.context.extensionUri.fsPath;
    const env = {
      ...process.env,
      LOCAL_AGENT_WORKSPACE: workspace,
      LOCAL_AGENT_MODEL: config.get('model') || 'qwen2.5-coder:3b',
      LOCAL_AGENT_OLLAMA_URL: config.get('ollamaUrl') || 'http://localhost:11434',
      PYTHONPATH: process.env.PYTHONPATH
        ? `${extensionRoot}${pathDelimiter()}${process.env.PYTHONPATH}`
        : extensionRoot
    };

    this.process = cp.spawn(pythonPath, ['-m', 'local_code_agent.vscode_server'], {
      cwd: workspace,
      env,
      stdio: ['pipe', 'pipe', 'pipe']
    });

    this.reader = readline.createInterface({ input: this.process.stdout });
    this.reader.on('line', (line) => this.handleLine(line));
    this.process.stderr.on('data', (data) => {
      console.error(`[Local AI Agent] ${data.toString()}`);
    });
    this.process.on('exit', () => {
      this.process = undefined;
      for (const [, pending] of this.pending) {
        pending.reject(new Error('Local agent backend exited.'));
      }
      this.pending.clear();
    });
  }

  restart() {
    this.stop();
    this.start();
  }

  stop() {
    if (this.reader) {
      this.reader.close();
      this.reader = undefined;
    }
    if (this.process) {
      this.process.kill();
      this.process = undefined;
    }
  }

  request(payload) {
    this.start();
    const id = this.nextId++;
    const message = { id, ...payload };
    return new Promise((resolve, reject) => {
      this.pending.set(id, { resolve, reject });
      this.process.stdin.write(`${JSON.stringify(message)}\n`, (error) => {
        if (error) {
          this.pending.delete(id);
          reject(error);
        }
      });
    });
  }

  handleLine(line) {
    let response;
    try {
      response = JSON.parse(line);
    } catch (error) {
      console.error(`[Local AI Agent] Invalid backend JSON: ${line}`);
      return;
    }

    const pending = this.pending.get(response.id);
    if (!pending) {
      return;
    }
    this.pending.delete(response.id);

    if (response.ok) {
      pending.resolve(response.data);
    } else {
      pending.reject(new Error(response.error || 'Unknown backend error.'));
    }
  }
}

class ChatViewProvider {
  constructor(context, backend) {
    this.context = context;
    this.backend = backend;
    this.view = undefined;
  }

  resolveWebviewView(webviewView) {
    this.view = webviewView;
    webviewView.webview.options = { enableScripts: true };
    webviewView.webview.html = this.getHtml(webviewView.webview);

    webviewView.webview.onDidReceiveMessage(async (message) => {
      await this.handleWebviewMessage(message);
    });

    this.post({ type: 'ready' });
    this.refreshStatus();
  }

  async handleWebviewMessage(message) {
    try {
      if (message.type === 'status') {
        await this.refreshStatus();
        return;
      }

      if (message.type === 'clear') {
        const data = await this.backend.request({ action: 'clear' });
        this.post({ type: 'system', text: data.message });
        await this.refreshStatus();
        return;
      }

      if (message.type === 'discard') {
        const data = await this.backend.request({ action: 'discard' });
        this.post({ type: 'system', text: data.message });
        await this.refreshStatus();
        return;
      }

      if (message.type === 'apply') {
        const data = await this.backend.request({ action: 'apply' });
        this.post({ type: 'system', text: data.message });
        await this.refreshStatus();
        return;
      }

      if (message.type === 'prompt') {
        await this.handlePrompt(message.text || '');
      }
    } catch (error) {
      this.post({ type: 'error', text: error.message });
    }
  }

  async handlePrompt(text) {
    const trimmed = text.trim();
    if (!trimmed) {
      return;
    }

    this.post({ type: 'user', text: trimmed });
    this.post({ type: 'busy', busy: true });

    try {
      const result = await this.dispatchPrompt(trimmed);
      this.post(result);
      await this.refreshStatus();
    } finally {
      this.post({ type: 'busy', busy: false });
    }
  }

  async dispatchPrompt(text) {
    if (text === '/tree') {
      const data = await this.backend.request({ action: 'tree' });
      return { type: 'agent', text: codeBlock(data.content) };
    }

    if (text.startsWith('/read ')) {
      const path = text.slice('/read '.length).trim();
      const data = await this.backend.request({ action: 'read', path });
      return { type: 'agent', text: codeBlock(data.content) };
    }

    if (text.startsWith('/search ')) {
      const query = text.slice('/search '.length).trim();
      const data = await this.backend.request({ action: 'search', query });
      return { type: 'agent', text: codeBlock(data.content) };
    }

    if (text.startsWith('/run ')) {
      const command = text.slice('/run '.length).trim();
      const data = await this.backend.request({ action: 'run', command });
      return { type: 'agent', text: codeBlock(data.content) };
    }

    if (text.startsWith('/patch ')) {
      const value = text.slice('/patch '.length);
      const separator = value.indexOf('::');
      if (separator === -1) {
        return { type: 'error', text: 'Usage: /patch <path> :: <task>' };
      }
      const path = value.slice(0, separator).trim();
      const instruction = value.slice(separator + 2).trim();
      const data = await this.backend.request({ action: 'patch', path, instruction });
      return {
        type: 'patch',
        text: data.hasChanges ? codeBlock(data.diff, 'diff') : 'No changes proposed.'
      };
    }

    const data = await this.backend.request({ action: 'chat', message: text });
    return { type: 'agent', text: data.content };
  }

  async refreshStatus() {
    try {
      const data = await this.backend.request({ action: 'status' });
      this.post({ type: 'status', status: data });
    } catch (error) {
      this.post({ type: 'error', text: error.message });
    }
  }

  post(message) {
    if (this.view) {
      this.view.webview.postMessage(message);
    }
  }

  getHtml(webview) {
    const nonce = String(Date.now());
    const styleUri = webview.asWebviewUri(
      vscode.Uri.joinPath(this.context.extensionUri, 'vscode-extension', 'media', 'chat.css')
    );
    const scriptUri = webview.asWebviewUri(
      vscode.Uri.joinPath(this.context.extensionUri, 'vscode-extension', 'media', 'chat.js')
    );

    return `<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0">
  <meta http-equiv="Content-Security-Policy" content="default-src 'none'; style-src ${webview.cspSource}; script-src 'nonce-${nonce}';">
  <link href="${styleUri}" rel="stylesheet">
  <title>Local AI Agent</title>
</head>
<body>
  <header>
    <strong>Local AI Agent</strong>
    <span id="status">Starting...</span>
  </header>
  <main id="messages"></main>
  <section id="actions">
    <button id="apply" disabled>Apply</button>
    <button id="discard" disabled>Discard</button>
    <button id="clear">Clear</button>
  </section>
  <form id="form">
    <textarea id="prompt" rows="4" placeholder="/read README.md&#10;/patch README.md :: improve the intro&#10;Ask a coding question..."></textarea>
    <button id="send" type="submit">Send</button>
  </form>
  <script nonce="${nonce}" src="${scriptUri}"></script>
</body>
</html>`;
  }
}

function getWorkspaceFolder() {
  const folders = vscode.workspace.workspaceFolders;
  if (!folders || folders.length === 0) {
    throw new Error('Open a workspace folder before starting the local agent.');
  }
  return folders[0].uri.fsPath;
}

function codeBlock(text, language = 'text') {
  return `\`\`\`${language}\n${text}\n\`\`\``;
}

function pathDelimiter() {
  return process.platform === 'win32' ? ';' : ':';
}

function activate(context) {
  const backend = new AgentBackend(context);
  const provider = new ChatViewProvider(context, backend);

  context.subscriptions.push(
    vscode.window.registerWebviewViewProvider('myLocalAgent.chatView', provider),
    vscode.commands.registerCommand('myLocalAgent.focus', async () => {
      await vscode.commands.executeCommand('workbench.view.extension.myLocalAgent');
    }),
    vscode.commands.registerCommand('myLocalAgent.restart', () => {
      backend.restart();
      vscode.window.showInformationMessage('Local AI Agent backend restarted.');
    }),
    { dispose: () => backend.stop() }
  );
}

function deactivate() {}

module.exports = { activate, deactivate };
