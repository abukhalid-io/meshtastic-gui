"""A tiny local HTTP control/inspection interface for this app.

Exists so a development/automation tool (or a person with curl) can read
live app state and trigger connect/disconnect WITHOUT screen-scraping the
GUI via screenshots or simulated clicks — those are slow, fragile, and get
confused the moment another window steals focus. Binds to 127.0.0.1 only;
never exposed on the network.

Endpoints:
    GET  /status   -> JSON snapshot (connection state, mqtt proxy state,
                       node/log counts, last error, etc.)
    GET  /log      -> plain text, the full in-memory log buffer
    POST /connect  -> triggers the same action as clicking Connect
    POST /disconnect -> triggers the same action as clicking Disconnect
"""
import json
import threading
from http.server import BaseHTTPRequestHandler, HTTPServer

from PySide6.QtCore import QObject, Signal


class DebugServer(QObject):
    command_requested = Signal(str)  # "connect" | "disconnect"
    send_requested = Signal(str, int, str)  # (text, channel_index, destination_id)

    def __init__(self, port=8765, parent=None):
        super().__init__(parent)
        self.port = port
        self._lock = threading.Lock()
        self._state = {}
        self._log_lines = []
        self._httpd = None
        self._thread = None

    # -- called from the GUI thread to publish state / log lines ---------
    def set_state(self, **kwargs):
        with self._lock:
            self._state.update(kwargs)

    def append_log(self, line: str):
        with self._lock:
            self._log_lines.append(line)
            if len(self._log_lines) > 4000:
                self._log_lines = self._log_lines[-4000:]

    # -- lifecycle -----------------------------------------------------
    def start(self):
        if self._httpd is not None:
            return
        try:
            handler_cls = self._make_handler()
            self._httpd = HTTPServer(("127.0.0.1", self.port), handler_cls)
        except OSError as e:  # noqa: BLE001 - port already in use, etc.
            self.append_log(f"[debug-server] gagal start di port {self.port}: {e}")
            self._httpd = None
            return
        self._thread = threading.Thread(target=self._httpd.serve_forever, daemon=True, name="debug-server")
        self._thread.start()
        self.append_log(f"[debug-server] aktif di http://127.0.0.1:{self.port}")

    def stop(self):
        if self._httpd is not None:
            self._httpd.shutdown()
            self._httpd = None

    def _make_handler(self):
        server = self

        class Handler(BaseHTTPRequestHandler):
            def log_message(self, *args):
                pass  # keep this off stderr — it would spam the console

            def _json(self, obj, code=200):
                body = json.dumps(obj, ensure_ascii=False).encode("utf-8")
                self.send_response(code)
                self.send_header("Content-Type", "application/json; charset=utf-8")
                self.send_header("Content-Length", str(len(body)))
                self.end_headers()
                self.wfile.write(body)

            def _text(self, text, code=200):
                body = text.encode("utf-8")
                self.send_response(code)
                self.send_header("Content-Type", "text/plain; charset=utf-8")
                self.send_header("Content-Length", str(len(body)))
                self.end_headers()
                self.wfile.write(body)

            def do_GET(self):  # noqa: N802 - stdlib API name
                if self.path == "/status":
                    with server._lock:
                        self._json(dict(server._state))
                elif self.path == "/log":
                    with server._lock:
                        text = "\n".join(server._log_lines)
                    self._text(text)
                elif self.path == "/transcript":
                    with server._lock:
                        text = server._state.get("transcript", "")
                    self._text(text)
                else:
                    self._json({"error": "not found", "try": ["/status", "/log", "/transcript"]}, 404)

            def do_POST(self):  # noqa: N802 - stdlib API name
                if self.path in ("/connect", "/disconnect"):
                    server.command_requested.emit(self.path.strip("/"))
                    self._json({"ok": True})
                elif self.path == "/send":
                    length = int(self.headers.get("Content-Length", 0))
                    try:
                        body = json.loads(self.rfile.read(length) or b"{}")
                    except Exception:  # noqa: BLE001
                        self._json({"error": "invalid JSON body"}, 400)
                        return
                    text = body.get("text", "")
                    if not text:
                        self._json({"error": "'text' is required"}, 400)
                        return
                    channel_index = int(body.get("channel_index", 0))
                    destination_id = body.get("destination_id", "^all")
                    server.send_requested.emit(text, channel_index, destination_id)
                    self._json({"ok": True})
                else:
                    self._json({"error": "not found", "try": ["/connect", "/disconnect", "/send"]}, 404)

        return Handler
