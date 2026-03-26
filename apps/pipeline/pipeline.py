#!/usr/bin/env python3
"""Pipeline Dashboard — Deal tracking and pipeline metrics."""
from __future__ import annotations

import argparse
import json
import os
import signal
import socket
import sqlite3
import subprocess
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

from flask import Flask, g, jsonify, render_template, request

APP_NAME = "pipeline"
DEFAULT_PORT = 3010
DATA_DIR = Path.home() / ".pipeline"
DB_PATH = DATA_DIR / "pipeline.db"
PID_PATH = DATA_DIR / "pipeline.pid"
BASE_DIR = Path(__file__).resolve().parent
SEED_PATH = BASE_DIR / "seed" / "deals.json"

STAGES = ["prospecting", "discovery", "proposal", "negotiation", "closed_won", "closed_lost"]
STAGE_WEIGHTS = {
    "prospecting": 0.10,
    "discovery": 0.25,
    "proposal": 0.50,
    "negotiation": 0.75,
    "closed_won": 1.00,
    "closed_lost": 0.00,
}


# ---------------------------------------------------------------------------
# Database helpers
# ---------------------------------------------------------------------------

def ensure_db() -> None:
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(DB_PATH))
    conn.execute("""
        CREATE TABLE IF NOT EXISTS deals (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            company TEXT NOT NULL,
            contact TEXT NOT NULL DEFAULT '',
            value REAL NOT NULL DEFAULT 0,
            stage TEXT NOT NULL DEFAULT 'prospecting',
            days_in_stage INTEGER NOT NULL DEFAULT 0,
            close_date TEXT,
            created_at TEXT NOT NULL
        )
    """)
    conn.commit()
    conn.close()


def get_db() -> sqlite3.Connection:
    if "db" not in g:
        g.db = sqlite3.connect(str(DB_PATH))
        g.db.row_factory = sqlite3.Row
    return g.db


def close_db(exc: BaseException | None = None) -> None:
    db = g.pop("db", None)
    if db is not None:
        db.close()


# ---------------------------------------------------------------------------
# Flask application
# ---------------------------------------------------------------------------

