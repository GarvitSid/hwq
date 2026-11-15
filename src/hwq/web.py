"""Lightweight HTTP server for cloud deployments such as Render (FR-CLI-1).

Provides:
- GET /healthz: Health check endpoint for Render / Kubernetes.
- GET /api/facts: JSON endpoint returning gathered hardware facts.
- POST /api/ask: JSON endpoint to ask hardware questions.
- GET /: Interactive web interface to test queries in any browser.
"""

from __future__ import annotations

import json
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, HTTPServer
from typing import Any

from hwq.config import Config
from hwq.llm.base import create_llm_client
from hwq.orchestrator import Orchestrator
from hwq.session import Session
from hwq.tools.base import create_backend
from hwq.tools.registry import ToolRegistry

INDEX_HTML = """<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0">
  <title>hwq &mdash; Linux Hardware Q&A Assistant</title>
  <style>
    :root {
      --bg: #0d1117;
      --card-bg: #161b22;
      --border: #30363d;
      --text: #c9d1d9;
      --text-dim: #8b949e;
      --accent: #58a6ff;
      --accent-green: #3fb950;
      --user-msg: #1f6feb;
      --bot-msg: #21262d;
    }
    * { box-sizing: border-box; margin: 0; padding: 0; }
    body {
      background: var(--bg);
      color: var(--text);
      font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif;
      display: flex;
      flex-direction: column;
      height: 100vh;
      max-width: 900px;
      margin: 0 auto;
      padding: 16px;
    }
    header {
      padding: 12px 0 20px;
      border-bottom: 1px solid var(--border);
      display: flex;
      justify-content: space-between;
      align-items: center;
    }
    .brand { font-size: 1.25rem; font-weight: 700; color: #fff; }
    .brand span { color: var(--accent-green); }
    .badges { display: flex; gap: 8px; }
    .badge {
      font-size: 0.75rem;
      padding: 3px 8px;
      border-radius: 12px;
      background: var(--border);
      color: var(--text-dim);
    }
    .badge.active { background: rgba(63, 185, 80, 0.15); color: var(--accent-green); }
    main {
      flex: 1;
      overflow-y: auto;
      padding: 20px 0;
      display: flex;
      flex-direction: column;
      gap: 16px;
    }
    .message {
      max-width: 85%;
      padding: 12px 16px;
      border-radius: 8px;
      line-height: 1.5;
      font-size: 0.95rem;
      white-space: pre-wrap;
    }
    .message.user {
      align-self: flex-end;
      background: var(--user-msg);
      color: #fff;
      border-bottom-right-radius: 2px;
    }
    .message.assistant {
      align-self: flex-start;
      background: var(--bot-msg);
      border: 1px solid var(--border);
      border-bottom-left-radius: 2px;
    }
    .suggestions {
      display: flex;
      gap: 8px;
      flex-wrap: wrap;
      margin-bottom: 8px;
    }
    .chip {
      background: var(--card-bg);
      border: 1px solid var(--border);
      color: var(--accent);
      padding: 6px 12px;
      border-radius: 16px;
      font-size: 0.85rem;
      cursor: pointer;
      transition: background 0.15s;
    }
    .chip:hover { background: rgba(88, 166, 255, 0.1); }
    footer {
      border-top: 1px solid var(--border);
      padding-top: 12px;
    }
    form { display: flex; gap: 8px; }
    input[type="text"] {
      flex: 1;
      padding: 12px 16px;
      border-radius: 6px;
      background: var(--card-bg);
      border: 1px solid var(--border);
      color: #fff;
      font-size: 1rem;
    }
    input[type="text"]:focus { outline: none; border-color: var(--accent); }
    button {
      padding: 12px 20px;
      border-radius: 6px;
      background: var(--accent-green);
      color: #fff;
      font-weight: 600;
      border: none;
      cursor: pointer;
    }
    button:disabled { opacity: 0.5; cursor: not-allowed; }
  </style>
</head>
<body>
  <header>
    <div class="brand">hwq <span>&#9679;</span> Hardware Assistant</div>
    <div class="badges">
      <span class="badge active">Read-Only</span>
      <span class="badge active">Grounded</span>
      <span class="badge">Safe Allowlist</span>
    </div>
  </header>

  <main id="chat">
    <div class="message assistant">Hello! I am hwq, your local Linux hardware assistant.
Ask me about CPU, RAM, storage, GPU, or upgrade capabilities!</div>
  </main>

  <footer>
    <div class="suggestions">
      <span class="chip" onclick="ask(this.innerText)">Can I upgrade my RAM?</span>
      <span class="chip" onclick="ask(this.innerText)">What CPU do I have?</span>
      <span class="chip" onclick="ask(this.innerText)">Is my SSD NVMe?</span>
      <span class="chip" onclick="ask(this.innerText)">What GPU is installed?</span>
    </div>
    <form id="inputForm" onsubmit="event.preventDefault(); submitQuery();">
      <input type="text" id="queryInput"
             placeholder="Ask a hardware question..." autocomplete="off" />
      <button type="submit" id="sendBtn">Ask</button>
    </form>
  </footer>

  <script>
    const chat = document.getElementById('chat');
    const input = document.getElementById('queryInput');
    const sendBtn = document.getElementById('sendBtn');

    function appendMessage(text, role) {
      const div = document.createElement('div');
      div.className = 'message ' + role;
      div.innerText = text;
      chat.appendChild(div);
      chat.scrollTop = chat.scrollHeight;
    }

    function ask(text) {
      input.value = text;
      submitQuery();
    }

    async function submitQuery() {
      const q = input.value.trim();
      if (!q) return;

      appendMessage(q, 'user');
      input.value = '';
      input.disabled = true;
      sendBtn.disabled = true;

      const loadingMsg = document.createElement('div');
      loadingMsg.className = 'message assistant';
      loadingMsg.innerText = 'Inspecting hardware...';
      chat.appendChild(loadingMsg);
      chat.scrollTop = chat.scrollHeight;

      try {
        const resp = await fetch('/api/ask', {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ question: q }),
        });
        const data = await resp.json();
        chat.removeChild(loadingMsg);
        appendMessage(data.answer || 'No response returned.', 'assistant');
      } catch (err) {
        chat.removeChild(loadingMsg);
        appendMessage('Error: ' + err.message, 'assistant');
      } finally {
        input.disabled = false;
        sendBtn.disabled = false;
        input.focus();
      }
    }
  </script>
</body>
</html>
"""


