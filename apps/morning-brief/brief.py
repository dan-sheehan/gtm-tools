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

from flask import Flask, jsonify, render_template

APP_NAME = "morning-brief"
DEFAULT_PORT = 3003
DATA_DIR = Path.home() / ".morning-brief"
JSON_PATH = DATA_DIR / "latest.json"
PID_PATH = DATA_DIR / "morning-brief.pid"
BASE_DIR = Path(__file__).resolve().parent
FETCH_SCRIPT = BASE_DIR / "fetch.sh"


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def ensure_data_dir():
    DATA_DIR.mkdir(parents=True, exist_ok=True)


def load_brief():
    """Load the latest brief JSON, returning a fallback on any error."""
    if not JSON_PATH.exists():
        return {"error": "No brief data yet. Run fetch.sh to generate.", "generated_at": None}
    try:
        return json.loads(JSON_PATH.read_text())
    except (json.JSONDecodeError, OSError):
        return {"error": "Failed to read brief data.", "generated_at": None}


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

    @app.route(prefix + "/")
    def index():
        return render_template("index.html")

    @app.route(prefix + "/api/brief", methods=["GET"])
    def api_brief():
        return jsonify(load_brief())

    @app.route(prefix + "/api/refresh", methods=["POST"])
    def api_refresh():
        try:
            subprocess.Popen(
                ["bash", str(FETCH_SCRIPT)],
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                start_new_session=True,
            )
            return jsonify({"status": "started"})
        except OSError as e:
            return jsonify({"status": "error", "message": str(e)}), 500

    @app.route(prefix + "/api/seed", methods=["POST"])
    def api_seed():
        seed_file = BASE_DIR / "sample_data.json"
        if not seed_file.exists():
            return jsonify({"error": "Sample data file not found"}), 404
        if JSON_PATH.exists():
            try:
                existing = json.loads(JSON_PATH.read_text())
                if existing.get("generated_at") and not existing.get("error"):
                    return jsonify({"status": "seeded", "count": 0, "message": "already seeded"})
            except (json.JSONDecodeError, OSError):
                pass
        ensure_data_dir()
        import shutil
        shutil.copy2(seed_file, JSON_PATH)
        return jsonify({"status": "seeded", "count": 1})

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
    ensure_data_dir()
    if PID_PATH.exists():
        pid = read_pid()
        if pid and is_process_running(pid):
            print(f"Morning brief already running (PID {pid}).")
            return 0
        PID_PATH.unlink(missing_ok=True)

    port = args.port or DEFAULT_PORT
    if is_port_in_use(port):
        print(f"Port {port} is in use. Stop other process or use '{APP_NAME} start --port XXXX'.")
        return 1

    cmd = [sys.executable, str(Path(__file__).resolve()), "serve", "--port", str(port)]
    process = subprocess.Popen(
        cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, start_new_session=True,
    )
    PID_PATH.write_text(str(process.pid))
    wait_for_port(port, timeout=2.0)
    print(f"Morning brief running at http://localhost:{port} (use '{APP_NAME} stop' to shut down)")
    return 0


def command_stop(_args):
    pid = read_pid()
    if not pid or not is_process_running(pid):
        print("Morning brief is not running.")
        PID_PATH.unlink(missing_ok=True)
        return 0
    try:
        os.kill(pid, signal.SIGTERM)
    except OSError:
        print("Unable to stop the morning brief process.")
        return 1
    PID_PATH.unlink(missing_ok=True)
    print("Morning brief stopped.")
    return 0


def command_status(_args):
    pid = read_pid()
    if pid and is_process_running(pid):
        print(f"Morning brief running (PID {pid}).")
        return 0
    print("Morning brief is not running.")
    return 1


def command_serve(args):
    ensure_data_dir()
    prefix = getattr(args, "prefix", "") or ""
    app = create_app(prefix=prefix)
    port = args.port or DEFAULT_PORT
    app.run(host="127.0.0.1", port=port, debug=False)
    return 0


# ---------------------------------------------------------------------------
# Argument parser
# ---------------------------------------------------------------------------

def build_parser():
    parser = argparse.ArgumentParser(prog=APP_NAME)
    subparsers = parser.add_subparsers(dest="command")

    start_parser = subparsers.add_parser("start", help="Start the morning brief server")
    start_parser.add_argument("--port", type=int, default=None, help="Port to bind")

    subparsers.add_parser("stop", help="Stop the morning brief server")
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
