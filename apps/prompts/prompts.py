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
from collections import Counter
from pathlib import Path

from flask import Flask, jsonify, render_template, request

APP_NAME = "prompts"
DEFAULT_PORT = 3002
DATA_DIR = Path.home() / ".promptlib"
PID_PATH = DATA_DIR / "prompts.pid"
CONFIG_PATH = DATA_DIR / "config.json"
BASE_DIR = Path(__file__).resolve().parent

# Add app directory to path so we can import cli subpackage
sys.path.insert(0, str(BASE_DIR))

from cli.indexer import index_prompts, Prompt  # noqa: E402
from cli.search import filter_by_tag  # noqa: E402


# ---------------------------------------------------------------------------
# Helpers
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


def slugify(name: str) -> str:
    s = name.lower().strip()
    s = re.sub(r"[^\w\s-]", "", s)
    s = re.sub(r"[\s_]+", "-", s)
    s = re.sub(r"-+", "-", s).strip("-")
    return s


def substitute_variables(body: str, variables: dict[str, str]) -> str:
    for key, value in variables.items():
        token = f"{{{{{key}}}}}"
        body = body.replace(token, value)
    return body


def prompt_to_dict(prompt: Prompt) -> dict:
    return {
        "name": prompt.name,
        "slug": slugify(prompt.name),
        "description": prompt.description,
        "tags": prompt.tags,
        "variables": prompt.variables,
        "body": prompt.body,
        "source_file": prompt.source_file,
        "type": prompt.type,
    }


def parse_pagination_args(default_limit=50, max_limit=100):
    offset = request.args.get("offset", "0")
    limit = request.args.get("limit", str(default_limit))
    try:
        offset = max(int(offset), 0)
    except ValueError:
        offset = 0
    try:
        limit = min(max(int(limit), 1), max_limit)
    except ValueError:
        limit = default_limit
    return offset, limit


def get_all_tags(prompts: list[Prompt]) -> list[dict]:
    tag_counts: Counter = Counter()
    for p in prompts:
        for t in p.tags:
            tag_counts[t.lower()] += 1
    return [
        {"name": name, "count": count}
        for name, count in sorted(tag_counts.items(), key=lambda x: (-x[1], x[0]))
    ]


