# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Commands

```bash
# Run standalone (development)
python3 brief.py serve --port 3003
python3 brief.py serve --port 3003 --prefix /brief   # behind gateway

# Lifecycle subcommands
python3 brief.py start [--port 3003]   # daemonize; PID → ~/.morning-brief/morning-brief.pid
python3 brief.py stop
python3 brief.py status

# Fetch signals (requires claude CLI + MCP credentials)
./fetch.sh                              # writes ~/.morning-brief/latest.json
# Or trigger via API after server is running:
curl -X POST http://localhost:3003/api/refresh

# Seed demo data (does NOT overwrite a real latest.json)
curl -X POST http://localhost:3003/api/seed
```

## Architecture

### Data flow

```
fetch.sh
  └─ claude -p prompt.md (MCP tools: Gmail, Calendar, Notion)
       └─ writes ~/.morning-brief/latest.json

Flask (brief.py)
  GET  /api/brief    → reads latest.json, returns signals JSON
  POST /api/refresh  → runs fetch.sh in background, returns {status: "started"}
  POST /api/seed     → copies sample_data.json to latest.json (demo mode)
  GET  /             → serves index.html

Browser (static/app.js)
  → fetches /api/brief on load
  → refresh button: POST /api/refresh, then polls /api/brief every 5s
    until timestamp changes (or 2-min timeout)
```

### Key design decisions

- **No database** — signals live in a single JSON file at `~/.morning-brief/latest.json`. There is no SQLite DB; this app differs from all other apps in the repo.
- **Async refresh** — `/api/refresh` returns immediately; the client polls for a changed timestamp. Fetch runs in a background thread.
- **Prefix injection** — `APP_PREFIX` is injected into both the Jinja2 template and embedded in a `<script>` tag so JS can construct API URLs correctly when running behind the `/brief` gateway prefix.
- **MCP tool allowlist** — `fetch.sh` calls `claude -p` with a hardcoded `--allowedTools` list containing UUID-namespaced MCP tool names. If MCP servers are reconfigured, UUIDs in `fetch.sh` must be updated. Run `claude mcp list` to find current UUIDs.

### prompt.md customization

The system prompt drives all signal extraction. Key hooks to adjust:
- **Gmail search queries** — subject line keywords, date ranges (`newer_than:3d`)
- **Severity thresholds** — what qualifies as high/medium/low
- **Signal categories** — if adding a new category, update both `prompt.md` and the rendering logic in `static/app.js`
- **Notion database** — the prompt references a specific Notion DB; update the ID if your workspace differs

### Error states

- No `latest.json` → API returns `{error: "..."}` JSON; UI shows error banner
- Malformed JSON → same error path
- `fetch.sh` failures → logged to `~/.morning-brief/fetch.log`
- MCP auth expired → open Claude Code and run the failing MCP tool manually to re-authenticate, then retry fetch
