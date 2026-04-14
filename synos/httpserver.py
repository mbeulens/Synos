"""Local HTTP server to serve audio files and proxy streams to Sonos."""

import mimetypes
import os
import socket
import threading
from http.server import HTTPServer, BaseHTTPRequestHandler
from urllib.parse import quote, unquote

import requests as http_requests

# Ensure audio MIME types are registered
mimetypes.add_type("audio/flac", ".flac")
mimetypes.add_type("audio/ogg", ".ogg")
mimetypes.add_type("audio/aac", ".aac")
mimetypes.add_type("audio/mp4", ".m4a")
mimetypes.add_type("audio/x-ms-wma", ".wma")

# Log callback — set by the window
_log = None


def set_log_callback(callback):
    global _log
    _log = callback


def _logmsg(msg, tag=None):
    if _log:
        _log(msg, tag)


# Proxy registry: proxy_id -> {url, headers, content_type}
_proxy_registry = {}
_proxy_lock = threading.Lock()
_proxy_counter = 0


def register_proxy(audio_url, headers=None, content_type="audio/mpeg"):
    """Register a URL for proxying. Returns a proxy ID."""
    global _proxy_counter
    with _proxy_lock:
        _proxy_counter += 1
        proxy_id = str(_proxy_counter)
        _proxy_registry[proxy_id] = {
            "url": audio_url,
            "headers": headers or {},
            "content_type": content_type,
        }
    return proxy_id


class _AudioHandler(BaseHTTPRequestHandler):
    """Serves local files and proxies remote audio streams."""

    allowed_dirs = []

    def do_GET(self):
        path = unquote(self.path)

        if path.startswith("/proxy/"):
            self._handle_proxy(path)
        else:
            self._handle_file(path)

    def _handle_file(self, path):
        """Serve a local file from allowed directories."""
        parts = path.strip("/").split("/", 1)
        if len(parts) < 2:
            self.send_error(404)
            return

        try:
            dir_idx = int(parts[0])
        except ValueError:
            self.send_error(404)
            return

        if dir_idx < 0 or dir_idx >= len(self.allowed_dirs):
            self.send_error(404)
            return

        base = self.allowed_dirs[dir_idx]
        rel = parts[1]
        full = os.path.normpath(os.path.join(base, rel))

        if not full.startswith(os.path.normpath(base)):
            self.send_error(403)
            return

        if not os.path.isfile(full):
            self.send_error(404)
            return

        content_type, _ = mimetypes.guess_type(full)
        content_type = content_type or "application/octet-stream"
        file_size = os.path.getsize(full)

        self.send_response(200)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(file_size))
        self.end_headers()

        with open(full, "rb") as f:
            while True:
                chunk = f.read(65536)
                if not chunk:
                    break
                self.wfile.write(chunk)

    def _handle_proxy(self, path):
        """Proxy a remote audio stream — download to cache then serve."""
        proxy_id = path.strip("/").split("/", 1)[1] if "/" in path[1:] else ""

        with _proxy_lock:
            entry = _proxy_registry.get(proxy_id)

        if not entry:
            _logmsg(f"Proxy 404: unknown proxy ID {proxy_id}", "error")
            self.send_error(404)
            return

        url = entry["url"]
        headers = entry["headers"]
        content_type = entry["content_type"]
        cache_path = entry.get("cache_path")

        # Download to temp file if not already cached
        if not cache_path or not os.path.exists(cache_path):
            _logmsg(f"Proxy downloading: {proxy_id}")
            _logmsg(f"  Remote URL: {url[:100]}...")
            try:
                import tempfile
                resp = http_requests.get(url, headers=headers, stream=True, timeout=60)
                if resp.status_code != 200:
                    _logmsg(f"Proxy upstream error: {resp.status_code}", "error")
                    self.send_error(502)
                    return

                fd, cache_path = tempfile.mkstemp(suffix=".audio")
                with os.fdopen(fd, "wb") as f:
                    for chunk in resp.iter_content(chunk_size=65536):
                        if chunk:
                            f.write(chunk)

                with _proxy_lock:
                    entry["cache_path"] = cache_path
                _logmsg(f"Proxy cached: {cache_path} ({os.path.getsize(cache_path)} bytes)", "success")

            except Exception as e:
                _logmsg(f"Proxy download error: {e}", "error")
                try:
                    self.send_error(502)
                except Exception:
                    pass
                return

        # Serve the cached file
        try:
            file_size = os.path.getsize(cache_path)
            self.send_response(200)
            self.send_header("Content-Type", content_type)
            self.send_header("Content-Length", str(file_size))
            self.send_header("Accept-Ranges", "bytes")
            self.end_headers()

            with open(cache_path, "rb") as f:
                while True:
                    chunk = f.read(65536)
                    if not chunk:
                        break
                    self.wfile.write(chunk)

        except Exception as e:
            _logmsg(f"Proxy serve error: {e}", "error")

    def log_message(self, format, *args):
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
    """Manages a background HTTP server for serving audio files and proxying streams."""

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

    def proxy_url(self, proxy_id):
        """Get the HTTP URL for a proxied stream."""
        return f"http://{self._host}:{self._port}/proxy/{proxy_id}"