def make_snippet(text, query, max_len=160):
    if not text:
        return ""
    lower = text.lower()
    idx = lower.find(query.lower()) if query else -1
    if idx == -1:
        snippet = text[:max_len]
        return snippet + ("..." if len(text) > max_len else "")
    start = max(0, idx - max_len // 2)
    end = min(len(text), start + max_len)
    snippet = text[start:end]
    prefix = "..." if start > 0 else ""
    suffix = "..." if end < len(text) else ""
    return f"{prefix}{snippet}{suffix}"


def numeric_sort_key(prompt):
    """Sort prompts numerically if they start with a number, otherwise alphabetically."""
    match = re.match(r"^(\d+)\.", prompt.name)
    if match:
        return (0, int(match.group(1)), prompt.name.lower())
    return (1, 0, prompt.name.lower())


def find_by_slug(prompts, slug):
    for p in prompts:
        if slugify(p.name) == slug:
            return p
    return None


def filter_prompts_by_query(prompts: list[Prompt], query: str) -> list[Prompt]:
    query_lower = query.lower()
    results = []
    for prompt in prompts:
        if (
            query_lower in prompt.name.lower()
            or query_lower in prompt.description.lower()
            or query_lower in prompt.body.lower()
            or any(query_lower in tag.lower() for tag in prompt.tags)
        ):
            results.append(prompt)
    results.sort(key=numeric_sort_key)
    return results


# ---------------------------------------------------------------------------
# Flask application
# ---------------------------------------------------------------------------

def create_app(prefix=""):
    app = Flask(
        __name__,
        static_folder=str(BASE_DIR / "static"),
        template_folder=str(BASE_DIR / "templates"),
    )
    app.config["URL_PREFIX"] = prefix

    @app.context_processor
    def inject_prefix():
        return {"prefix": app.config["URL_PREFIX"]}

    # --- Page routes -------------------------------------------------------

    @app.route("/")
    def index():
        return render_template("index.html")

    @app.route("/prompt/<slug>")
    def prompt_detail(slug):
        return render_template("prompt.html", prompt_slug=slug)

    @app.route("/prompt/<slug>/run")
    def prompt_run(slug):
        return render_template("run.html", prompt_slug=slug)

    @app.route("/search")
    def search_page():
        return render_template("search.html")

    # --- API routes --------------------------------------------------------

    @app.route("/api/prompts", methods=["GET"])
    def api_prompts_list():
        prompts = index_prompts()
        q = (request.args.get("q") or "").strip()
        tag = (request.args.get("tag") or "").strip()
        prompt_type = (request.args.get("type") or "").strip()
        offset, limit = parse_pagination_args()

        if prompt_type:
            prompts = [p for p in prompts if p.type == prompt_type]
        if tag:
            prompts = filter_by_tag(prompts, tag)
        if q:
            prompts = filter_prompts_by_query(prompts, q)
        else:
            prompts.sort(key=numeric_sort_key)

        total = len(prompts)
        page = prompts[offset: offset + limit]
        payload = [prompt_to_dict(p) for p in page]
        if q:
            for item, prompt in zip(payload, page):
                item["snippet"] = make_snippet(prompt.body, q)

        return jsonify(
            {
                "prompts": payload,
                "total": total,
                "offset": offset,
                "limit": limit,
                "has_more": offset + len(page) < total,
            }
        )

    @app.route("/api/prompts/<slug>", methods=["GET"])
    def api_prompt_get(slug):
        prompts = index_prompts()
        prompt = find_by_slug(prompts, slug)
        if not prompt:
            return jsonify({"error": "Prompt not found"}), 404
        return jsonify(prompt_to_dict(prompt))

    @app.route("/api/prompts/<slug>/run", methods=["POST"])
    def api_prompt_run(slug):
        prompts = index_prompts()
        prompt = find_by_slug(prompts, slug)
        if not prompt:
            return jsonify({"error": "Prompt not found"}), 404

        data = request.get_json(silent=True) or {}
        variables = data.get("variables", {})

        missing = [v for v in prompt.variables if v not in variables]
        if missing:
            return jsonify({"error": f"Missing variables: {', '.join(missing)}"}), 400

        rendered = substitute_variables(prompt.body, variables)
        return jsonify({"rendered": rendered, "name": prompt.name})

    @app.route("/api/tags", methods=["GET"])
    def api_tags():
        prompts = index_prompts()
        prompt_type = (request.args.get("type") or "").strip()
        if prompt_type:
            prompts = [p for p in prompts if p.type == prompt_type]
        return jsonify({"tags": get_all_tags(prompts)})

    @app.route("/api/types", methods=["GET"])
    def api_types():
        prompts = index_prompts()
        type_counts = Counter(p.type for p in prompts)
        return jsonify({"types": [
            {"name": name, "count": count}
            for name, count in sorted(type_counts.items())
        ]})

    @app.route("/api/search", methods=["GET"])
    def api_search():
        q = (request.args.get("q") or "").strip()
        offset, limit = parse_pagination_args()
        if not q:
            return jsonify(
                {"results": [], "total": 0, "offset": offset, "limit": limit, "has_more": False}
            )
        prompts = index_prompts()
        results = filter_prompts_by_query(prompts, q)
        total = len(results)
        page = results[offset: offset + limit]
        output = []
        for p in page:
            d = prompt_to_dict(p)
            d["snippet"] = make_snippet(p.body, q)
            output.append(d)
        return jsonify(
            {
                "results": output,
                "total": total,
                "offset": offset,
                "limit": limit,
                "has_more": offset + len(page) < total,
            }
        )

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
            print(f"Prompt library already running (PID {pid}).")
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

    print(f"Prompt library running at http://localhost:{port} (use '{APP_NAME} stop' to shut down)")
    return 0


def command_stop(_args):
    pid = read_pid()
    if not pid or not is_process_running(pid):
        print("Prompt library is not running.")
        PID_PATH.unlink(missing_ok=True)
        return 0
    try:
        os.kill(pid, signal.SIGTERM)
    except OSError:
        print("Unable to stop the prompt library process.")
        return 1
    PID_PATH.unlink(missing_ok=True)
    print("Prompt library stopped.")
    return 0


def command_status(_args):
    pid = read_pid()
    if pid and is_process_running(pid):
        print(f"Prompt library running (PID {pid}).")
        return 0
    print("Prompt library is not running.")
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

    start_parser = subparsers.add_parser("start", help="Start the prompt library server")
    start_parser.add_argument("--port", type=int, default=None, help="Port to bind")

    subparsers.add_parser("stop", help="Stop the prompt library server")
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
