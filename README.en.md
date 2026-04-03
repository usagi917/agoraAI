# Agent AI

[![日本語](https://img.shields.io/badge/lang-日本語-green.svg)](README.md)
[![CI](https://github.com/usagi917/agoraAI/actions/workflows/ci.yml/badge.svg)](https://github.com/usagi917/agoraAI/actions/workflows/ci.yml)
[![License: AGPL-3.0](https://img.shields.io/badge/License-AGPL--3.0-blue.svg)](LICENSE)
[![Python 3.11+](https://img.shields.io/badge/python-3.11%2B-blue.svg)](backend/pyproject.toml)
[![Node.js 20+](https://img.shields.io/badge/node-20%2B-339933.svg)](frontend/package.json)

> A multi-agent analysis app that takes a single question through social reaction simulation, representative council debate, and Decision Brief generation. The `frontend` is built with Vue 3 + Vite, and the `backend` is built around FastAPI and async SQLAlchemy.

## Overview

- Start from one of four guided question templates or a free-form prompt on the LaunchPad.
- Switch between five presets: `quick`, `standard`, `deep`, `research`, and `baseline`.
- Attach `.txt`, `.md`, and `.pdf` files to a project and run evidence-aware analysis on top of them.
- Follow progress live over SSE with activity feed, social response views, conversations, and graph updates.
- Review Decision Briefs, scenario comparison, propagation analysis, transcripts, reruns, and follow-up questions on the results page.
- Generate, inspect, and fork synthetic populations from `/populations`.
- Decision Lab runs two scenarios against the same population side-by-side, comparing opinion shifts, coalition changes, and audit trails.
- Theater UI shows debate cards, live dialogue streams, and real-time stance shifts during simulation.

## Screens And Workflow

| Route | Purpose | Main contents |
| --- | --- | --- |
| `/` | LaunchPad | question templates, free-form prompt, file upload, preset selection, run history |
| `/sim/:id` | Live Simulation | SSE progress, activity feed, social response views, conversations, live graph, Theater UI (debate cards, dialogue stream) |
| `/sim/:id/results` | Results | Decision Brief, scenario comparison, propagation, transcript, follow-up |
| `/populations` | Populations | generation, listing, detail view, forking |
| `/scenario/:id` | Decision Lab | scenario pair comparison, opinion shift table, coalition map, audit timeline |

The main execution flow has three stages:

1. `Society Pulse`
Build a large synthetic population from config and aggregate reactions from selected agents.
2. `Council`
Pick citizen representatives and experts, then run a structured multi-round debate.
3. `Synthesis`
Combine social signals, debate output, and quality metadata into a Decision Brief and comparable scenarios.

### Presets

| Preset | Main phases | When to use it |
| --- | --- | --- |
| `quick` | `society_pulse -> synthesis` | Fast first-pass judgment |
| `standard` | `society_pulse -> council -> synthesis` | Default analysis flow |
| `deep` | `society_pulse -> multi_perspective -> council -> pm_analysis -> synthesis` | Deeper analysis including PM review |
| `research` | `society_pulse -> issue_mining -> multi_perspective -> intervention -> synthesis` | Issue mining and intervention comparison |
| `baseline` | single-LLM baseline execution | Comparison and validation |

Legacy mode names are normalized internally. For example, `unified -> standard`, `society_first -> research`, and `single -> quick`.

## Architecture

```mermaid
flowchart TB
    subgraph Frontend["Frontend"]
        UI["Vue 3 + Vite"]
        STORE["Pinia stores"]
        GRAPH["Three.js / 3d-force-graph"]
    end

    subgraph Backend["Backend"]
        API["FastAPI REST + SSE"]
        ORCH["Simulation dispatcher / orchestrators"]
        SOC["Society services"]
        LLM["Task router + multi-provider adapters"]
        DB["Async SQLAlchemy"]
    end

    subgraph Data["Data / Infra"]
        SQLITE["SQLite (local default)"]
        POSTGRES["PostgreSQL (Compose)"]
        REDIS["Redis (optional / Compose)"]
        CFG["config/*.yaml"]
        TMPL["templates/ja/*.yaml"]
    end

    UI --> API
    STORE --> API
    GRAPH --> API
    API --> ORCH
    ORCH --> SOC
    ORCH --> LLM
    API --> DB
    DB --> SQLITE
    DB --> POSTGRES
    ORCH --> CFG
    API -. optional .-> REDIS
    API --> TMPL
```

Notes:

- The Docker `frontend` is served by Nginx and proxies `/api` to `backend:8000`.
- The `backend` seeds templates from `templates/ja/*.yaml` on startup.
- Local minimal development assumes SQLite. Docker Compose uses PostgreSQL and Redis.

## Quick Start

### Start with Docker Compose

```bash
cp .env.example .env
# If the provider stays openai, set OPENAI_API_KEY
docker compose up --build
```

- App: `http://localhost:3000`
- API docs: `http://localhost:8000/docs`
- Health check: `http://localhost:8000/health`

Notes:

- The default provider in `config/models.yaml` is `openai`. In that state, new simulations require `OPENAI_API_KEY`.
- `GOOGLE_API_KEY` and `ANTHROPIC_API_KEY` are needed only when you actually enable those providers via `config/llm_providers.yaml`.
- The app still boots without API keys, but new live executions are disabled.

### Minimal API example

```bash
curl -X POST http://localhost:8000/simulations \
  -H "Content-Type: application/json" \
  -d '{
    "mode": "standard",
    "execution_profile": "standard",
    "template_name": "market_entry",
    "prompt_text": "Should we enter the EV battery market?",
    "evidence_mode": "strict"
  }'
```

```bash
curl -N http://localhost:8000/simulations/SIM_ID/stream
```

```bash
curl http://localhost:8000/simulations/SIM_ID/report
```

## Local Development

### 1. Backend

`.env.example` points to SQLite, so you can boot the backend without extra infrastructure.

```bash
cp .env.example .env

cd backend
uv sync --extra dev
uv run uvicorn src.app.main:app --reload --host 0.0.0.0 --port 8000
```

### 2. Frontend

Run this in another terminal:

```bash
cd frontend
pnpm install
pnpm dev
```

- Frontend dev server: `http://localhost:5173`
- Vite proxies `/api` to `http://localhost:8000`
- Only set `VITE_API_BASE_URL` when you want to override that default

### 3. With PostgreSQL And Redis

```bash
docker compose up -d postgres redis
```

To match the Docker stack more closely, use:

```bash
DATABASE_URL=postgresql+asyncpg://agentai:agentai@localhost:5432/agentai
REDIS_URL=redis://localhost:6379/0
```

## Configuration

### Important environment variables

| Variable | Purpose |
| --- | --- |
| `OPENAI_API_KEY` | Execution key for the default `openai` provider |
| `GOOGLE_API_KEY` | Key for Gemini through the OpenAI-compatible endpoint |
| `ANTHROPIC_API_KEY` | Key for the Anthropic provider |
| `LLM_MODEL` | Default model; task-level overrides live in `config/models.yaml` |
| `DATABASE_URL` | SQLite locally, PostgreSQL in Compose |
| `REDIS_URL` | Needed only when Redis is enabled |
| `COGNITIVE_MODE` | Switch between `legacy` and `advanced` cognitive modes |
| `MAX_ACTIVE_AGENTS` | Upper bound for managed cognitive agents |
| `MAX_CONCURRENT_AGENTS` | Upper bound for concurrent cognitive cycles |
| `MAX_CONCURRENT_COLONIES` | Upper bound for concurrently running colonies |

### Config files you will likely touch

| File | Purpose |
| --- | --- |
| `config/models.yaml` | default provider, default model, task-specific model routing |
| `config/llm_providers.yaml` | Society-side provider definitions, env key names, fallback order |
| `config/cognitive.yaml` | BDI / ToM / scheduling / rate limiting details |
| `config/swarm_profiles.yaml` | colony counts, round counts, and profile tuning |
| `templates/ja/*.yaml` | LaunchPad templates seeded into the database on startup |

## API Summary

### Core workflow

| Method | Endpoint | Purpose |
| --- | --- | --- |
| `GET` | `/health` | service status and live execution availability |
| `GET` | `/templates` | list available templates |
| `POST` | `/projects` | create a project for attached documents |
| `POST` | `/projects/{project_id}/documents` | upload `.txt` / `.md` / `.pdf` documents |
| `POST` | `/simulations` | create a new simulation |
| `GET` | `/simulations/{sim_id}` | fetch status and metadata |
| `GET` | `/simulations/{sim_id}/stream` | SSE progress stream |
| `GET` | `/simulations/{sim_id}/timeline` | timeline of events |
| `GET` | `/simulations/{sim_id}/graph` | latest graph snapshot |
| `GET` | `/simulations/{sim_id}/graph/history` | graph history by round |
| `GET` | `/simulations/{sim_id}/report` | final report |
| `POST` | `/simulations/{sim_id}/followups` | ask follow-up questions against the result |
| `POST` | `/simulations/{sim_id}/rerun` | rerun with the same conditions |

### Society and operational endpoints

| Method | Endpoint | Purpose |
| --- | --- | --- |
| `GET` | `/society/populations` | list populations |
| `POST` | `/society/populations/generate` | generate a population |
| `GET` | `/society/populations/{pop_id}` | population details |
| `POST` | `/society/populations/{pop_id}/fork` | fork a population |
| `GET` | `/society/simulations/{sim_id}/activation` | activation output |
| `GET` | `/society/simulations/{sim_id}/meeting` | meeting output |
| `GET` | `/society/simulations/{sim_id}/evaluation` | evaluation metrics |
| `GET` | `/society/simulations/{sim_id}/propagation` | propagation data |
| `GET` | `/society/simulations/{sim_id}/transcript` | transcript data |
| `GET` | `/admin/costs` | token and cost aggregation |
| `GET` | `/admin/quality-metrics` | quality and fallback aggregation |

Notes:

- `/runs/*` is the older single-run API and remains for backward compatibility.
- `/simulations/{sim_id}/backtest` is a compatibility endpoint for `society_first` style flows.

## Testing

CI runs the following:

```bash
cd backend
uv sync --extra dev
uv run pytest -q
```

```bash
cd frontend
pnpm install --frozen-lockfile
pnpm build
pnpm test:unit
pnpm exec playwright install --with-deps chromium
pnpm test:e2e
```

## Repository Layout

```text
.
├── backend/            # FastAPI app, async SQLAlchemy, tests, Dockerfile
├── frontend/           # Vue 3 + Vite app, Playwright/Vitest, Dockerfile
├── config/             # LLM / cognitive / grounding / swarm profiles
├── templates/          # templates seeded at startup
├── data/               # local DB and runtime data
├── docker-compose.yml  # frontend + backend + postgres + redis
├── README.md           # Japanese README
└── README.en.md        # English README
```

## Contributing

- See [CONTRIBUTING.md](CONTRIBUTING.md) for contribution workflow and development expectations.
- See [CODE_OF_CONDUCT.md](CODE_OF_CONDUCT.md) for the project code of conduct.

## License

AGPL-3.0. See [LICENSE](LICENSE) for details.
