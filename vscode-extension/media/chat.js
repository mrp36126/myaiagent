const vscode = acquireVsCodeApi();

const messages = document.getElementById('messages');
const form = document.getElementById('form');
const promptInput = document.getElementById('prompt');
const sendButton = document.getElementById('send');
const statusEl = document.getElementById('status');
const applyButton = document.getElementById('apply');
const discardButton = document.getElementById('discard');
const clearButton = document.getElementById('clear');

form.addEventListener('submit', (event) => {
  event.preventDefault();
  const text = promptInput.value;
  promptInput.value = '';
  vscode.postMessage({ type: 'prompt', text });
});

applyButton.addEventListener('click', () => vscode.postMessage({ type: 'apply' }));
discardButton.addEventListener('click', () => vscode.postMessage({ type: 'discard' }));
clearButton.addEventListener('click', () => {
  messages.innerHTML = '';
  vscode.postMessage({ type: 'clear' });
});

window.addEventListener('message', (event) => {
  const message = event.data;

  if (message.type === 'ready') {
    addMessage('system', 'Ready. Try /tree or /read README.md.');
    return;
  }

  if (message.type === 'status') {
    const status = message.status;
    statusEl.textContent = `${status.model} · ${status.workspace}`;
    applyButton.disabled = !status.hasPendingPatch;
    discardButton.disabled = !status.hasPendingPatch;
    return;
  }

  if (message.type === 'busy') {
    sendButton.disabled = message.busy;
    sendButton.textContent = message.busy ? '...' : 'Send';
    return;
  }

  if (message.type === 'patch') {
    addMessage('agent', message.text, 'Patch');
    return;
  }

  if (message.type === 'agent') {
    addMessage('agent', message.text, 'Agent');
    return;
  }

  if (message.type === 'user') {
    addMessage('user', message.text, 'You');
    return;
  }

  if (message.type === 'system') {
    addMessage('system', message.text, 'System');
    return;
  }

  if (message.type === 'error') {
    addMessage('error', message.text, 'Error');
  }
});

function addMessage(kind, text, label = '') {
  const el = document.createElement('article');
  el.className = `message ${kind}`;

  if (label) {
    const labelEl = document.createElement('span');
    labelEl.className = 'label';
    labelEl.textContent = label;
    el.appendChild(labelEl);
  }

  const pre = document.createElement('pre');
  pre.textContent = text;
  el.appendChild(pre);
  messages.appendChild(el);
  el.scrollIntoView({ block: 'end' });
}
