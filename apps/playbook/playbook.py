#!/usr/bin/env python3
import argparse
import json
import os
import signal
import socket
import subprocess
import sys
import time
from pathlib import Path

import sqlite3
import threading
from flask import Flask, Response, jsonify, render_template, request, g

_generating = threading.Lock()

APP_NAME = "playbook"
DEFAULT_PORT = 3004
DATA_DIR = Path.home() / ".playbook"
DB_PATH = DATA_DIR / "playbook.db"
PID_PATH = DATA_DIR / "playbook.pid"
CONFIG_PATH = DATA_DIR / "config.json"
BASE_DIR = Path(__file__).resolve().parent


# ---------------------------------------------------------------------------
# Data directory & config
# ---------------------------------------------------------------------------

def ensure_data_dir():
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    config = {}
    if CONFIG_PATH.exists():
        try:
            config = json.loads(CONFIG_PATH.read_text())
        except json.JSONDecodeError:
            config = {}
    config.setdefault("port", DEFAULT_PORT)
    config["app_root"] = str(BASE_DIR)
    CONFIG_PATH.write_text(json.dumps(config, indent=2))


# ---------------------------------------------------------------------------
# Database helpers
# ---------------------------------------------------------------------------

def get_db():
    if "db" not in g:
        g.db = sqlite3.connect(DB_PATH)
        g.db.row_factory = sqlite3.Row
    return g.db


def close_db(_exc=None):
    db = g.pop("db", None)
    if db is not None:
        db.close()


SCHEMA_SQL = """
CREATE TABLE IF NOT EXISTS playbooks (
    id               INTEGER PRIMARY KEY AUTOINCREMENT,
    product_name     TEXT NOT NULL,
    product_desc     TEXT NOT NULL,
    customer_segment TEXT NOT NULL,
    desired_outcomes TEXT,
    playbook_md      TEXT NOT NULL,
    created_at       DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP
);
"""


def init_db(conn):
    conn.executescript(SCHEMA_SQL)
    conn.commit()


def ensure_db():
    ensure_data_dir()
    conn = sqlite3.connect(DB_PATH)
    try:
        init_db(conn)
    finally:
        conn.close()


# ---------------------------------------------------------------------------
# Claude prompt
# ---------------------------------------------------------------------------

SYSTEM_PROMPT = (
    "You are an expert Customer Success and Onboarding strategist. You create "
    "detailed, actionable onboarding playbooks for SaaS products. Your playbooks "
    "are structured, specific, and grounded in CS best practices. Output only "
    "valid markdown with no preamble or commentary."
)

USER_PROMPT_TEMPLATE = """\
Create a detailed onboarding playbook for the following product and customer segment.

**Product:** {product_name}
**Product Description:** {product_desc}
**Customer Segment:** {customer_segment}
**Desired Outcomes:** {desired_outcomes}

Generate the playbook in this exact structure:

# Onboarding Playbook: {product_name} — {customer_segment}

## Overview
Brief summary of the onboarding approach tailored to this segment (2-3 sentences).

## Timeline & Milestones
A phased timeline (typically 30/60/90 days) with specific milestones. Use a table:
| Phase | Timeline | Milestone | Success Criteria |

## Kickoff & Welcome
- What happens in the first 24-48 hours after signing
- Welcome email content themes
- Kickoff call agenda items

## Email/Touchpoint Sequence
Numbered sequence of touchpoints with timing, channel (email/call/in-app), subject line, \
and purpose. Include at least 8-10 touchpoints across the onboarding period.

## Check-in Cadence
- Frequency and format of check-in calls
- Standing agenda items
- Escalation triggers

## Success Criteria & Health Signals
- Leading indicators of healthy adoption
- Red flags to watch for
- Metrics to track (with specific thresholds where possible)

## Handoff to Ongoing CS
- Criteria for graduating from onboarding
- What the transition looks like
- Documentation to hand off

Keep the content specific to the product and segment. Avoid generic advice. \
If the product description suggests specific features, reference them in the milestones \
and touchpoints."""


def build_prompt(data):
    return USER_PROMPT_TEMPLATE.format(
        product_name=data["product_name"],
        product_desc=data["product_desc"],
        customer_segment=data["customer_segment"],
        desired_outcomes=data.get("desired_outcomes") or "Successful product adoption and time-to-value",
    )


# ---------------------------------------------------------------------------
# Flask application
# ---------------------------------------------------------------------------

