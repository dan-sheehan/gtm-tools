#!/usr/bin/env python3
import argparse
import os
import re
import signal
import socket
import subprocess
import sys
import time
from pathlib import Path
from collections import defaultdict

from flask import Flask, jsonify, render_template, request

APP_NAME = "gtm-trends"
DEFAULT_PORT = 3009
DATA_DIR = Path.home() / ".gtm-trends"
PID_PATH = DATA_DIR / "gtm-trends.pid"
BASE_DIR = Path(__file__).resolve().parent


# ---------------------------------------------------------------------------
# Tool & Skill Dictionaries
# ---------------------------------------------------------------------------

# Each entry: "Display Name": ("Category", [regex_patterns])
# Patterns are matched with word boundaries and case-insensitive

TOOL_DICTIONARY = {
    # CRM
    "Salesforce":       ("CRM", [r"salesforce", r"\bsfdc\b"]),
    "HubSpot":          ("CRM", [r"hubspot"]),
    "Pipedrive":        ("CRM", [r"pipedrive"]),
    "Dynamics 365":     ("CRM", [r"dynamics\s*365", r"\bd365\b"]),
    "Zoho CRM":         ("CRM", [r"zoho\s*crm"]),
    "Close":            ("CRM", [r"\bclose\.com\b", r"\bclose\s+crm\b"]),

    # Sales Engagement
    "Outreach":         ("Sales Engagement", [r"outreach\.io", r"\boutreach\b"]),
    "Salesloft":        ("Sales Engagement", [r"salesloft"]),
    "Apollo":           ("Sales Engagement", [r"apollo\.io", r"\bapollo\b"]),
    "Instantly":        ("Sales Engagement", [r"instantly\.ai", r"\binstantly\b"]),
    "Lemlist":          ("Sales Engagement", [r"lemlist"]),
    "Mixmax":           ("Sales Engagement", [r"mixmax"]),
    "Gong":             ("Sales Engagement", [r"\bgong\b"]),
    "Chorus":           ("Sales Engagement", [r"\bchorus\b"]),

    # Data Enrichment
    "Clay":             ("Data Enrichment", [r"\bclay\b"]),
    "ZoomInfo":         ("Data Enrichment", [r"zoominfo"]),
    "Clearbit":         ("Data Enrichment", [r"clearbit"]),
    "6sense":           ("Data Enrichment", [r"6sense"]),
    "Bombora":          ("Data Enrichment", [r"bombora"]),
    "Lusha":            ("Data Enrichment", [r"lusha"]),
    "Cognism":          ("Data Enrichment", [r"cognism"]),
    "LeadIQ":           ("Data Enrichment", [r"leadiq"]),
    "Demandbase":       ("Data Enrichment", [r"demandbase"]),
    "People Data Labs": ("Data Enrichment", [r"people\s*data\s*labs", r"\bpdl\b"]),
    "Waterfall Enrichment": ("Data Enrichment", [r"waterfall\s*enrichment"]),

    # Automation / Orchestration
    "Zapier":           ("Automation", [r"zapier"]),
    "Make":             ("Automation", [r"make\.com", r"\bintegromat\b"]),
    "n8n":              ("Automation", [r"\bn8n\b"]),
    "Workato":          ("Automation", [r"workato"]),
    "Tray.io":          ("Automation", [r"tray\.io"]),
    "Bardeen":          ("Automation", [r"bardeen"]),

    # Programming Languages
    "Python":           ("Programming", [r"\bpython\b"]),
    "SQL":              ("Programming", [r"\bsql\b"]),
    "JavaScript":       ("Programming", [r"\bjavascript\b", r"\bnode\.?js\b"]),
    "TypeScript":       ("Programming", [r"\btypescript\b"]),
    "R":                ("Programming", [r"\bR\b(?!\s*&\s*D)"]),
    "HTML/CSS":         ("Programming", [r"\bhtml\b", r"\bcss\b"]),
    "Bash/Shell":       ("Programming", [r"\bbash\b", r"\bshell\s*script"]),
    "Go":               ("Programming", [r"\bgolang\b", r"\bgo\s+(?:language|programming)\b"]),

    # Analytics / BI
    "Looker":           ("Analytics", [r"looker"]),
    "Tableau":          ("Analytics", [r"tableau"]),
    "Power BI":         ("Analytics", [r"power\s*bi"]),
    "Metabase":         ("Analytics", [r"metabase"]),
    "dbt":              ("Analytics", [r"\bdbt\b"]),
    "Google Analytics": ("Analytics", [r"google\s*analytics", r"\bga4\b"]),
    "Amplitude":        ("Analytics", [r"amplitude"]),
    "Mixpanel":         ("Analytics", [r"mixpanel"]),
    "Heap":             ("Analytics", [r"\bheap\b"]),
    "Mode":             ("Analytics", [r"\bmode\s+analytics\b"]),

    # Marketing Automation
    "Marketo":          ("Marketing Automation", [r"marketo"]),
    "Pardot":           ("Marketing Automation", [r"pardot"]),
    "Mailchimp":        ("Marketing Automation", [r"mailchimp"]),
    "Braze":            ("Marketing Automation", [r"braze"]),
    "Iterable":         ("Marketing Automation", [r"iterable"]),
    "Customer.io":      ("Marketing Automation", [r"customer\.io"]),
    "Klaviyo":          ("Marketing Automation", [r"klaviyo"]),
    "ActiveCampaign":   ("Marketing Automation", [r"activecampaign"]),
    "Sendgrid":         ("Marketing Automation", [r"sendgrid"]),
    "Intercom":         ("Marketing Automation", [r"intercom"]),

    # ABM
    "Terminus":         ("ABM", [r"terminus"]),
    "RollWorks":        ("ABM", [r"rollworks"]),

    # CS / Success Platforms
    "Gainsight":        ("CS Platforms", [r"gainsight"]),
    "Vitally":          ("CS Platforms", [r"vitally"]),
    "ChurnZero":        ("CS Platforms", [r"churnzero"]),
    "Totango":          ("CS Platforms", [r"totango"]),
    "Catalyst":         ("CS Platforms", [r"\bcatalyst\b"]),
    "Planhat":          ("CS Platforms", [r"planhat"]),

    # Data Infrastructure
    "Snowflake":        ("Data Infrastructure", [r"snowflake"]),
    "BigQuery":         ("Data Infrastructure", [r"bigquery", r"big\s*query"]),
    "Redshift":         ("Data Infrastructure", [r"redshift"]),
    "PostgreSQL":       ("Data Infrastructure", [r"postgres", r"postgresql"]),
    "MongoDB":          ("Data Infrastructure", [r"mongodb", r"\bmongo\b"]),
    "Databricks":       ("Data Infrastructure", [r"databricks"]),
    "Fivetran":         ("Data Infrastructure", [r"fivetran"]),
    "Airbyte":          ("Data Infrastructure", [r"airbyte"]),
    "Segment":          ("Data Infrastructure", [r"\bsegment\b"]),
    "Census":           ("Data Infrastructure", [r"\bcensus\b"]),
    "Hightouch":        ("Data Infrastructure", [r"hightouch"]),
    "Reverse ETL":      ("Data Infrastructure", [r"reverse\s*etl"]),

    # AI / ML Tools
    "OpenAI":           ("AI / ML", [r"openai", r"\bgpt\b", r"chatgpt"]),
    "Claude":           ("AI / ML", [r"\bclaude\b", r"anthropic"]),
    "LangChain":        ("AI / ML", [r"langchain"]),
    "Perplexity":       ("AI / ML", [r"perplexity"]),
    "LLM":              ("AI / ML", [r"\bllm\b", r"large\s*language\s*model"]),

    # DevOps / Infrastructure
    "AWS":              ("Cloud / DevOps", [r"\baws\b", r"amazon\s*web\s*services"]),
    "GCP":              ("Cloud / DevOps", [r"\bgcp\b", r"google\s*cloud"]),
    "Azure":            ("Cloud / DevOps", [r"\bazure\b"]),
    "Docker":           ("Cloud / DevOps", [r"docker"]),
    "Kubernetes":       ("Cloud / DevOps", [r"kubernetes", r"\bk8s\b"]),
    "Terraform":        ("Cloud / DevOps", [r"terraform"]),
    "GitHub Actions":   ("Cloud / DevOps", [r"github\s*actions"]),

    # Project / Collaboration
    "Notion":           ("Collaboration", [r"\bnotion\b"]),
    "Slack":            ("Collaboration", [r"\bslack\b"]),
    "Jira":             ("Collaboration", [r"\bjira\b"]),
    "Asana":            ("Collaboration", [r"\basana\b"]),
    "Linear":           ("Collaboration", [r"\blinear\b"]),
    "Confluence":       ("Collaboration", [r"confluence"]),
    "Airtable":         ("Collaboration", [r"airtable"]),

    # Other GTM Tools
    "Drift":            ("Conversational", [r"\bdrift\b"]),
    "Qualified":        ("Conversational", [r"qualified"]),
    "Chilipiper":       ("Scheduling", [r"chilipiper", r"chili\s*piper"]),
    "Calendly":         ("Scheduling", [r"calendly"]),
    "DocuSign":         ("Document", [r"docusign"]),
    "PandaDoc":         ("Document", [r"pandadoc"]),
    "Loom":             ("Content", [r"\bloom\b"]),
    "Vidyard":          ("Content", [r"vidyard"]),
    "Webflow":          ("Content", [r"webflow"]),
    "WordPress":        ("Content", [r"wordpress"]),
    "Figma":            ("Design", [r"figma"]),

    # CPQ / Billing
    "Stripe":           ("Billing / CPQ", [r"\bstripe\b"]),
    "Chargebee":        ("Billing / CPQ", [r"chargebee"]),
    "DealHub":          ("Billing / CPQ", [r"dealhub"]),
    "Zuora":            ("Billing / CPQ", [r"zuora"]),
    "CPQ":              ("Billing / CPQ", [r"\bcpq\b"]),
}

