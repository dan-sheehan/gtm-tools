# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Commands

```bash
pip install -r requirements.txt   # Install dependencies (Flask>=3.0, only dependency)
./hub start                        # Start all apps + gateway (runs in foreground)
./hub stop                         # Stop all apps
./hub status                       # Check what's running
make seed                          # Load sample data into all apps (idempotent)
make test                          # Run pytest
pytest tests/test_pipeline.py      # Run a single test file
make lint                          # Run ruff check apps/
```

**Run a single app standalone** (useful for development):
```bash
python3 apps/pipeline/pipeline.py serve --port 3010
python3 apps/pipeline/pipeline.py serve --port 3010 --prefix /pipeline  # with gateway prefix
```

Each app CLI also supports `start` (daemonize), `stop`, and `status` subcommands.

## Architecture

**Gateway pattern**: A stdlib reverse proxy at port 8000 routes by path prefix to individual Flask apps. Each app works standalone on its own port or behind the gateway.

| App | Port | Prefix | Key file |
|-----|------|--------|----------|
| Gateway | 8000 | — | `apps/gateway/gateway.py` |
| Morning Brief | 3003 | `/brief` | `apps/morning-brief/brief.py` |
| Playbook | 3004 | `/playbook` | `apps/playbook/playbook.py` |
| Discovery | 3005 | `/discovery` | `apps/discovery/discovery.py` |
| Competitive Intel | 3006 | `/competitive-intel` | `apps/competitive-intel/competitive_intel.py` |
| Prompt Builder | 3007 | `/prompt-builder` | `apps/prompt-builder/prompt_builder.py` |
| Outbound Email | 3008 | `/outbound-email` | `apps/outbound-email/outbound_email.py` |
| GTM Trends | 3009 | `/gtm-trends` | `apps/gtm-trends/gtm_trends.py` |
| Pipeline | 3010 | `/pipeline` | `apps/pipeline/pipeline.py` |
| Enrichment | 3011 | `/enrichment` | `apps/enrichment/enrichment.py` |
| ICP Scorer | 3012 | `/icp-scorer` | `apps/icp-scorer/icp_scorer.py` |

**App structure**: Each app follows the same pattern — a single Python file with Flask routes + argparse (`serve --port --prefix`), a `templates/` dir with Jinja2 HTML, and `static/` with one `app.js` and one `style.css`. No build step, no frontend frameworks.

**Data storage**: SQLite databases in user home dirs (e.g. `~/.playbook/playbook.db`). DB connections use Flask `g` object.

**AI integration**: Playbook and the 4 sales tools (Discovery, Competitive Intel, Prompt Builder, Outbound Email) invoke `claude -p` via `subprocess` and stream output to the browser using SSE (Server-Sent Events). Sales tools pass `--allowedTools WebSearch,WebFetch` for web research.

**Morning Brief**: Uses MCP servers (Gmail, Calendar, Notion) via Claude Code to fetch data into `~/.morning-brief/latest.json`, then renders via Flask.

**Seed data**: Most apps support `POST /api/seed` to load sample data for demo mode. `make seed` hits all endpoints.

## Testing

Tests live in `tests/` and run with pytest. CI (GitHub Actions) runs `ruff check` + `pytest` on Python 3.10 and 3.12.

**Critical pattern**: App directories have hyphens (e.g. `competitive-intel`), so they can't be imported normally. `tests/conftest.py` uses `importlib` to load each app module and registers them as `app_gateway`, `app_enrichment`, `app_competitive_intel`, etc. Tests import these registered module names.

## Style

Ruff with line-length 120, target py39. Python >=3.10 required.
