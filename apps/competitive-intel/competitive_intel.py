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

_researching = threading.Lock()

APP_NAME = "competitive-intel"
DEFAULT_PORT = 3006
DATA_DIR = Path.home() / ".competitive-intel"
DB_PATH = DATA_DIR / "competitive-intel.db"
PID_PATH = DATA_DIR / "competitive-intel.pid"
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
CREATE TABLE IF NOT EXISTS analyses (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    company_name    TEXT NOT NULL,
    analysis_type   TEXT NOT NULL DEFAULT 'general',
    competitors     TEXT,
    result_markdown TEXT,
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
    "You are an expert competitive intelligence analyst. "
    "You deliver professional, crisp, executive-level analysis. "
    "Use web search to gather current data — do NOT guess or fabricate information. "
    "If something is not available, say 'Not available'. "
    "Focus on insights, not just facts. Always explain why something matters. "
    "Output ONLY valid JSON — no preamble, no markdown fences, no commentary."
)

USER_PROMPT_TEMPLATE = """\
Research {company_name} and provide a {analysis_type} competitive intelligence analysis.

Return JSON:
{{"company":"{company_name}","summary":"2-3 sentence executive summary of the company and its competitive position","updates":[{{"title":"...","detail":"...","why_it_matters":"..."}},{{"title":"...","detail":"...","why_it_matters":"..."}}],"positioning":"1-2 sentences on how the company positions itself in the market","strategic_actions":["Actionable recommendation 1","Actionable recommendation 2","Actionable recommendation 3"]}}

Rules:
- Provide 3-5 updates covering: product releases, strategy shifts, hiring trends, pricing changes, partnerships
- Each update must include a "why_it_matters" insight
- Strategic actions should be specific and actionable
- Use "Not available" for anything you cannot verify
- Do NOT guess or fabricate data"""


def build_prompt(data):
    return USER_PROMPT_TEMPLATE.format(
        company_name=data["company_name"],
        analysis_type=data.get("analysis_type", "general"),
    )