def create_app(prefix=""):
    static_path = prefix + "/static" if prefix else "/static"
    app = Flask(
        __name__,
        static_folder=str(BASE_DIR / "static"),
        static_url_path=static_path,
        template_folder=str(BASE_DIR / "templates"),
    )
    app.config["URL_PREFIX"] = prefix

    @app.context_processor
    def inject_prefix():
        return {"prefix": app.config["URL_PREFIX"]}

    @app.teardown_appcontext
    def teardown_db(exception=None):
        close_db(exception)

    # --- Page routes -------------------------------------------------------

    @app.route(prefix + "/")
    @app.route("/")
    def index():
        return render_template("index.html")

    @app.route(prefix + "/view/<int:playbook_id>")
    @app.route("/view/<int:playbook_id>")
    def view_playbook(playbook_id):
        return render_template("view.html", playbook_id=playbook_id)

    # --- API routes --------------------------------------------------------

    @app.route(prefix + "/api/generate", methods=["POST"])
    @app.route("/api/generate", methods=["POST"])
    def api_generate():
        data = request.get_json(silent=True) or {}

        # Validate required fields
        for field in ("product_name", "product_desc", "customer_segment"):
            if not (data.get(field) or "").strip():
                return jsonify({"error": f"{field} is required"}), 400

        prompt = build_prompt(data)

        def stream():
            if not _generating.acquire(blocking=False):
                yield f"data: {json.dumps({'error': 'A playbook is already being generated. Please wait.'})}\n\n"
                return

            full_prompt = SYSTEM_PROMPT + "\n\n" + prompt

            try:
                import shutil
                claude_bin = shutil.which("claude")
                if not claude_bin:
                    yield f"data: {json.dumps({'error': 'claude CLI not found. Install Claude Code first.'})}\n\n"
                    return

                # Strip CLAUDECODE env var so nested CLI works
                env = {k: v for k, v in os.environ.items() if k != "CLAUDECODE"}
                proc = subprocess.Popen(
                    [claude_bin, "-p", full_prompt, "--output-format", "text"],
                    stdout=subprocess.PIPE,
                    stderr=subprocess.PIPE,
                    text=True,
                    env=env,
                )

                full_text = []
                # Read output in chunks for streaming
                while True:
                    chunk = proc.stdout.read(80)
                    if not chunk:
                        break
                    full_text.append(chunk)
                    yield f"data: {json.dumps({'text': chunk})}\n\n"

                proc.wait()

                if proc.returncode != 0:
                    stderr = proc.stderr.read()
                    yield f"data: {json.dumps({'error': f'Claude CLI error: {stderr}'})}\n\n"
                    return

                # Save to DB
                playbook_md = "".join(full_text)
                if not playbook_md.strip():
                    yield f"data: {json.dumps({'error': 'No output from Claude CLI'})}\n\n"
                    return

                conn = sqlite3.connect(DB_PATH)
                conn.row_factory = sqlite3.Row
                try:
                    cur = conn.execute(
                        "INSERT INTO playbooks (product_name, product_desc, customer_segment, desired_outcomes, playbook_md) VALUES (?, ?, ?, ?, ?)",
                        (data["product_name"].strip(), data["product_desc"].strip(),
                         data["customer_segment"].strip(),
                         (data.get("desired_outcomes") or "").strip(),
                         playbook_md),
                    )
                    conn.commit()
                    playbook_id = cur.lastrowid
                finally:
                    conn.close()

                yield f"data: {json.dumps({'done': True, 'id': playbook_id})}\n\n"

            except Exception as e:
                yield f"data: {json.dumps({'error': str(e)})}\n\n"
            finally:
                _generating.release()

        return Response(stream(), mimetype="text/event-stream",
                        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"})

    @app.route(prefix + "/api/playbooks", methods=["GET"])
    @app.route("/api/playbooks", methods=["GET"])
    def api_playbooks_list():
        ensure_db()
        conn = get_db()
        rows = conn.execute(
            "SELECT id, product_name, customer_segment, created_at FROM playbooks ORDER BY created_at DESC"
        ).fetchall()
        return jsonify({
            "playbooks": [
                {"id": r["id"], "product_name": r["product_name"],
                 "customer_segment": r["customer_segment"], "created_at": r["created_at"]}
                for r in rows
            ]
        })

    @app.route(prefix + "/api/playbooks/<int:playbook_id>", methods=["GET"])
    @app.route("/api/playbooks/<int:playbook_id>", methods=["GET"])
    def api_playbook_get(playbook_id):
        ensure_db()
        conn = get_db()
        row = conn.execute("SELECT * FROM playbooks WHERE id = ?", (playbook_id,)).fetchone()
        if not row:
            return jsonify({"error": "Playbook not found"}), 404
        return jsonify({
            "id": row["id"],
            "product_name": row["product_name"],
            "product_desc": row["product_desc"],
            "customer_segment": row["customer_segment"],
            "desired_outcomes": row["desired_outcomes"],
            "playbook_md": row["playbook_md"],
            "created_at": row["created_at"],
        })

    @app.route(prefix + "/api/playbooks/<int:playbook_id>", methods=["DELETE"])
    @app.route("/api/playbooks/<int:playbook_id>", methods=["DELETE"])
    def api_playbook_delete(playbook_id):
        ensure_db()
        conn = get_db()
        existing = conn.execute("SELECT id FROM playbooks WHERE id = ?", (playbook_id,)).fetchone()
        if not existing:
            return jsonify({"error": "Playbook not found"}), 404
        conn.execute("DELETE FROM playbooks WHERE id = ?", (playbook_id,))
        conn.commit()
        return jsonify({"success": True})

    @app.route("/api/seed", methods=["POST"])
    def api_seed():
        seed_file = BASE_DIR / "sample_data.json"
        if not seed_file.exists():
            return jsonify({"error": "Sample data file not found"}), 404
        db = get_db()
        existing = db.execute("SELECT COUNT(*) FROM playbooks").fetchone()[0]
        if existing > 0:
            return jsonify({"status": "seeded", "count": 0, "message": "already seeded"})
        seed_data = json.loads(seed_file.read_text())
        for item in seed_data:
            db.execute(
                "INSERT INTO playbooks (product_name, product_desc, customer_segment, desired_outcomes, playbook_md) VALUES (?, ?, ?, ?, ?)",
                (item["product_name"], item["product_desc"], item["customer_segment"], item["desired_outcomes"], item["playbook_md"]),
            )
        db.commit()
        return jsonify({"status": "seeded", "count": len(seed_data)})

    return app


# ---------------------------------------------------------------------------
# Server lifecycle CLI
# ---------------------------------------------------------------------------

def is_port_in_use(port):
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.settimeout(0.2)
        return sock.connect_ex(("127.0.0.1", port)) == 0


def wait_for_port(port, timeout=2.0):
    start = time.time()
    while time.time() - start < timeout:
        if is_port_in_use(port):
            return True
        time.sleep(0.1)
    return False


def read_pid():
    if not PID_PATH.exists():
        return None
    try:
        return int(PID_PATH.read_text().strip())
    except ValueError:
        return None


def is_process_running(pid):
    if pid is None:
        return False
    try:
        os.kill(pid, 0)
    except OSError:
        return False
    return True


def command_start(args):
    ensure_db()

    if PID_PATH.exists():
        pid = read_pid()
        if pid and is_process_running(pid):
            print(f"Playbook generator already running (PID {pid}).")
            return 0
        PID_PATH.unlink(missing_ok=True)

    port = args.port or DEFAULT_PORT
    if is_port_in_use(port):
        print(
            f"Port {port} is in use. Stop other process or use '{APP_NAME} start --port XXXX'."
        )
        return 1

    cmd = [sys.executable, str(Path(__file__).resolve()), "serve", "--port", str(port)]
    process = subprocess.Popen(
        cmd,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        start_new_session=True,
    )
    PID_PATH.write_text(str(process.pid))

    wait_for_port(port, timeout=2.0)
    try:
        import webbrowser
        webbrowser.open(f"http://localhost:{port}")
    except Exception:
        print(f"Open http://localhost:{port} in your browser.")

    print(f"Playbook generator running at http://localhost:{port} (use '{APP_NAME} stop' to shut down)")
    return 0


def command_stop(_args):
    pid = read_pid()
    if not pid or not is_process_running(pid):
        print("Playbook generator is not running.")
        PID_PATH.unlink(missing_ok=True)
        return 0
    try:
        os.kill(pid, signal.SIGTERM)
    except OSError:
        print("Unable to stop the playbook generator process.")
        return 1
    PID_PATH.unlink(missing_ok=True)
    print("Playbook generator stopped.")
    return 0


def command_status(_args):
    pid = read_pid()
    if pid and is_process_running(pid):
        print(f"Playbook generator running (PID {pid}).")
        return 0
    print("Playbook generator is not running.")
    return 1


def command_serve(args):
    ensure_db()
    prefix = getattr(args, "prefix", "") or ""
    app = create_app(prefix=prefix)
    port = args.port or DEFAULT_PORT
    app.run(host="127.0.0.1", port=port, debug=False, threaded=True)
    return 0


# ---------------------------------------------------------------------------
# Argument parser
# ---------------------------------------------------------------------------

def build_parser():
    parser = argparse.ArgumentParser(prog=APP_NAME)
    subparsers = parser.add_subparsers(dest="command")

    start_parser = subparsers.add_parser("start", help="Start the playbook generator server")
    start_parser.add_argument("--port", type=int, default=None, help="Port to bind")

    subparsers.add_parser("stop", help="Stop the playbook generator server")
    subparsers.add_parser("status", help="Show server status")

    serve_parser = subparsers.add_parser("serve")
    serve_parser.add_argument("--port", type=int, default=None)
    serve_parser.add_argument("--prefix", type=str, default="", help="URL prefix for gateway mode")

    return parser


def main():
    parser = build_parser()
    args = parser.parse_args()

    if args.command == "start":
        return command_start(args)
    if args.command == "stop":
        return command_stop(args)
    if args.command == "status":
        return command_status(args)
    if args.command == "serve":
        return command_serve(args)

    parser.print_help()
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