# Skill patterns: "Skill Name": [regex_patterns]
SKILL_DICTIONARY = {
    "API Integration":          [r"\bapi\b.*integrat", r"rest\s*api", r"webhook", r"\bapi\s*(?:design|develop|build)"],
    "Data Analysis":            [r"data\s*analy", r"data.driven", r"reporting\s*(?:and|&)\s*analytics"],
    "Workflow Automation":      [r"workflow\s*automat", r"process\s*automat", r"automat(?:e|ing)\s*(?:workflow|process|task)"],
    "CRM Administration":       [r"crm\s*(?:admin|manage|config)", r"salesforce\s*admin", r"hubspot\s*admin"],
    "Scripting / Coding":       [r"script(?:ing)?\b", r"coding\b", r"programm(?:ing|atic)"],
    "Data Modeling":            [r"data\s*model", r"schema\s*design", r"data\s*architect"],
    "Revenue Operations":       [r"rev\s*ops", r"revenue\s*operat", r"go.to.market\s*ops"],
    "Lead Scoring / Routing":   [r"lead\s*scor", r"lead\s*rout", r"intent\s*data", r"lead\s*qualif"],
    "ETL / Data Pipelines":     [r"\betl\b", r"data\s*pipeline", r"data\s*ingest", r"data\s*transform"],
    "A/B Testing":              [r"a/b\s*test", r"experiment(?:ation)?", r"split\s*test"],
    "Web Scraping":             [r"web\s*scrap", r"data\s*scrap", r"crawl(?:ing|er)"],
    "SQL Querying":             [r"sql\s*quer", r"write\s*sql", r"complex\s*sql", r"sql\s*report"],
    "Marketing Ops":            [r"marketing\s*ops", r"martech", r"marketing\s*automat"],
    "Technical Writing":        [r"technical\s*writ", r"documentation", r"api\s*doc"],
    "Dashboard Building":       [r"dashboard", r"data\s*visual", r"report\s*build"],
    "Outbound Prospecting":     [r"outbound", r"cold\s*(?:email|outreach|call)", r"prospect(?:ing)?"],
    "Sales Operations":         [r"sales\s*ops", r"sales\s*operat", r"sales\s*process"],
    "Attribution / Tracking":   [r"attribution", r"utm\s*track", r"conversion\s*track"],
    "Product-Led Growth":       [r"product.led", r"\bplg\b", r"self.serve"],
    "Cross-functional Collaboration": [r"cross.functional", r"stakeholder\s*manag", r"collaborate\s*(?:with|across)"],
    "AI / Prompt Engineering":  [r"prompt\s*engineer", r"ai\s*tool", r"generative\s*ai", r"ai.powered"],
    "Systems Integration":      [r"systems?\s*integrat", r"tech\s*stack\s*integrat", r"connect\s*(?:tool|system|platform)"],
    "Lifecycle Marketing":      [r"lifecycle", r"customer\s*journey", r"nurtur(?:e|ing)"],
    "Territory / Capacity Planning": [r"territory\s*plan", r"capacity\s*plan", r"quota\s*(?:set|plan)"],
}