def parse_json_response(text):
    """Try to extract JSON from Claude's response, handling markdown fences."""
    text = text.strip()
    # Try direct parse
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        pass
    # Try extracting from code fences
    match = re.search(r"```(?:json)?\s*\n?(.*?)\n?```", text, re.DOTALL)
    if match:
        try:
            return json.loads(match.group(1))
        except json.JSONDecodeError:
            pass
    # Try finding first { ... } block
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
    lines.append(f"# Competitive Intelligence: {data.get('company', 'Unknown')}")
    lines.append("")

    lines.append("## Summary")
    lines.append(data.get("summary", "Not available"))
    lines.append("")

    lines.append("## Key Updates")
    for u in data.get("updates", []):
        lines.append(f"### {u.get('title', 'Update')}")
        lines.append(u.get("detail", ""))
        lines.append(f"**Why it matters:** {u.get('why_it_matters', 'Not available')}")
        lines.append("")

    lines.append("## Positioning")
    lines.append(data.get("positioning", "Not available"))
    lines.append("")

    lines.append("## Strategic Actions")
    for a in data.get("strategic_actions", []):
        lines.append(f"- {a}")

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

    @app.route(prefix + "/api/analyze", methods=["POST"])
    @app.route("/api/analyze", methods=["POST"])
    def api_analyze():
        data = request.get_json(silent=True) or {}

        if not (data.get("company_name") or "").strip():
            return jsonify({"error": "company_name is required"}), 400

        prompt = build_prompt(data)

        def stream():
            if not _researching.acquire(blocking=False):
                yield f"data: {json.dumps({'error': 'An analysis is already running. Please wait.'})}\n\n"
                return

            full_prompt = SYSTEM_PROMPT + "\n\n" + prompt

            try:
                import shutil
                claude_bin = shutil.which("claude")
                if not claude_bin:
                    yield f"data: {json.dumps({'error': 'claude CLI not found. Install Claude Code first.'})}\n\n"
                    return

                env = {k: v for k, v in os.environ.items() if k != "CLAUDECODE"}

                yield f"data: {json.dumps({'status': 'Researching competitive intelligence...'})}\n\n"

                result = subprocess.run(
                    [
                        claude_bin, "-p", full_prompt,
                        "--output-format", "text",
                        "--model", "claude-sonnet-4-6",
                        "--allowedTools", "WebSearch,WebFetch",
                    ],
                    capture_output=True,
                    text=True,
                    env=env,
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

                # Parse the JSON response
                parsed = parse_json_response(raw_text)
                if not parsed:
                    yield f"data: {json.dumps({'error': 'Could not parse results as JSON', 'raw': raw_text})}\n\n"
                    return

                # Save to DB
                markdown = result_to_markdown(parsed)
                conn = sqlite3.connect(DB_PATH)
                conn.row_factory = sqlite3.Row
                try:
                    cur = conn.execute(
                        "INSERT INTO analyses (company_name, analysis_type, competitors, result_markdown) VALUES (?, ?, ?, ?)",
                        (
                            data["company_name"].strip(),
                            (data.get("analysis_type") or "general").strip(),
                            json.dumps(data.get("competitors", [])),
                            markdown,
                        ),
                    )
                    conn.commit()
                    analysis_id = cur.lastrowid
                finally:
                    conn.close()

                yield f"data: {json.dumps({'done': True, 'id': analysis_id, 'result': parsed})}\n\n"

            except subprocess.TimeoutExpired:
                yield f"data: {json.dumps({'error': 'Analysis timed out after 2 minutes. Try again.'})}\n\n"
            except Exception as e:
                yield f"data: {json.dumps({'error': str(e)})}\n\n"
            finally:
                _researching.release()

        return Response(stream(), mimetype="text/event-stream",
                        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"})

    @app.route(prefix + "/api/analyses", methods=["GET"])
    @app.route("/api/analyses", methods=["GET"])
    def api_analyses_list():
        ensure_db()
        conn = get_db()
        rows = conn.execute(
            "SELECT id, company_name, analysis_type, created_at FROM analyses ORDER BY created_at DESC"
        ).fetchall()
        return jsonify({
            "analyses": [
                {
                    "id": r["id"],
                    "company_name": r["company_name"],
                    "analysis_type": r["analysis_type"],
                    "created_at": r["created_at"],
                }
                for r in rows
            ]
        })

    @app.route(prefix + "/api/analyses/<int:analysis_id>", methods=["GET"])
    @app.route("/api/analyses/<int:analysis_id>", methods=["GET"])
    def api_analysis_get(analysis_id):
        ensure_db()
        conn = get_db()
        row = conn.execute("SELECT * FROM analyses WHERE id = ?", (analysis_id,)).fetchone()
        if not row:
            return jsonify({"error": "Analysis not found"}), 404
        return jsonify({
            "id": row["id"],
            "company_name": row["company_name"],
            "analysis_type": row["analysis_type"],
            "competitors": json.loads(row["competitors"]) if row["competitors"] else [],
            "result_markdown": row["result_markdown"],
            "created_at": row["created_at"],
        })

    @app.route(prefix + "/api/analyses/<int:analysis_id>", methods=["PUT"])
    @app.route("/api/analyses/<int:analysis_id>", methods=["PUT"])
    def api_analysis_update(analysis_id):
        ensure_db()
        conn = get_db()
        existing = conn.execute("SELECT id FROM analyses WHERE id = ?", (analysis_id,)).fetchone()
        if not existing:
            return jsonify({"error": "Analysis not found"}), 404

        data = request.get_json(silent=True) or {}
        updates = []
        params = []

        if "company_name" in data:
            updates.append("company_name = ?")
            params.append(data["company_name"])
        if "result_markdown" in data:
            updates.append("result_markdown = ?")
            params.append(data["result_markdown"])

        if updates:
            params.append(analysis_id)
            conn.execute(f"UPDATE analyses SET {', '.join(updates)} WHERE id = ?", params)
            conn.commit()

        return jsonify({"success": True})

    @app.route(prefix + "/api/analyses/<int:analysis_id>", methods=["DELETE"])
    @app.route("/api/analyses/<int:analysis_id>", methods=["DELETE"])
    def api_analysis_delete(analysis_id):
        ensure_db()
        conn = get_db()
        existing = conn.execute("SELECT id FROM analyses WHERE id = ?", (analysis_id,)).fetchone()
        if not existing:
            return jsonify({"error": "Analysis not found"}), 404
        conn.execute("DELETE FROM analyses WHERE id = ?", (analysis_id,))
        conn.commit()
        return jsonify({"success": True})

    @app.route(prefix + "/api/analyses/<int:analysis_id>/export", methods=["GET"])
    @app.route("/api/analyses/<int:analysis_id>/export", methods=["GET"])
    def api_analysis_export(analysis_id):
        ensure_db()
        conn = get_db()
        row = conn.execute("SELECT * FROM analyses WHERE id = ?", (analysis_id,)).fetchone()
        if not row:
            return jsonify({"error": "Analysis not found"}), 404
        filename = f"competitive-intel-{row['company_name']}-{row['analysis_type']}.md"
        filename = re.sub(r"[^\w\s.-]", "", filename).replace(" ", "-").lower()
        return Response(
            row["result_markdown"],
            mimetype="text/markdown",
            headers={"Content-Disposition": f"attachment; filename={filename}"},
        )

    @app.route("/api/seed", methods=["POST"])
    def api_seed():
        seed_file = BASE_DIR / "sample_data.json"
        if not seed_file.exists():
            return jsonify({"error": "Sample data file not found"}), 404
        db = get_db()
        existing = db.execute("SELECT COUNT(*) FROM analyses").fetchone()[0]
        if existing > 0:
            return jsonify({"status": "seeded", "count": 0, "message": "already seeded"})
        seed_data = json.loads(seed_file.read_text())
        for item in seed_data:
            db.execute(
                "INSERT INTO analyses (company_name, analysis_type, competitors, result_markdown) VALUES (?, ?, ?, ?)",
                (item["company_name"], item["analysis_type"], json.dumps(item["competitors"]), item["result_markdown"]),
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
            print(f"Competitive Intelligence already running (PID {pid}).")
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

    print(f"Competitive Intelligence running at http://localhost:{port} (use '{APP_NAME} stop' to shut down)")
    return 0


def command_stop(_args):
    pid = read_pid()
    if not pid or not is_process_running(pid):
        print("Competitive Intelligence is not running.")
        PID_PATH.unlink(missing_ok=True)
        return 0
    try:
        os.kill(pid, signal.SIGTERM)
    except OSError:
        print("Unable to stop the Competitive Intelligence process.")
        return 1
    PID_PATH.unlink(missing_ok=True)
    print("Competitive Intelligence stopped.")
    return 0


def command_status(_args):
    pid = read_pid()
    if pid and is_process_running(pid):
        print(f"Competitive Intelligence running (PID {pid}).")
        return 0
    print("Competitive Intelligence is not running.")
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

    start_parser = subparsers.add_parser("start", help="Start the Competitive Intelligence server")
    start_parser.add_argument("--port", type=int, default=None, help="Port to bind")

    subparsers.add_parser("stop", help="Stop the Competitive Intelligence server")
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
