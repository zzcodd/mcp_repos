"""Built-in HTTP server that renders the todos as an interactive dashboard.

Runs in a daemon thread so it dies with the MCP server process. Serves a
single-page app (index.html) plus a small JSON API:

    GET  /             -> the SPA (index.html, re-read from disk each request)
    GET  /api/todos    -> {"todos": [...]}                      (read)
    POST /api/add      -> {text, priority?, due?, tags?}        (create)
    POST /api/toggle   -> {id, done}                            (mark done/undone)
    POST /api/edit     -> {id, text?, priority?, due?, tags?}   (edit fields)
    POST /api/delete   -> {id}                                  (remove)

tags may be a list or a comma-separated string; "" clears all tags on edit.

This is READ AND WRITE, bound to 127.0.0.1 only, with NO auth — intended for
local personal use. Don't expose the port to other machines.

All mutations go through todo_mcp.data, so the dashboard and the MCP tools
share the same single source of truth (.claude/todos.md).
"""
from __future__ import annotations

import json
import socket
import threading
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path
from typing import Callable

from todo_mcp import data

_TEMPLATE_PATH = Path(__file__).parent / "templates" / "index.html"


def _is_port_free(port: int) -> bool:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        try:
            s.bind(("127.0.0.1", port))
        except OSError:
            return False
        return True


def _find_port(start: int = 8765, max_tries: int = 10) -> int:
    for offset in range(max_tries):
        port = start + offset
        if _is_port_free(port):
            return port
    raise RuntimeError(f"No free port in range {start}-{start + max_tries - 1}")


def start(get_todos_path: Callable[[], Path], port: int | None = None) -> int:
    """Start the dashboard HTTP server in a daemon thread. Returns the bound port.

    port=None  -> pick a predictable free port starting at 8765 (production).
    port=0     -> let the OS assign an ephemeral port (handy for tests).
    """
    bind_port = _find_port() if port is None else port

    class Handler(BaseHTTPRequestHandler):
        # ---------- response helpers ----------
        def _send(self, body: bytes, content_type: str, status: int = 200) -> None:
            self.send_response(status)
            self.send_header("Content-Type", content_type)
            self.send_header("Content-Length", str(len(body)))
            self.send_header("Cache-Control", "no-store")
            self.end_headers()
            self.wfile.write(body)

        def _json(self, obj: dict, status: int = 200) -> None:
            self._send(
                json.dumps(obj, ensure_ascii=False, default=str).encode("utf-8"),
                "application/json; charset=utf-8",
                status,
            )

        def _read_body(self) -> dict:
            length = int(self.headers.get("Content-Length", 0))
            if length == 0:
                return {}
            return json.loads(self.rfile.read(length).decode("utf-8"))

        # ---------- GET ----------
        def do_GET(self):  # noqa: N802 — BaseHTTPRequestHandler API
            path = self.path.split("?", 1)[0]
            if path == "/":
                try:
                    # Re-read the template every request -> HTML/CSS/JS hot-reload.
                    html = _TEMPLATE_PATH.read_text(encoding="utf-8")
                    self._send(html.encode("utf-8"), "text/html; charset=utf-8")
                except Exception as e:  # noqa: BLE001
                    self._send(f"<pre>template error: {e}</pre>".encode("utf-8"),
                               "text/html; charset=utf-8", 500)
            elif path == "/api/todos":
                try:
                    self._json({"todos": data.load(get_todos_path())})
                except Exception as e:  # noqa: BLE001
                    self._json({"error": str(e)}, 500)
            else:
                self.send_error(404)

        # ---------- POST (mutations) ----------
        def do_POST(self):  # noqa: N802
            path = self.path.split("?", 1)[0]
            try:
                body = self._read_body()
                todos_path = get_todos_path()
                if path == "/api/add":
                    todo = data.add(
                        todos_path,
                        body["text"],
                        priority=body.get("priority", "med"),
                        due=body.get("due") or None,
                        tags=body.get("tags"),
                    )
                elif path == "/api/toggle":
                    todo = data.mark_done(todos_path, int(body["id"]), done=bool(body["done"]))
                elif path == "/api/edit":
                    todo = data.edit(
                        todos_path,
                        int(body["id"]),
                        text=body.get("text"),
                        priority=body.get("priority"),
                        due=body.get("due"),
                        done=body.get("done"),
                        tags=body.get("tags"),
                    )
                elif path == "/api/delete":
                    todo = data.remove(todos_path, int(body["id"]))
                else:
                    self.send_error(404)
                    return
                self._json({"todo": todo})
            except KeyError as e:
                self._json({"error": f"missing field: {e}"}, 400)
            except ValueError as e:
                self._json({"error": str(e)}, 400)
            except Exception as e:  # noqa: BLE001
                self._json({"error": str(e)}, 500)

        def log_message(self, format, *args):  # noqa: A002
            # Silence default access log — keep stderr clean for MCP debugging.
            pass

    httpd = HTTPServer(("127.0.0.1", bind_port), Handler)
    actual_port = httpd.server_address[1]
    thread = threading.Thread(target=httpd.serve_forever, daemon=True)
    thread.start()
    return actual_port
