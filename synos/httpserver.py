"""Local HTTP server to serve audio files to Sonos speakers."""

import mimetypes
import os
import socket
import threading
from http.server import HTTPServer, SimpleHTTPRequestHandler
from urllib.parse import quote, unquote


# Ensure audio MIME types are registered
mimetypes.add_type("audio/flac", ".flac")
mimetypes.add_type("audio/ogg", ".ogg")
mimetypes.add_type("audio/aac", ".aac")
mimetypes.add_type("audio/mp4", ".m4a")
mimetypes.add_type("audio/x-ms-wma", ".wma")


class _AudioHandler(SimpleHTTPRequestHandler):
    """Serves files from a list of allowed directories."""

    allowed_dirs = []

    def translate_path(self, path):
        """Map URL path to a real file path within allowed dirs."""
        # URL format: /dir_index/relative/path/to/file.mp3
        path = unquote(path)
        parts = path.strip("/").split("/", 1)
        if len(parts) < 2:
            return ""

        try:
            dir_idx = int(parts[0])
        except ValueError:
            return ""

        if dir_idx < 0 or dir_idx >= len(self.allowed_dirs):
            return ""

        base = self.allowed_dirs[dir_idx]
        rel = parts[1]
        full = os.path.normpath(os.path.join(base, rel))

        # Prevent directory traversal
        if not full.startswith(os.path.normpath(base)):
            return ""

        return full

    def log_message(self, format, *args):
        # Silence request logging
        pass


def _get_local_ip():
    """Get the local IP address that can reach the network."""
    try:
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        s.connect(("8.8.8.8", 80))
        ip = s.getsockname()[0]
        s.close()
        return ip
    except Exception:
        return "127.0.0.1"


class AudioServer:
    """Manages a background HTTP server for serving audio files."""

    def __init__(self):
        self._server = None
        self._thread = None
        self._dirs = []
        self._host = _get_local_ip()
        self._port = 0

    @property
    def running(self):
        return self._server is not None

    def set_dirs(self, dirs):
        """Update the list of allowed directories."""
        self._dirs = list(dirs)
        _AudioHandler.allowed_dirs = self._dirs

    def start(self):
        """Start the HTTP server on a random available port."""
        if self._server:
            return

        _AudioHandler.allowed_dirs = self._dirs
        self._server = HTTPServer((self._host, 0), _AudioHandler)
        self._port = self._server.server_address[1]

        self._thread = threading.Thread(target=self._server.serve_forever, daemon=True)
        self._thread.start()

    def stop(self):
        """Stop the HTTP server."""
        if self._server:
            self._server.shutdown()
            self._server = None
            self._thread = None

    def file_url(self, dir_index, relative_path):
        """Get the HTTP URL for a file in a given library directory."""
        encoded = quote(relative_path)
        return f"http://{self._host}:{self._port}/{dir_index}/{encoded}"
