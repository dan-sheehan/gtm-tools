# GTM Tools

Open-source GTM engineering toolkit — 9 AI-powered apps covering the full revenue cycle from prospecting through close to post-sale retention.

Local-first. No SaaS dependencies. Clone, install, run.

## What's included

| App | What it does | Port |
|-----|-------------|------|
| **Discovery Call Prep** | Research companies & prospects before calls | 3005 |
| **Competitive Intelligence** | Build competitive battlecards in 3 formats | 3006 |
| **Outbound Email** | Generate persona-based multi-touch cadences | 3008 |
| **Onboarding Playbook** | Create segment-specific onboarding playbooks | 3004 |
| **Prompt Builder** | Generate meeting-memory search prompts | 3007 |
| **GTM Trends** | Spot tool & skill patterns across GTM job postings | 3009 |
| **Morning Brief** | Daily signal detection dashboard | 3003 |
| **Prompt Library** | Searchable library of reusable AI prompts | 3002 |
| **Gateway** | Hub page that routes to all apps | 8000 |

## Quick start

```bash
git clone https://github.com/dan-sheehan/gtm-eng-toolkit.git
cd gtm-eng-toolkit
make install
make start
# Open http://localhost:8000
```

## Architecture

```
gtm-tools/
├── apps/              # 9 independent Flask apps
│   └── gateway/       # stdlib reverse proxy (no Flask)
├── data/
│   ├── prompts/       # Prompt template files
│   └── contexts/      # Company context files for discovery prep
└── hub                # Bash launcher (start/stop/status)
```

**Design decisions:**
- **Gateway pattern** — One entry point at `localhost:8000` routes to independent backends by path prefix
- **AI layer** — Claude CLI (`claude -p`) via subprocess with streaming output over SSE
- **Storage** — SQLite per app, zero config, no shared state
- **Frontend** — Vanilla HTML/CSS/JS, no build step, no node_modules
- **Local-first** — All data stays on your machine

## Tech stack

Python, Flask, SQLite, Claude CLI, vanilla JavaScript, Server-Sent Events

## Requirements

- Python 3.9+
- [Claude CLI](https://docs.anthropic.com/en/docs/claude-code) (for AI-powered apps)

## Commands

```bash
make install    # Install Python dependencies
make start      # Start all apps + gateway
make stop       # Stop everything
make status     # Show what's running
make test       # Run tests
make lint       # Run linter
```

## Adding company context

The discovery app can load markdown files as context for call prep. Drop company research into `data/contexts/<company-name>/`:

```
data/contexts/
└── acme/
    ├── notes.md
    └── research.md
```

## Contributing

See [CONTRIBUTING.md](CONTRIBUTING.md).

## License

MIT — see [LICENSE](LICENSE).
