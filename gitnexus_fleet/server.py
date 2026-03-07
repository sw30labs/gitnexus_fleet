import json
from pathlib import Path
from http.server import HTTPServer, BaseHTTPRequestHandler
from urllib.parse import urlparse

from .config import STATIC_DIR


class DashboardHandler(BaseHTTPRequestHandler):
    mcp_client = None
    statuses = {}
    dashboard_path = STATIC_DIR / "dashboard.html"

    def log_message(self, *args):
        pass

    def _json(self, data: dict, code: int = 200):
        body = json.dumps(data).encode()
        self.send_response(code)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Access-Control-Allow-Origin", "*")
        self.end_headers()
        self.wfile.write(body)

    def _html(self, path: Path):
        content = path.read_bytes()
        self.send_response(200)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.send_header("Content-Length", str(len(content)))
        self.end_headers()
        self.wfile.write(content)

    def do_OPTIONS(self):
        self.send_response(204)
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Methods", "GET, POST, OPTIONS")
        self.send_header("Access-Control-Allow-Headers", "Content-Type")
        self.end_headers()

    def do_GET(self):
        parsed = urlparse(self.path)
        path = parsed.path

        if path in ("/", "/index.html"):
            if self.dashboard_path.exists():
                self._html(self.dashboard_path)
            else:
                self._json({"error": "dashboard.html not found"}, 404)

        elif path == "/api/repos":
            repos_info = [
                {
                    "name": name,
                    "cloned": st.cloned,
                    "indexed": st.indexed,
                    "error": st.error,
                }
                for name, st in self.statuses.items()
            ]
            self._json({"repos": repos_info})

        elif path == "/api/health":
            self._json({"mcp_ready": self.mcp_client.ready if self.mcp_client else False})

        else:
            self._json({"error": "not found"}, 404)

    def do_POST(self):
        length = int(self.headers.get("Content-Length", 0))
        body = json.loads(self.rfile.read(length)) if length else {}
        parsed = urlparse(self.path)
        path = parsed.path

        if not self.mcp_client or not self.mcp_client.ready:
            self._json({"error": "MCP not ready yet"}, 503)
            return

        if path == "/api/query":
            q = body.get("query", "")
            repo = body.get("repo")
            args = {"query": q}
            if repo:
                args["repo"] = repo
            self._json(self.mcp_client.call_tool("query", args))

        elif path == "/api/impact":
            target = body.get("target", "")
            direction = body.get("direction", "upstream")
            repo = body.get("repo")
            args = {"target": target, "direction": direction}
            if repo:
                args["repo"] = repo
            self._json(self.mcp_client.call_tool("impact", args))

        elif path == "/api/context":
            name = body.get("name", "")
            repo = body.get("repo")
            args = {"name": name}
            if repo:
                args["repo"] = repo
            self._json(self.mcp_client.call_tool("context", args))

        elif path == "/api/cypher":
            cypher = body.get("cypher", "")
            repo = body.get("repo")
            args = {"query": cypher}
            if repo:
                args["repo"] = repo
            self._json(self.mcp_client.call_tool("cypher", args))

        elif path == "/api/list_repos":
            self._json(self.mcp_client.call_tool("list_repos", {}))

        elif path == "/api/ask":
            question = body.get("question", "")
            repo = body.get("repo")
            if not question:
                self._json({"error": "No question provided"}, 400)
                return
            try:
                from .nlq import translate_question, summarize_result

                tool_call = translate_question(question)
                tool_name = tool_call["tool"]
                tool_args = tool_call["args"]
                explanation = tool_call.get("explanation", "")

                if repo:
                    tool_args["repo"] = repo

                result = self.mcp_client.call_tool(tool_name, tool_args)

                if "error" in result:
                    self._json({
                        "error": result["error"],
                        "explanation": explanation,
                        "tool": tool_name,
                        "args": tool_args,
                    })
                    return

                summary = summarize_result(question, tool_name, result["result"])

                self._json({
                    "summary": summary,
                    "raw": result["result"],
                    "tool": tool_name,
                    "args": tool_args,
                    "explanation": explanation,
                })
            except Exception as e:
                self._json({"error": str(e)}, 500)

        else:
            self._json({"error": "unknown endpoint"}, 404)


def run_server(port: int):
    server = HTTPServer(("127.0.0.1", port), DashboardHandler)
    server.serve_forever()