def create_app(prefix: str = "") -> Flask:
    app = Flask(
        __name__,
        static_folder=str(BASE_DIR / "static"),
        template_folder=str(BASE_DIR / "templates"),
    )
    app.config["URL_PREFIX"] = prefix
    app.teardown_appcontext(close_db)

    @app.context_processor
    def inject_prefix() -> dict[str, str]:
        return {"prefix": app.config["URL_PREFIX"]}

    @app.route("/")
    def index():
        return render_template("index.html")

    @app.route("/api/deals", methods=["GET"])
    def api_deals():
        db = get_db()
        stage_filter = request.args.get("stage")
        if stage_filter and stage_filter in STAGES:
            rows = db.execute(
                "SELECT * FROM deals WHERE stage = ? ORDER BY value DESC", (stage_filter,)
            ).fetchall()
        else:
            rows = db.execute("SELECT * FROM deals ORDER BY created_at DESC").fetchall()
        return jsonify({"deals": [dict(r) for r in rows]})

    @app.route("/api/deals", methods=["POST"])
    def api_create_deal():
        data = request.get_json(silent=True) or {}
        company = data.get("company", "").strip()
        if not company:
            return jsonify({"error": "Company name is required"}), 400

        now = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S")
        db = get_db()
        cur = db.execute(
            "INSERT INTO deals (company, contact, value, stage, days_in_stage, close_date, created_at) VALUES (?, ?, ?, ?, ?, ?, ?)",
            (
                company,
                data.get("contact", ""),
                float(data.get("value", 0)),
                data.get("stage", "prospecting"),
                int(data.get("days_in_stage", 0)),
                data.get("close_date", ""),
                now,
            ),
        )
        db.commit()
        return jsonify({"id": cur.lastrowid, "status": "created"})

    @app.route("/api/deals/<int:deal_id>", methods=["PUT"])
    def api_update_deal(deal_id):
        data = request.get_json(silent=True) or {}
        db = get_db()
        row = db.execute("SELECT * FROM deals WHERE id = ?", (deal_id,)).fetchone()
        if not row:
            return jsonify({"error": "Not found"}), 404

        db.execute(
            "UPDATE deals SET company=?, contact=?, value=?, stage=?, days_in_stage=?, close_date=? WHERE id=?",
            (
                data.get("company", row["company"]),
                data.get("contact", row["contact"]),
                float(data.get("value", row["value"])),
                data.get("stage", row["stage"]),
                int(data.get("days_in_stage", row["days_in_stage"])),
                data.get("close_date", row["close_date"]),
                deal_id,
            ),
        )
        db.commit()
        return jsonify({"status": "updated"})

    @app.route("/api/deals/<int:deal_id>", methods=["DELETE"])
    def api_delete_deal(deal_id):
        db = get_db()
        db.execute("DELETE FROM deals WHERE id = ?", (deal_id,))
        db.commit()
        return jsonify({"status": "deleted"})

    @app.route("/api/metrics", methods=["GET"])
    def api_metrics():
        db = get_db()
        rows = db.execute("SELECT * FROM deals").fetchall()
        deals = [dict(r) for r in rows]

        open_stages = ["prospecting", "discovery", "proposal", "negotiation"]
        open_deals = [d for d in deals if d["stage"] in open_stages]
        won_deals = [d for d in deals if d["stage"] == "closed_won"]
        lost_deals = [d for d in deals if d["stage"] == "closed_lost"]

        total_pipeline = sum(d["value"] for d in open_deals)
        weighted_pipeline = sum(
            d["value"] * STAGE_WEIGHTS.get(d["stage"], 0) for d in open_deals
        )
        avg_deal_size = total_pipeline / len(open_deals) if open_deals else 0

        # Stage counts and values
        stage_summary = []
        for stage in STAGES:
            stage_deals = [d for d in deals if d["stage"] == stage]
            stage_summary.append({
                "stage": stage,
                "count": len(stage_deals),
                "value": sum(d["value"] for d in stage_deals),
            })

        # Win rate
        closed_total = len(won_deals) + len(lost_deals)
        win_rate = round(len(won_deals) / closed_total * 100) if closed_total > 0 else 0

        # Average days in stage for open deals
        avg_days = {}
        for stage in open_stages:
            stage_deals = [d for d in deals if d["stage"] == stage]
            if stage_deals:
                avg_days[stage] = round(
                    sum(d["days_in_stage"] for d in stage_deals) / len(stage_deals), 1
                )
            else:
                avg_days[stage] = 0

        return jsonify({
            "total_pipeline": round(total_pipeline, 2),
            "weighted_pipeline": round(weighted_pipeline, 2),
            "avg_deal_size": round(avg_deal_size, 2),
            "open_deals": len(open_deals),
            "won_deals": len(won_deals),
            "lost_deals": len(lost_deals),
            "win_rate": win_rate,
            "stage_summary": stage_summary,
            "avg_days_in_stage": avg_days,
        })

    @app.route("/api/seed", methods=["POST"])
    def api_seed():
        if not SEED_PATH.exists():
            return jsonify({"error": "Seed file not found"}), 404
        db = get_db()
        existing = db.execute("SELECT COUNT(*) FROM deals").fetchone()[0]
        if existing > 0:
            return jsonify({"status": "seeded", "count": 0, "message": "already seeded"})
        seed_data = json.loads(SEED_PATH.read_text())
        now = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S")
        for deal in seed_data:
            db.execute(
                "INSERT INTO deals (company, contact, value, stage, days_in_stage, close_date, created_at) VALUES (?, ?, ?, ?, ?, ?, ?)",
                (
                    deal["company"],
                    deal.get("contact", ""),
                    float(deal.get("value", 0)),
                    deal.get("stage", "prospecting"),
                    int(deal.get("days_in_stage", 0)),
                    deal.get("close_date", ""),
                    now,
                ),
            )
        db.commit()
        return jsonify({"status": "seeded", "count": len(seed_data)})

    return app


