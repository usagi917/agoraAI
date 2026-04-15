# Agent AI

[![日本語](https://img.shields.io/badge/lang-日本語-green.svg)](README.md)
[![CI](https://github.com/usagi917/agoraAI/actions/workflows/ci.yml/badge.svg)](https://github.com/usagi917/agoraAI/actions/workflows/ci.yml)
[![License: AGPL-3.0](https://img.shields.io/badge/License-AGPL--3.0-blue.svg)](LICENSE)
[![Python 3.11+](https://img.shields.io/badge/python-3.11%2B-blue.svg)](backend/pyproject.toml)
[![Node.js 20+](https://img.shields.io/badge/node-20%2B-339933.svg)](frontend/package.json)

> A multi-agent analysis app that turns one question into synthetic population reactions, council debate, and a final Decision Brief.

## What It Is

- `frontend`: Vue 3 + Vite SPA
- `backend`: FastAPI + async SQLAlchemy + LiteLLM
- Main use cases: market entry, policy impact, scenario comparison, issue exploration
- Execution modes: `quick` / `standard` / `deep` / `research` / `baseline`

## Architecture

### System Overview

```mermaid
flowchart LR
    User["User"] --> Frontend

    subgraph Frontend["Frontend"]
        LaunchPad["LaunchPad / Compare / Populations"]
        LiveUI["Live Simulation / Results"]
    end

    subgraph Backend["Backend"]
        API["FastAPI REST API + SSE"]
        Dispatcher["Simulation Dispatcher"]
        Unified["Unified Orchestrator"]
        Baseline["Baseline Orchestrator"]
    end

    subgraph Runtime["Data / Runtime"]
        DB["SQLite local / PostgreSQL compose"]
        Redis["Redis compose<br/>optional in local dev"]
        Config["config/*.yaml"]
        Templates["templates/ja/*.yaml"]
        LLM["LiteLLM + provider adapters"]
    end

    Frontend --> API
    LaunchPad --> API
    LiveUI --> API
    API --> Dispatcher
    Dispatcher --> Unified
    Dispatcher --> Baseline
    Backend --> DB
    Backend --> Redis
    Backend --> Config
    Backend --> Templates
    Unified --> LLM
    Baseline --> LLM
```

### Analysis Pipeline

```mermaid
flowchart TB
    Input["1. Question + file attachments"] --> Create["2. POST /simulations"]
    Create --> Dispatch["3. Dispatcher selects the mode"]

    Dispatch -->|quick / standard / deep / research| Pulse["4. Society Pulse<br/>population -> selection -> activation -> evaluation"]
    Pulse --> Council["5. Council<br/>representatives -> devil's advocate -> 3-round debate"]
    Council --> Synthesis["6. Synthesis<br/>Decision Brief / report generation"]

    Dispatch -->|baseline| BaselinePath["4b. Single-LLM baseline analysis"]

    Pulse --> Stream["SSE / graph / timeline updates"]
    Council --> Stream
    Synthesis --> Stream
    BaselinePath --> Stream

    Synthesis --> Results["7. Results / follow-up / rerun"]
    BaselinePath --> Results
```

- `baseline` skips the multi-agent debate flow and produces a comparison brief from a single LLM call.
- `scenario-pairs` runs two simulations from the same population snapshot and then builds a side-by-side comparison.

## How It Works

1. Enter a question on the LaunchPad.
2. Attach files if needed.
3. Start a simulation and watch progress in the live view over SSE.
4. Review the final report, then ask follow-up questions or rerun the simulation.
5. Use `scenario-pairs` when you want to compare scenarios side by side.

## Quick Start

### Docker Compose

```bash
cp .env.example .env
docker compose up --build
```

- App: `http://localhost:3000`
- API docs: `http://localhost:8000/docs`
- Health check: `http://localhost:8000/health`

Notes:

- The default provider is `openai`.
- Running new simulations usually requires `OPENAI_API_KEY`.
- The app can still boot without API keys, but live execution will be disabled.

### Minimal API Example

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

### Backend

```bash
cp .env.example .env

cd backend
uv sync --extra dev
uv run uvicorn src.app.main:app --reload --host 0.0.0.0 --port 8000
```

The local default `DATABASE_URL` uses SQLite, so the backend can start without extra infrastructure.

### Frontend

```bash
cd frontend
pnpm install
pnpm dev
```

- Frontend dev server: `http://localhost:5173`
- When `VITE_API_BASE_URL` is unset, the app uses `/api`
- Vite proxies `/api` to `http://localhost:8000`

### With PostgreSQL / Redis

```bash
docker compose up -d postgres redis
```

If needed, switch `.env` to:

```bash
DATABASE_URL=postgresql+asyncpg://agentai:agentai@localhost:5432/agentai
REDIS_URL=redis://localhost:6379/0
```

## Configuration

| Item | Location |
| --- | --- |
| API keys and DB connection | `.env` |
| Default provider and model | `config/models.yaml` |
| Provider definitions and fallback | `config/llm_providers.yaml` |
| Cognitive and scheduling settings | `config/cognitive.yaml` |
| Execution profiles | `config/swarm_profiles.yaml` |
| LaunchPad templates | `templates/ja/*.yaml` |

## Main API

| Method | Endpoint | Purpose |
| --- | --- | --- |
| `GET` | `/health` | service status |
| `GET` | `/templates` | list templates |
| `POST` | `/projects` | create a project for attachments |
| `POST` | `/projects/{project_id}/documents` | add documents |
| `POST` | `/simulations` | create a simulation |
| `GET` | `/simulations/{sim_id}` | get status |
| `GET` | `/simulations/{sim_id}/stream` | SSE progress |
| `GET` | `/simulations/{sim_id}/report` | final report |
| `POST` | `/simulations/{sim_id}/followups` | follow-up question |
| `POST` | `/simulations/{sim_id}/rerun` | rerun |
| `POST` | `/scenario-pairs` | start a scenario comparison |

## Repository Layout

```text
.
├── backend/       # FastAPI app, services, tests
├── frontend/      # Vue app
├── config/        # provider / cognitive / profile settings
├── templates/     # seeded prompt templates
├── data/          # local runtime data
├── DESIGN.md      # extra design notes
└── CONTRIBUTING.md
```

## More Docs

- Design notes: [DESIGN.md](DESIGN.md)
- Contributing: [CONTRIBUTING.md](CONTRIBUTING.md)
- Code of conduct: [CODE_OF_CONDUCT.md](CODE_OF_CONDUCT.md)

## License

AGPL-3.0. See [LICENSE](LICENSE) for details.
