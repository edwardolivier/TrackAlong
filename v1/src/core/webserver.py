"""
Minimal local HTTP server so the Leaflet map loads from http://localhost
instead of file://, which blocks external tile requests in Qt WebEngine.
"""

import http.server
import socket
import threading
from pathlib import Path

WEB_DIR = Path(__file__).parent.parent / "web"
_port: int = 0
_started = threading.Event()


class _SilentHandler(http.server.SimpleHTTPRequestHandler):
    def log_message(self, *args):
        pass  # suppress console noise

    def end_headers(self):
        # Allow any origin so QWebChannel JS can talk back
        self.send_header("Access-Control-Allow-Origin", "*")
        super().end_headers()


def _find_free_port() -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


def _serve(port: int):
    import os
    handler = lambda *a, **kw: _SilentHandler(*a, directory=str(WEB_DIR), **kw)
    with http.server.HTTPServer(("127.0.0.1", port), handler) as httpd:
        _started.set()
        httpd.serve_forever()


def start() -> int:
    """Start the server (idempotent) and return the port."""
    global _port
    if _port:
        return _port
    _port = _find_free_port()
    t = threading.Thread(target=_serve, args=(_port,), daemon=True)
    t.start()
    _started.wait(timeout=3)
    return _port


def map_url() -> str:
    return f"http://127.0.0.1:{start()}/map.html"