# ---------------------------------------------------------------------------
# Server lifecycle CLI
# ---------------------------------------------------------------------------

def is_port_in_use(port: int) -> bool:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.settimeout(0.2)
        return sock.connect_ex(("127.0.0.1", port)) == 0


def wait_for_port(port: int, timeout: float = 2.0) -> bool:
    start = time.time()
    while time.time() - start < timeout:
        if is_port_in_use(port):
            return True
        time.sleep(0.1)
    return False


def read_pid() -> int | None:
    if not PID_PATH.exists():
        return None
    try:
        return int(PID_PATH.read_text().strip())
    except ValueError:
        return None


def is_process_running(pid: int | None) -> bool:
    if pid is None:
        return False
    try:
        os.kill(pid, 0)
    except OSError:
        return False
    return True


def command_start(args: argparse.Namespace) -> int:
    ensure_db()
    if PID_PATH.exists():
        pid = read_pid()
        if pid and is_process_running(pid):
            print(f"Pipeline Dashboard already running (PID {pid}).")
            return 0
        PID_PATH.unlink(missing_ok=True)

    port = args.port or DEFAULT_PORT
    if is_port_in_use(port):
        print(f"Port {port} is in use.")
        return 1

    cmd = [sys.executable, str(Path(__file__).resolve()), "serve", "--port", str(port)]
    if args.prefix:
        cmd += ["--prefix", args.prefix]
    process = subprocess.Popen(
        cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, start_new_session=True,
    )
    PID_PATH.write_text(str(process.pid))
    wait_for_port(port)
    print(f"Pipeline Dashboard running at http://localhost:{port}")
    return 0


def command_stop(_args: argparse.Namespace) -> int:
    pid = read_pid()
    if not pid or not is_process_running(pid):
        print("Pipeline Dashboard is not running.")
        PID_PATH.unlink(missing_ok=True)
        return 0
    try:
        os.kill(pid, signal.SIGTERM)
    except OSError:
        print("Unable to stop Pipeline Dashboard.")
        return 1
    PID_PATH.unlink(missing_ok=True)
    print("Pipeline Dashboard stopped.")
    return 0


def command_status(_args: argparse.Namespace) -> int:
    pid = read_pid()
    if pid and is_process_running(pid):
        print(f"Pipeline Dashboard running (PID {pid}).")
        return 0
    print("Pipeline Dashboard is not running.")
    return 1


def command_serve(args: argparse.Namespace) -> int:
    ensure_db()
    prefix = getattr(args, "prefix", "") or ""
    app = create_app(prefix=prefix)
    port = args.port or DEFAULT_PORT
    app.run(host="127.0.0.1", port=port, debug=False)
    return 0


# ---------------------------------------------------------------------------
# Argument parser
# ---------------------------------------------------------------------------

def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog=APP_NAME)
    subparsers = parser.add_subparsers(dest="command")

    start_p = subparsers.add_parser("start")
    start_p.add_argument("--port", type=int, default=None)
    start_p.add_argument("--prefix", type=str, default="")

    subparsers.add_parser("stop")
    subparsers.add_parser("status")

    serve_p = subparsers.add_parser("serve")
    serve_p.add_argument("--port", type=int, default=None)
    serve_p.add_argument("--prefix", type=str, default="")

    return parser


def main() -> int:
    parser = build_parser()
    args = parser.parse_args()

    commands = {
        "start": command_start,
        "stop": command_stop,
        "status": command_status,
        "serve": command_serve,
    }

    handler = commands.get(args.command)
    if handler:
        return handler(args)

    parser.print_help()
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