# Category color mapping for consistent chart colors
CATEGORY_COLORS = {
    "CRM":                  "#58a6ff",
    "Sales Engagement":     "#f78166",
    "Data Enrichment":      "#d2a8ff",
    "Automation":           "#3fb950",
    "Programming":          "#ffa657",
    "Analytics":            "#79c0ff",
    "Marketing Automation": "#ff7b72",
    "ABM":                  "#b392f0",
    "CS Platforms":         "#56d4dd",
    "Data Infrastructure":  "#e3b341",
    "AI / ML":              "#f778ba",
    "Cloud / DevOps":       "#8b949e",
    "Collaboration":        "#7ee787",
    "Conversational":       "#ffc680",
    "Scheduling":           "#a5d6ff",
    "Document":             "#d1d5db",
    "Content":              "#fddf68",
    "Design":               "#da77f2",
    "Billing / CPQ":        "#69db7c",
}


# ---------------------------------------------------------------------------
# Analysis Logic
# ---------------------------------------------------------------------------

def extract_from_jd(text, jd_index):
    """Extract tool and skill matches from a single JD."""
    tool_matches = []
    skill_matches = []

    for name, (category, patterns) in TOOL_DICTIONARY.items():
        for pattern in patterns:
            if re.search(pattern, text, re.IGNORECASE):
                tool_matches.append({"name": name, "category": category, "jd_index": jd_index})
                break

    for name, patterns in SKILL_DICTIONARY.items():
        for pattern in patterns:
            if re.search(pattern, text, re.IGNORECASE):
                skill_matches.append({"name": name, "jd_index": jd_index})
                break

    return tool_matches, skill_matches


