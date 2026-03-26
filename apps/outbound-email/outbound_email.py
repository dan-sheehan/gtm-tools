#!/usr/bin/env python3
import argparse
import json
import os
import re
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

APP_NAME = "outbound-email"
DEFAULT_PORT = 3008
DATA_DIR = Path.home() / ".outbound-email"
DB_PATH = DATA_DIR / "outbound-email.db"
PID_PATH = DATA_DIR / "outbound-email.pid"
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
CREATE TABLE IF NOT EXISTS sequences (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    company_url     TEXT NOT NULL,
    company_name    TEXT,
    prospect_name   TEXT,
    prospect_title  TEXT,
    department      TEXT,
    emails_json     TEXT,
    created_at      DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP
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
    "You are a 20-year expert in business development and cold outreach. "
    "You specialize in writing highly effective cold prospecting email sequences. "
    "You write all outreach from the perspective of the user's company. "
    "You NEVER fabricate information. You only use information from verifiable public sources: "
    "company websites, earnings calls, 10-K filings, investor presentations, blogs, product updates, "
    "leadership interviews, podcasts, press releases, and job postings. "
    "If you cannot find verifiable information, say so. Do not guess. "
    "Output ONLY valid JSON - no preamble, no markdown fences, no commentary."
)

USER_PROMPT_TEMPLATE = """\
Research {company_url} to understand how the company is using or planning to use AI. \
Pull from verifiable public sources only: website, earnings calls, 10-K filings, investor presentations, \
blogs, product updates, leadership interviews, podcasts, press releases, job postings.

{prospect_context}

Then generate 4 cold prospecting emails written as outreach from the user's company. \
Tailor the value propositions based on the prospect's specific challenges and AI usage.

Email guidelines:
- Simple plain language (approximately 3rd-grade reading level)
- Provide value in every email
- Avoid marketing fluff, filler, adjectives, adverbs, cliches, jargon, hashtags, emojis, semicolons
- Avoid competitive attacks
- Be highly concise

The 4 emails should be:
1. INITIAL: Short, clear, mirrors the prospect's own words where possible, under 100 words, gets to the point fast
2. FOLLOW_UP_1: Automated reply to email 1, adds a small additional insight
3. FOLLOW_UP_2: Semi-automated, builds slightly more context and value
4. BREAKUP: Soft breakup that still provides value, no guilt-tripping

Example style for email 1:
Subject: [topic relevant to their AI initiative]
Body: Hi [Name], saw [specific thing they are doing with AI]. Most teams doing this hit [specific problem]. We help by [one value prop]. Worth a quick look?

Return JSON:
{{"company_name":"...","ai_usage_summary":"brief 2-3 sentence summary of their AI usage/plans","emails":[{{"subject":"...","body":"...","type":"initial"}},{{"subject":"...","body":"...","type":"follow_up_1"}},{{"subject":"...","body":"...","type":"follow_up_2"}},{{"subject":"...","body":"...","type":"breakup"}}]}}
"""


def build_prompt(data):
    prospect_parts = []
    if data.get("prospect_name", "").strip():
        prospect_parts.append(f"The target prospect is {data['prospect_name'].strip()}.")
    if data.get("prospect_title", "").strip():
        prospect_parts.append(f"Their title is {data['prospect_title'].strip()}.")
    if data.get("department", "").strip():
        prospect_parts.append(f"They work in the {data['department'].strip()} department.")

    if prospect_parts:
        prospect_context = " ".join(prospect_parts) + " Tailor the emails to this audience."
    else:
        prospect_context = "No specific prospect provided. Write emails to a general senior leader."

    return USER_PROMPT_TEMPLATE.format(
        company_url=data["company_url"],
        prospect_context=prospect_context,
    )


def parse_json_response(text):
    """Try to extract JSON from Claude's response, handling markdown fences."""
    text = text.strip()
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        pass
    match = re.search(r"```(?:json)?\s*\n?(.*?)\n?```", text, re.DOTALL)
    if match:
        try:
            return json.loads(match.group(1))
        except json.JSONDecodeError:
            pass
    match = re.search(r"\{.*\}", text, re.DOTALL)
    if match:
        try:
            return json.loads(match.group(0))
        except json.JSONDecodeError:
            pass
    return None


