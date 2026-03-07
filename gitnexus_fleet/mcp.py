import json
import subprocess
import threading
from pathlib import Path

from .config import console


class GitNexusMCP:
    """Thread-safe MCP stdio client for gitnexus."""

    def __init__(self):
        self.process = None
        self.lock = threading.Lock()
        self._msg_id = 0
        self.ready = False

    def start(self):
        try:
            self.process = subprocess.Popen(
                ["npx", "-y", "gitnexus@latest", "mcp"],
                stdin=subprocess.PIPE,
                stdout=subprocess.PIPE,
                stderr=subprocess.DEVNULL,
                text=True,
                bufsize=1,
                cwd=str(Path.home()),
            )
            self._initialize()
            self.ready = True
        except Exception as e:
            console.print(f"[red]MCP start failed: {e}[/red]")

    def _next_id(self):
        self._msg_id += 1
        return self._msg_id

    def _send(self, msg: dict):
        self.process.stdin.write(json.dumps(msg) + "\n")
        self.process.stdin.flush()

    def _recv(self):
        while True:
            line = self.process.stdout.readline()
            if not line:
                return None
            line = line.strip()
            if not line:
                continue
            try:
                return json.loads(line)
            except json.JSONDecodeError:
                continue

    def _initialize(self):
        self._send({
            "jsonrpc": "2.0", "id": self._next_id(),
            "method": "initialize",
            "params": {
                "protocolVersion": "2024-11-05",
                "capabilities": {},
                "clientInfo": {"name": "fleet-dashboard", "version": "1.0"},
            },
        })
        self._recv()
        self._send({"jsonrpc": "2.0", "method": "notifications/initialized"})

    def call_tool(self, name: str, arguments: dict) -> dict:
        if not self.ready:
            return {"error": "MCP server not ready"}
        with self.lock:
            msg_id = self._next_id()
            self._send({
                "jsonrpc": "2.0", "id": msg_id,
                "method": "tools/call",
                "params": {"name": name, "arguments": arguments},
            })
            while True:
                resp = self._recv()
                if resp is None:
                    return {"error": "MCP disconnected"}
                if resp.get("id") != msg_id:
                    continue
                if "error" in resp:
                    return {"error": resp["error"].get("message", "Unknown MCP error")}
                content = resp.get("result", {}).get("content", [])
                text = "\n".join(c.get("text", "") for c in content if c.get("type") == "text")
                return {"result": text}

    def stop(self):
        if self.process:
            try:
                self.process.terminate()
                self.process.wait(timeout=5)
            except Exception:
                self.process.kill()
            self.process = None
            self.ready = False
