import json
import os
import socket
import threading
from datetime import datetime
from http.server import HTTPServer, BaseHTTPRequestHandler
from urllib.parse import urlparse

# Load .env file if present (local dev only — never committed to git)
_env_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), ".env")
if os.path.exists(_env_path):
    with open(_env_path) as _f:
        for _line in _f:
            _line = _line.strip()
            if _line and not _line.startswith("#") and "=" in _line:
                _k, _, _v = _line.partition("=")
                os.environ.setdefault(_k.strip(), _v.strip())

# ── Storage ───────────────────────────────────────────────────────────────────
# On Railway: DATABASE_URL is set automatically when you add a Postgres addon.
# Locally:    falls back to a JSON file in the project directory.

DATABASE_URL = os.environ.get("DATABASE_URL")

_base = os.path.dirname(os.path.abspath(__file__))
DATA_DIR     = os.environ.get("DATA_DIR", _base)
ENTRIES_FILE = os.path.join(DATA_DIR, "entries.json")


def _get_conn():
    import psycopg2
    return psycopg2.connect(DATABASE_URL)


def _init_db():
    """Create the entries table if it doesn't exist yet."""
    with _get_conn() as conn:
        with conn.cursor() as cur:
            cur.execute("""
                CREATE TABLE IF NOT EXISTS entries (
                    id        TEXT PRIMARY KEY,
                    timestamp TEXT NOT NULL,
                    situation TEXT,
                    facts     TEXT,
                    truth     TEXT
                )
            """)


def load_entries():
    if DATABASE_URL:
        with _get_conn() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    "SELECT id, timestamp, situation, facts, truth "
                    "FROM entries ORDER BY timestamp ASC"
                )
                return [
                    {"id": r[0], "timestamp": r[1],
                     "situation": r[2] or "", "facts": r[3] or "", "truth": r[4] or ""}
                    for r in cur.fetchall()
                ]
    else:
        if not os.path.exists(ENTRIES_FILE):
            return []
        with open(ENTRIES_FILE, "r", encoding="utf-8") as f:
            return json.load(f)


def create_entry(entry):
    if DATABASE_URL:
        with _get_conn() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    "INSERT INTO entries (id, timestamp, situation, facts, truth) "
                    "VALUES (%s, %s, %s, %s, %s)",
                    (entry["id"], entry["timestamp"],
                     entry["situation"], entry["facts"], entry["truth"])
                )
    else:
        entries = load_entries()
        entries.append(entry)
        os.makedirs(DATA_DIR, exist_ok=True)
        with open(ENTRIES_FILE, "w", encoding="utf-8") as f:
            json.dump(entries, f, indent=2, ensure_ascii=False)


def remove_entry(entry_id):
    if DATABASE_URL:
        with _get_conn() as conn:
            with conn.cursor() as cur:
                cur.execute("DELETE FROM entries WHERE id = %s", (entry_id,))
                return cur.rowcount > 0
    else:
        entries = load_entries()
        new_entries = [e for e in entries if e["id"] != entry_id]
        if len(new_entries) == len(entries):
            return False
        with open(ENTRIES_FILE, "w", encoding="utf-8") as f:
            json.dump(new_entries, f, indent=2, ensure_ascii=False)
        return True


# ── Claude suggestion ─────────────────────────────────────────────────────────

SUGGEST_SYSTEM = (
    "You are a clear-headed, unsentimental advisor. "
    "Your job is to apply one principle: strip away emotion and state only what the facts objectively show.\n\n"
    "You will be given a situation (the problem as named) and a list of facts. Do the following two things:\n\n"
    "First — state what the facts actually demonstrate. Be direct and plain. "
    "Do not reassure, speculate beyond what is stated, or use therapeutic language. "
    "If the facts are thin or vague, say so as part of your conclusion. "
    "If they show no real problem, say so plainly. "
    "If they show a genuine problem, say that plainly too. "
    "2-3 sentences, no more.\n\n"
    "Second — suggest possible next steps, grounded only in what the facts support. "
    "If there is no real problem, one step is enough (e.g. 'Accept the situation and get on with your day'). "
    "If there is a real problem, offer up to three concrete steps. "
    "If the facts are too vague to act on meaningfully, say so.\n\n"
    "Return your response as JSON with exactly two fields: "
    "\"truth\" (string, 2-3 sentences) and \"steps\" (array of strings, 0-3 items). "
    "Return only the JSON object — no markdown, no code fences, no other text."
)