def result_to_markdown(data):
    """Convert structured JSON result to markdown."""
    lines = []
    company_name = data.get("company_name", "Unknown")
    ai_summary = data.get("ai_usage_summary", "")
    emails = data.get("emails", [])

    lines.append(f"# Outbound Email Sequence: {company_name}")
    lines.append("")
    if ai_summary:
        lines.append(f"**AI Usage:** {ai_summary}")
        lines.append("")

    type_labels = {
        "initial": "Email 1 - Initial",
        "follow_up_1": "Email 2 - Follow-up 1",
        "follow_up_2": "Email 3 - Follow-up 2",
        "breakup": "Email 4 - Breakup",
    }

    for i, email in enumerate(emails):
        label = type_labels.get(email.get("type", ""), f"Email {i + 1}")
        lines.append(f"## {label}")
        lines.append(f"**Subject:** {email.get('subject', '')}")
        lines.append("")
        lines.append(email.get("body", ""))
        lines.append("")
        lines.append("---")
        lines.append("")

    return "\n".join(lines)


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

    # --- API routes --------------------------------------------------------

    @app.route(prefix + "/api/generate", methods=["POST"])
    @app.route("/api/generate", methods=["POST"])
    def api_generate():
        data = request.get_json(silent=True) or {}

        if not (data.get("company_url") or "").strip():
            return jsonify({"error": "company_url is required"}), 400

        prompt = build_prompt(data)

        def stream():
            if not _generating.acquire(blocking=False):
                yield f"data: {json.dumps({'error': 'A generation request is already running. Please wait.'})}\n\n"
                return

            full_prompt = SYSTEM_PROMPT + "\n\n" + prompt

            try:
                import shutil
                claude_bin = shutil.which("claude")
                if not claude_bin:
                    yield f"data: {json.dumps({'error': 'claude CLI not found. Install Claude Code first.'})}\n\n"
                    return

                yield f"data: {json.dumps({'status': 'Researching company and generating emails...'})}\n\n"

                result = subprocess.run(
                    [
                        claude_bin, "-p", full_prompt,
                        "--output-format", "text",
                        "--model", "claude-sonnet-4-6",
                        "--allowedTools", "WebSearch,WebFetch",
                    ],
                    capture_output=True,
                    text=True,
                    env={k: v for k, v in os.environ.items() if k != "CLAUDECODE"},
                    cwd=str(Path.home()),
                    stdin=subprocess.DEVNULL,
                    timeout=120,
                )

                if result.returncode != 0:
                    err_detail = result.stderr.strip() or result.stdout.strip() or "(no output)"
                    yield f"data: {json.dumps({'error': f'Claude CLI error (exit {result.returncode}): {err_detail}'})}\n\n"
                    return

                raw_text = result.stdout
                if not raw_text.strip():
                    yield f"data: {json.dumps({'error': 'No output from Claude CLI'})}\n\n"
                    return

                parsed = parse_json_response(raw_text)
                if not parsed:
                    yield f"data: {json.dumps({'error': 'Could not parse results as JSON', 'raw': raw_text})}\n\n"
                    return

                # Save to DB
                company_name = parsed.get("company_name", "")
                emails_json = json.dumps(parsed.get("emails", []))
                conn = sqlite3.connect(DB_PATH)
                conn.row_factory = sqlite3.Row
                try:
                    cur = conn.execute(
                        "INSERT INTO sequences (company_url, company_name, prospect_name, prospect_title, department, emails_json) VALUES (?, ?, ?, ?, ?, ?)",
                        (
                            data["company_url"].strip(),
                            company_name,
                            (data.get("prospect_name") or "").strip() or None,
                            (data.get("prospect_title") or "").strip() or None,
                            (data.get("department") or "").strip() or None,
                            emails_json,
                        ),
                    )
                    conn.commit()
                    seq_id = cur.lastrowid
                finally:
                    conn.close()

                yield f"data: {json.dumps({'done': True, 'id': seq_id, 'result': parsed})}\n\n"

            except subprocess.TimeoutExpired:
                yield f"data: {json.dumps({'error': 'Generation timed out after 2 minutes. Try again.'})}\n\n"
            except Exception as e:
                yield f"data: {json.dumps({'error': str(e)})}\n\n"
            finally:
                _generating.release()

        return Response(stream(), mimetype="text/event-stream",
                        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"})

    @app.route(prefix + "/api/sequences", methods=["GET"])
    @app.route("/api/sequences", methods=["GET"])
    def api_sequences_list():
        ensure_db()
        conn = get_db()
        rows = conn.execute(
            "SELECT id, company_url, company_name, prospect_name, prospect_title, department, created_at FROM sequences ORDER BY created_at DESC"
        ).fetchall()
        return jsonify({
            "sequences": [
                {
                    "id": r["id"],
                    "company_url": r["company_url"],
                    "company_name": r["company_name"],
                    "prospect_name": r["prospect_name"],
                    "prospect_title": r["prospect_title"],
                    "department": r["department"],
                    "created_at": r["created_at"],
                }
                for r in rows
            ]
        })

    @app.route(prefix + "/api/sequences/<int:seq_id>", methods=["GET"])
    @app.route("/api/sequences/<int:seq_id>", methods=["GET"])
    def api_sequence_get(seq_id):
        ensure_db()
        conn = get_db()
        row = conn.execute("SELECT * FROM sequences WHERE id = ?", (seq_id,)).fetchone()
        if not row:
            return jsonify({"error": "Sequence not found"}), 404
        return jsonify({
            "id": row["id"],
            "company_url": row["company_url"],
            "company_name": row["company_name"],
            "prospect_name": row["prospect_name"],
            "prospect_title": row["prospect_title"],
            "department": row["department"],
            "emails": json.loads(row["emails_json"]) if row["emails_json"] else [],
            "created_at": row["created_at"],
        })

    @app.route(prefix + "/api/sequences/<int:seq_id>", methods=["PUT"])
    @app.route("/api/sequences/<int:seq_id>", methods=["PUT"])
    def api_sequence_update(seq_id):
        ensure_db()
        conn = get_db()
        existing = conn.execute("SELECT id FROM sequences WHERE id = ?", (seq_id,)).fetchone()
        if not existing:
            return jsonify({"error": "Sequence not found"}), 404

        data = request.get_json(silent=True) or {}
        updates = []
        params = []

        if "emails" in data:
            updates.append("emails_json = ?")
            params.append(json.dumps(data["emails"]))
        if "company_name" in data:
            updates.append("company_name = ?")
            params.append(data["company_name"])
        if "prospect_name" in data:
            updates.append("prospect_name = ?")
            params.append(data["prospect_name"])
        if "prospect_title" in data:
            updates.append("prospect_title = ?")
            params.append(data["prospect_title"])
        if "department" in data:
            updates.append("department = ?")
            params.append(data["department"])

        if updates:
            params.append(seq_id)
            conn.execute(f"UPDATE sequences SET {', '.join(updates)} WHERE id = ?", params)
            conn.commit()

        return jsonify({"success": True})

    @app.route(prefix + "/api/sequences/<int:seq_id>", methods=["DELETE"])
    @app.route("/api/sequences/<int:seq_id>", methods=["DELETE"])
    def api_sequence_delete(seq_id):
        ensure_db()
        conn = get_db()
        existing = conn.execute("SELECT id FROM sequences WHERE id = ?", (seq_id,)).fetchone()
        if not existing:
            return jsonify({"error": "Sequence not found"}), 404
        conn.execute("DELETE FROM sequences WHERE id = ?", (seq_id,))
        conn.commit()
        return jsonify({"success": True})

    @app.route(prefix + "/api/sequences/<int:seq_id>/export", methods=["GET"])
    @app.route("/api/sequences/<int:seq_id>/export", methods=["GET"])
    def api_sequence_export(seq_id):
        ensure_db()
        conn = get_db()
        row = conn.execute("SELECT * FROM sequences WHERE id = ?", (seq_id,)).fetchone()
        if not row:
            return jsonify({"error": "Sequence not found"}), 404
        emails = json.loads(row["emails_json"]) if row["emails_json"] else []
        parsed = {
            "company_name": row["company_name"] or "unknown",
            "emails": emails,
        }
        markdown = result_to_markdown(parsed)
        filename = f"outbound-emails-{row['company_name'] or 'unknown'}.md"
        filename = re.sub(r"[^\w\s.-]", "", filename).replace(" ", "-").lower()
        return Response(
            markdown,
            mimetype="text/markdown",
            headers={"Content-Disposition": f"attachment; filename={filename}"},
        )

    @app.route("/api/seed", methods=["POST"])
    def api_seed():
        seed_file = BASE_DIR / "sample_data.json"
        if not seed_file.exists():
            return jsonify({"error": "Sample data file not found"}), 404
        db = get_db()
        existing = db.execute("SELECT COUNT(*) FROM sequences").fetchone()[0]
        if existing > 0:
            return jsonify({"status": "seeded", "count": 0, "message": "already seeded"})
        seed_data = json.loads(seed_file.read_text())
        for item in seed_data:
            db.execute(
                "INSERT INTO sequences (company_url, company_name, prospect_name, prospect_title, department, emails_json) VALUES (?, ?, ?, ?, ?, ?)",
                (item["company_url"], item["company_name"], item["prospect_name"], item["prospect_title"], item["department"], json.dumps(item["emails"])),
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
            print(f"Outbound email helper already running (PID {pid}).")
            return 0
        PID_PATH.unlink(missing_ok=True)

    port = args.port or DEFAULT_PORT
    if is_port_in_use(port):
        print(f"Port {port} is in use. Stop other process or use '{APP_NAME} start --port XXXX'.")
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

    print(f"Outbound email helper running at http://localhost:{port} (use '{APP_NAME} stop' to shut down)")
    return 0


def command_stop(_args):
    pid = read_pid()
    if not pid or not is_process_running(pid):
        print("Outbound email helper is not running.")
        PID_PATH.unlink(missing_ok=True)
        return 0
    try:
        os.kill(pid, signal.SIGTERM)
    except OSError:
        print("Unable to stop the outbound email helper process.")
        return 1
    PID_PATH.unlink(missing_ok=True)
    print("Outbound email helper stopped.")
    return 0


def command_status(_args):
    pid = read_pid()
    if pid and is_process_running(pid):
        print(f"Outbound email helper running (PID {pid}).")
        return 0
    print("Outbound email helper is not running.")
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

    start_parser = subparsers.add_parser("start", help="Start the outbound email helper server")
    start_parser.add_argument("--port", type=int, default=None, help="Port to bind")

    subparsers.add_parser("stop", help="Stop the outbound email helper server")
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
