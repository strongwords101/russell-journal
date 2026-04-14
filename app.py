import json
import os
import socket
import threading
from datetime import datetime
from http.server import HTTPServer, BaseHTTPRequestHandler
from urllib.parse import urlparse

# On cloud (Railway etc.) set DATA_DIR env var to the mounted volume path.
# Locally it defaults to the project directory.
_base = os.path.dirname(os.path.abspath(__file__))
DATA_DIR = os.environ.get("DATA_DIR", _base)
ENTRIES_FILE = os.path.join(DATA_DIR, "entries.json")


def load_entries():
    if not os.path.exists(ENTRIES_FILE):
        return []
    with open(ENTRIES_FILE, "r", encoding="utf-8") as f:
        return json.load(f)


def save_entries(entries):
    with open(ENTRIES_FILE, "w", encoding="utf-8") as f:
        json.dump(entries, f, indent=2, ensure_ascii=False)


class Handler(BaseHTTPRequestHandler):
    def log_message(self, format, *args):
        pass  # suppress request logging

    def send_json(self, data, status=200):
        body = json.dumps(data).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", len(body))
        self.send_header("Access-Control-Allow-Origin", "*")
        self.end_headers()
        self.wfile.write(body)

    def send_file(self, path, content_type):
        with open(path, "rb") as f:
            body = f.read()
        self.send_response(200)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", len(body))
        self.end_headers()
        self.wfile.write(body)

    def do_OPTIONS(self):
        self.send_response(200)
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Methods", "GET, POST, DELETE, OPTIONS")
        self.send_header("Access-Control-Allow-Headers", "Content-Type")
        self.end_headers()

    def do_GET(self):
        parsed = urlparse(self.path)
        path = parsed.path

        if path == "/" or path == "/index.html":
            self.send_file(os.path.join(os.path.dirname(__file__), "index.html"), "text/html; charset=utf-8")
        elif path == "/api/entries":
            entries = load_entries()
            # newest first
            self.send_json(list(reversed(entries)))
        else:
            self.send_response(404)
            self.end_headers()

    def do_POST(self):
        parsed = urlparse(self.path)
        path = parsed.path

        if path == "/api/entries":
            length = int(self.headers.get("Content-Length", 0))
            body = json.loads(self.rfile.read(length))
            facts = body.get("facts", "").strip()
            truth = body.get("truth", "").strip()

            situation = body.get("situation", "").strip()[:50]
            if not situation and not facts and not truth:
                self.send_json({"error": "Entry is empty"}, 400)
                return

            entries = load_entries()
            entry = {
                "id": datetime.now().strftime("%Y%m%d%H%M%S%f"),
                "timestamp": datetime.now().isoformat(),
                "situation": situation,
                "facts": facts,
                "truth": truth,
            }
            entries.append(entry)
            save_entries(entries)
            self.send_json(entry, 201)
        else:
            self.send_response(404)
            self.end_headers()

    def do_DELETE(self):
        parsed = urlparse(self.path)
        parts = parsed.path.strip("/").split("/")

        if len(parts) == 3 and parts[0] == "api" and parts[1] == "entries":
            entry_id = parts[2]
            entries = load_entries()
            new_entries = [e for e in entries if e["id"] != entry_id]
            if len(new_entries) == len(entries):
                self.send_json({"error": "Not found"}, 404)
                return
            save_entries(new_entries)
            self.send_json({"ok": True})
        else:
            self.send_response(404)
            self.end_headers()


class IPv6Server(HTTPServer):
    address_family = socket.AF_INET6


if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5055))
    on_cloud = bool(os.environ.get("RAILWAY_ENVIRONMENT") or os.environ.get("RENDER"))

    # Ensure data directory exists (important on cloud volumes)
    os.makedirs(DATA_DIR, exist_ok=True)

    print(f"Russell Journal running on port {port}")

    if on_cloud:
        # Cloud: bind to all interfaces; the platform's proxy handles TLS + routing
        HTTPServer(("0.0.0.0", port), Handler).serve_forever()
    else:
        # Local: dual-stack so 'localhost' works whether it resolves to ::1 or 127.0.0.1
        ipv4 = HTTPServer(("0.0.0.0", port), Handler)
        t = threading.Thread(target=ipv4.serve_forever, daemon=True)
        t.start()
        try:
            ipv6 = IPv6Server(("::1", port), Handler)
            ipv6.serve_forever()
        except Exception:
            t.join()