def get_suggestion(situation, facts):
    import anthropic
    client = anthropic.Anthropic(api_key=os.environ.get("ANTHROPIC_API_KEY"))
    user_msg = f"Situation: {situation}\nFacts: {facts}\nWhat do the facts bear out?"
    msg = client.messages.create(
        model="claude-sonnet-4-5",
        max_tokens=400,
        system=SUGGEST_SYSTEM,
        messages=[{"role": "user", "content": user_msg}]
    )
    raw = msg.content[0].text.strip()
    try:
        return json.loads(raw)
    except json.JSONDecodeError:
        return {"truth": raw, "steps": []}


# ── HTTP handler ──────────────────────────────────────────────────────────────

class Handler(BaseHTTPRequestHandler):
    def log_message(self, format, *args):
        pass

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
        path = urlparse(self.path).path
        if path in ("/", "/index.html"):
            self.send_file(
                os.path.join(os.path.dirname(os.path.abspath(__file__)), "index.html"),
                "text/html; charset=utf-8"
            )
        elif path == "/api/entries":
            self.send_json(list(reversed(load_entries())))
        else:
            self.send_response(404)
            self.end_headers()

    def do_POST(self):
        path = urlparse(self.path).path

        if path == "/api/suggest":
            body = json.loads(self.rfile.read(int(self.headers.get("Content-Length", 0))))
            situation = body.get("situation", "").strip()
            facts     = body.get("facts", "").strip()
            if not facts:
                self.send_json({"error": "Add some facts first."}, 400)
                return
            if not os.environ.get("ANTHROPIC_API_KEY"):
                self.send_json({"error": "ANTHROPIC_API_KEY not configured."}, 500)
                return
            try:
                self.send_json(get_suggestion(situation, facts))
            except Exception as e:
                self.send_json({"error": str(e)}, 500)
            return

        if path != "/api/entries":
            self.send_response(404)
            self.end_headers()
            return

        body = json.loads(self.rfile.read(int(self.headers.get("Content-Length", 0))))
        situation = body.get("situation", "").strip()[:50]
        facts     = body.get("facts", "").strip()
        truth     = body.get("truth", "").strip()

        if not situation and not facts and not truth:
            self.send_json({"error": "Entry is empty"}, 400)
            return

        entry = {
            "id":        datetime.now().strftime("%Y%m%d%H%M%S%f"),
            "timestamp": datetime.now().isoformat(),
            "situation": situation,
            "facts":     facts,
            "truth":     truth,
        }
        create_entry(entry)
        self.send_json(entry, 201)

    def do_DELETE(self):
        parts = urlparse(self.path).path.strip("/").split("/")
        if len(parts) == 3 and parts[0] == "api" and parts[1] == "entries":
            found = remove_entry(parts[2])
            self.send_json({"ok": True} if found else {"error": "Not found"},
                           200 if found else 404)
        else:
            self.send_response(404)
            self.end_headers()


# ── Server startup ────────────────────────────────────────────────────────────

class IPv6Server(HTTPServer):
    address_family = socket.AF_INET6


if __name__ == "__main__":
    port      = int(os.environ.get("PORT", 5055))
    on_cloud  = bool(os.environ.get("RAILWAY_ENVIRONMENT") or os.environ.get("RENDER"))

    if DATABASE_URL:
        _init_db()

    print(f"Russell Journal running on port {port}")

    if on_cloud:
        HTTPServer(("0.0.0.0", port), Handler).serve_forever()
    else:
        ipv4 = HTTPServer(("0.0.0.0", port), Handler)
        t = threading.Thread(target=ipv4.serve_forever, daemon=True)
        t.start()
        try:
            ipv6 = IPv6Server(("::1", port), Handler)
            ipv6.serve_forever()
        except Exception:
            t.join()