def get_jd_summary(text):
    """Extract a short summary line from a JD (first meaningful line, truncated)."""
    for line in text.strip().split("\n"):
        line = line.strip()
        if len(line) > 10:
            return line[:100] + ("..." if len(line) > 100 else "")
    return "Untitled JD"


def analyze_jds(raw_text):
    """Split text on --- and analyze each JD."""
    segments = re.split(r"\n\s*---\s*\n", raw_text.strip())
    segments = [s.strip() for s in segments if s.strip()]

    if not segments:
        return {"error": "No job descriptions found. Paste at least one JD."}

    jd_count = len(segments)
    all_tools = []
    all_skills = []
    jd_summaries = []

    for i, segment in enumerate(segments):
        jd_summaries.append(get_jd_summary(segment))
        tools, skills = extract_from_jd(segment, i)
        all_tools.extend(tools)
        all_skills.extend(skills)

    # Aggregate tools
    tool_agg = defaultdict(lambda: {"count": 0, "jd_indices": set(), "category": ""})
    for t in all_tools:
        key = t["name"]
        tool_agg[key]["count"] += 1
        tool_agg[key]["jd_indices"].add(t["jd_index"])
        tool_agg[key]["category"] = t["category"]

    tools_sorted = sorted(
        [
            {
                "name": name,
                "category": data["category"],
                "count": len(data["jd_indices"]),
                "jd_indices": sorted(data["jd_indices"]),
            }
            for name, data in tool_agg.items()
        ],
        key=lambda x: x["count"],
        reverse=True,
    )

    # Aggregate skills
    skill_agg = defaultdict(lambda: {"count": 0, "jd_indices": set()})
    for s in all_skills:
        key = s["name"]
        skill_agg[key]["count"] += 1
        skill_agg[key]["jd_indices"].add(s["jd_index"])

    skills_sorted = sorted(
        [
            {
                "name": name,
                "count": len(data["jd_indices"]),
                "jd_indices": sorted(data["jd_indices"]),
            }
            for name, data in skill_agg.items()
        ],
        key=lambda x: x["count"],
        reverse=True,
    )

    # Group tools by category
    categories = defaultdict(list)
    for t in tools_sorted:
        categories[t["category"]].append({"name": t["name"], "count": t["count"], "jd_indices": t["jd_indices"]})

    return {
        "jd_count": jd_count,
        "tools": tools_sorted,
        "skills": skills_sorted,
        "categories": dict(categories),
        "category_colors": CATEGORY_COLORS,
        "jd_summaries": jd_summaries,
    }


