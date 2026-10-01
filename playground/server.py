"""Local Jev playground. Serves index.html and proxies requests to TypeSafe so the API key stays here.

Run from the repo root: .venv/bin/python playground/server.py
"""
import json
import os
import sys
import urllib.error
import urllib.request
import webbrowser
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

HERE = Path(__file__).resolve().parent
ENV_FILE = HERE.parent / ".env"
API = "https://api.typesafe.ai/v1"
HOST, PORT = "127.0.0.1", 8765


def load_key(env_file=ENV_FILE):
    """TYPESAFE_API_KEY from the repo root .env, else from the environment."""
    if env_file.exists():
        for line in env_file.read_text().splitlines():
            line = line.strip()
            if line.startswith("export "):
                line = line[7:].lstrip()
            name, sep, value = line.partition("=")
            if sep and name.strip() == "TYPESAFE_API_KEY":
                value = value.strip()
                if len(value) >= 2 and value[0] == value[-1] and value[0] in "\"'":
                    value = value[1:-1]
                if value:
                    return value
    return os.environ.get("TYPESAFE_API_KEY", "").strip()


def call_api(method, path, key, body=None):
    """(status, body bytes) from TypeSafe. Error statuses come back as they are, not as exceptions."""
    req = urllib.request.Request(API + path, data=body, method=method, headers={
        "Authorization": f"Bearer {key}", "Content-Type": "application/json", "Accept": "application/json"})
    try:
        with urllib.request.urlopen(req, timeout=120) as resp:
            return resp.status, resp.read()
    except urllib.error.HTTPError as e:
        return e.code, e.read()
    except (urllib.error.URLError, TimeoutError) as e:
        return 502, json.dumps({"error": "could not reach TypeSafe", "detail": str(getattr(e, "reason", e))}).encode()


class Handler(BaseHTTPRequestHandler):
    key = ""

    def send(self, status, body, ctype="application/json"):
        self.send_response(status)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(body)

    def trusted(self):
        """Refuse other web pages: a foreign Host (DNS rebinding) or Origin, or a non-JSON POST (no CORS preflight)."""
        allowed = {f"127.0.0.1:{PORT}", f"localhost:{PORT}"}
        if self.headers.get("Host") not in allowed:
            return False
        origin = self.headers.get("Origin")
        if origin and origin.split("://", 1)[-1] not in allowed:
            return False
        return self.command == "GET" or self.headers.get("Content-Type", "").startswith("application/json")

    def do_GET(self):
        if not self.trusted():
            return self.send(403, b'{"error": "forbidden"}')
        if self.path in ("/", "/index.html"):
            self.send(200, (HERE / "index.html").read_bytes(), "text/html; charset=utf-8")
        elif self.path == "/models":
            self.send(*call_api("GET", "/models", self.key))
        else:
            self.send(404, b'{"error": "not found"}')

    def do_POST(self):
        if not self.trusted():
            return self.send(403, b'{"error": "forbidden"}')
        if self.path != "/run":
            return self.send(404, b'{"error": "not found"}')
        body = self.rfile.read(int(self.headers.get("Content-Length") or 0))
        self.send(*call_api("POST", "/systemone", self.key, body))

    def log_message(self, fmt, *args):  # keep the terminal quiet; nothing here ever includes the key
        pass


def main():
    key = load_key()
    if not key:
        print(f"TYPESAFE_API_KEY not found. Put it in {ENV_FILE} or export it, then run again.", file=sys.stderr)
        sys.exit(1)
    Handler.key = key
    server = ThreadingHTTPServer((HOST, PORT), Handler)
    url = f"http://{HOST}:{PORT}/"
    print(f"Jev playground running at {url} (Ctrl+C to stop)", flush=True)
    if not os.environ.get("PLAYGROUND_NO_BROWSER"):
        webbrowser.open(url)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass


if __name__ == "__main__":
    main()
