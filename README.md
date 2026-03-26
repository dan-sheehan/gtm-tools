# GTM Tools

A local-first GTM engineering toolkit that automates the research, scoring, and outreach workflows revenue teams do manually every day.

Built with Python, Flask, SQLite, and Claude CLI. No SaaS dependencies. No build step. No vendor lock-in.

## Outbound Pipeline

Tools that chain together to find, qualify, and reach target accounts.

| Tool | What it does |
|------|-------------|
| **Lead Enrichment** | Multi-step company enrichment — web research, tech stack, funding signals, competitive landscape |
| **ICP Scorer** | Rule-based scoring engine with weighted dimensions — industry, size, funding, tech stack, growth, buying signals |
| **Outbound Email** | AI-powered cold outreach sequences — persona-targeted, 4-touch cadences with research-backed personalization |
| **GTM Signal Dashboard** | Daily signal detection — pipeline alerts, competitive intel, account changes, market signals |

**Workflow:** Enrichment gathers company data → ICP Scorer qualifies the account → Outbound Email generates a personalized sequence → Signal Dashboard surfaces daily alerts.

## Sales Enablement

Tools that prepare reps to win deals.

| Tool | What it does |
|------|-------------|
| **Discovery Call Prep** | Research companies and prospects before calls — company bullets, prospect background, talking points |
| **Competitive Intelligence** | Battlecards, head-to-head comparisons, and market positioning analysis |
| **Onboarding Playbook** | Segment-specific onboarding playbooks with milestones and success criteria |
| **Prompt Builder** | Generate meeting-memory search prompts tailored to company and role |

**Workflow:** Discovery researches the account → Competitive Intel arms the rep → deal closes → Playbook generates onboarding plan.

## Infrastructure

| Tool | What it does |
|------|-------------|
| **Pipeline Dashboard** | Deal tracking with stage-weighted metrics and pipeline visualization |
| **GTM Trends** | Analyze GTM job postings to spot tool and skill patterns across the market |
| **Gateway** | Reverse proxy hub — one entry point at localhost:8000 routes to all apps |

## Quick Start

```bash
git clone <repo-url>
cd gtm-tools
make install
make start
make seed     # Load sample data (optional — skip if you have Claude CLI)
# Open http://localhost:8000
```

## Architecture

**Gateway pattern** — One entry point at `localhost:8000` routes to independent backends by path prefix. Each app is a standalone Flask server that can run independently on its own port.

**AI layer** — Claude CLI (`claude -p`) via subprocess with streaming output over Server-Sent Events. Tools that need web research pass `--allowedTools WebSearch,WebFetch`. No API keys required — works with a Claude Max subscription via CLI.

**Storage** — SQLite per app (`~/.appname/appname.db`), zero config, no shared state. Apps never contend for locks, and data is easy to inspect or reset independently.

**Frontend** — Vanilla HTML/CSS/JS, no build step, no node_modules. Each app has a single `app.js` wrapped in an IIFE and a `style.css` with CSS variables.

**Local-first** — All data stays on your machine. No external databases, no cloud storage, no telemetry.

## Tech Stack

Python · Flask · SQLite · Claude CLI · Vanilla JavaScript · Server-Sent Events

## How AI Is Used

Every AI-powered tool calls Claude CLI (`claude -p`) via subprocess and streams results to the browser over Server-Sent Events. Tools that need web research pass `--allowedTools WebSearch,WebFetch`. This means:

- No API keys required (uses Claude Max subscription via CLI)
- All AI calls are transparent — you can see exactly what prompt was sent
- Results stream in real-time, not batch

## Requirements

- Python 3.9+
- Flask
- Claude CLI (for AI-powered tools — install from https://docs.anthropic.com/en/docs/claude-code)

## License

MIT
