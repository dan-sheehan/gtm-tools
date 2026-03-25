# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Commands

```bash
pip install -r requirements.txt   # Install dependencies (Flask)
./hub start                        # Start all apps + gateway (runs in foreground)
./hub stop                         # Stop all apps
./hub status                       # Check what's running
```

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

**App structure**: Each app follows the same pattern — a single Python file with Flask routes + argparse (`serve --port --prefix`), a `templates/` dir with Jinja2 HTML, and `static/` with one `app.js` and one `style.css`. No build step, no frontend frameworks.

**Data storage**: SQLite databases in user home dirs (e.g. `~/.playbook/playbook.db`). DB connections use Flask `g` object.

**AI integration**: Playbook and the 4 sales tools (Discovery, Competitive Intel, Prompt Builder, Outbound Email) invoke `claude -p` via `subprocess` and stream output to the browser using SSE (Server-Sent Events). Sales tools pass `--allowedTools WebSearch,WebFetch` for web research.

**Morning Brief**: Uses MCP servers (Gmail, Calendar, Notion) via Claude Code to fetch data into `~/.morning-brief/latest.json`, then renders via Flask.