def make_handler(config: Config) -> type[BaseHTTPRequestHandler]:
    """Factory creating an HTTP request handler configured with backend & orchestrator."""
    backend = create_backend(config)
    llm_client = create_llm_client(config)
    orchestrator = Orchestrator(backend=backend, llm=llm_client)
    registry = ToolRegistry()
    registry.probe_availability(backend)
    session = Session()

    class HWQRequestHandler(BaseHTTPRequestHandler):
        def do_GET(self) -> None:
            if self.path == "/" or self.path.startswith("/index.html"):
                self.send_response(HTTPStatus.OK)
                self.send_header("Content-Type", "text/html; charset=utf-8")
                self.end_headers()
                self.wfile.write(INDEX_HTML.encode("utf-8"))
                return

            if self.path == "/healthz" or self.path == "/health":
                self.send_response(HTTPStatus.OK)
                self.send_header("Content-Type", "application/json")
                self.end_headers()
                self.wfile.write(b'{"status": "ok", "app": "hwq"}')
                return

            if self.path == "/api/facts":
                facts_data: dict[str, Any] = {}
                for tool_name in registry.tool_names:
                    try:
                        env = registry.execute_tool(tool_name, {}, backend)
                        facts_data[tool_name] = env.model_dump()
                    except Exception as err:
                        facts_data[tool_name] = {"error": str(err)}

                payload = json.dumps(facts_data, indent=2).encode("utf-8")
                self.send_response(HTTPStatus.OK)
                self.send_header("Content-Type", "application/json")
                self.send_header("Content-Length", str(len(payload)))
                self.end_headers()
                self.wfile.write(payload)
                return

            self.send_response(HTTPStatus.NOT_FOUND)
            self.send_header("Content-Type", "application/json")
            self.end_headers()
            self.wfile.write(b'{"error": "Not found"}')

        def do_POST(self) -> None:
            if self.path == "/api/ask":
                try:
                    content_len = int(self.headers.get("Content-Length", 0))
                    body = self.rfile.read(content_len)
                    req_data = json.loads(body.decode("utf-8"))
                    question = str(req_data.get("question", "")).strip()

                    if not question:
                        self.send_response(HTTPStatus.BAD_REQUEST)
                        self.send_header("Content-Type", "application/json")
                        self.end_headers()
                        self.wfile.write(b'{"error": "Field \'question\' is required"}')
                        return

                    answer = orchestrator.run_turn(session, question)
                    res_body = json.dumps({
                        "question": question,
                        "answer": answer,
                        "status": "ok",
                    }).encode("utf-8")

                    self.send_response(HTTPStatus.OK)
                    self.send_header("Content-Type", "application/json")
                    self.send_header("Content-Length", str(len(res_body)))
                    self.end_headers()
                    self.wfile.write(res_body)
                except Exception as err:
                    err_body = json.dumps({"error": str(err)}).encode("utf-8")
                    self.send_response(HTTPStatus.INTERNAL_SERVER_ERROR)
                    self.send_header("Content-Type", "application/json")
                    self.send_header("Content-Length", str(len(err_body)))
                    self.end_headers()
                    self.wfile.write(err_body)
                return

            self.send_response(HTTPStatus.NOT_FOUND)
            self.send_header("Content-Type", "application/json")
            self.end_headers()
            self.wfile.write(b'{"error": "Not found"}')

        def log_message(self, format: str, *args: Any) -> None:
            # Minimal log format
            print(f"[hwq-http] {self.address_string()} - {format % args}")

    return HWQRequestHandler


def run_server(host: str = "0.0.0.0", port: int = 10000, config: Config | None = None) -> None:
    """Run the hwq web server on the specified host and port."""
    if config is None:
        from hwq.config import load_config

        config = load_config()

    handler_cls = make_handler(config)
    server = HTTPServer((host, port), handler_cls)
    print(f"Starting hwq web service at http://{host}:{port}")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\nStopping hwq web service...")
    finally:
        server.server_close()