# ---------------------------------------------------------------------------
# Flask application
# ---------------------------------------------------------------------------

def create_app(prefix=""):
    app = Flask(
        __name__,
        static_folder=str(BASE_DIR / "static"),
        static_url_path="/static",
        template_folder=str(BASE_DIR / "templates"),
    )
    app.config["URL_PREFIX"] = prefix

    @app.context_processor
    def inject_prefix():
        return {"prefix": app.config["URL_PREFIX"]}

    # Serve static files at prefixed path too (for direct access with --prefix)
    if prefix:
        @app.route(prefix + "/static/<path:filename>")
        def prefixed_static(filename):
            return app.send_static_file(filename)

    @app.route(prefix + "/")
    @app.route("/")
    def index():
        return render_template("index.html")

    @app.route(prefix + "/api/analyze", methods=["POST"])
    @app.route("/api/analyze", methods=["POST"])
    def api_analyze():
        data = request.get_json(silent=True) or {}
        text = (data.get("text") or "").strip()
        if not text:
            return jsonify({"error": "No text provided"}), 400
        result = analyze_jds(text)
        if "error" in result:
            return jsonify(result), 400
        return jsonify(result)

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
    DATA_DIR.mkdir(parents=True, exist_ok=True)

    if PID_PATH.exists():
        pid = read_pid()
        if pid and is_process_running(pid):
            print(f"GTM Trends already running (PID {pid}).")
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
    print(f"GTM Trends running at http://localhost:{port} (use '{APP_NAME} stop' to shut down)")
    return 0


def command_stop(_args):
    pid = read_pid()
    if not pid or not is_process_running(pid):
        print("GTM Trends is not running.")
        PID_PATH.unlink(missing_ok=True)
        return 0
    try:
        os.kill(pid, signal.SIGTERM)
    except OSError:
        print("Unable to stop the GTM Trends process.")
        return 1
    PID_PATH.unlink(missing_ok=True)
    print("GTM Trends stopped.")
    return 0


def command_status(_args):
    pid = read_pid()
    if pid and is_process_running(pid):
        print(f"GTM Trends running (PID {pid}).")
        return 0
    print("GTM Trends is not running.")
    return 1


def command_serve(args):
    prefix = getattr(args, "prefix", "") or ""
    app = create_app(prefix=prefix)
    port = args.port or DEFAULT_PORT
    app.run(host="127.0.0.1", port=port, debug=False, threaded=True)
    return 0


def build_parser():
    parser = argparse.ArgumentParser(prog=APP_NAME)
    subparsers = parser.add_subparsers(dest="command")

    start_parser = subparsers.add_parser("start", help="Start the GTM Trends server")
    start_parser.add_argument("--port", type=int, default=None, help="Port to bind")

    subparsers.add_parser("stop", help="Stop the GTM Trends server")
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
