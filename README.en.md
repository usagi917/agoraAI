# Agent AI

[![日本語](https://img.shields.io/badge/lang-日本語-green.svg)](README.md)
[![CI](https://github.com/usagi917/agoraAI/actions/workflows/ci.yml/badge.svg)](https://github.com/usagi917/agoraAI/actions/workflows/ci.yml)
[![License: AGPL-3.0](https://img.shields.io/badge/License-AGPL--3.0-blue.svg)](LICENSE)
[![Python 3.11+](https://img.shields.io/badge/python-3.11%2B-blue.svg)](backend/pyproject.toml)
[![Node.js 20+](https://img.shields.io/badge/node-20%2B-339933.svg)](frontend/package.json)

> A multi-agent analysis app that runs social reaction simulation, council debate, and Decision Brief generation in one UI. The `frontend` is built with Vue 3 + Vite, and the `backend` is built with FastAPI + async SQLAlchemy.

## Quick Start

```bash
cp .env.example .env
# Set OPENAI_API_KEY if you want live execution
docker compose up --build
```

- App: http://localhost:3000
- API docs: http://localhost:8000/docs
- Health check: http://localhost:8000/health

The app still boots without `OPENAI_API_KEY`. Live execution is disabled, but you can still browse sample results and inspect the UI.

## What It Does

- Starts analysis from four guided question flows:
  - market entry
  - product acceptance
  - policy impact
  - option comparison
- Accepts `.txt`, `.md`, and `.pdf` uploads alongside free-form prompts and stores them per project.
- Runs five execution presets:
  - `quick`
  - `standard`
  - `deep`
  - `research`
  - `baseline`
- Streams live progress through SSE with activity feed, social response views, and a 3D graph.
- Shows Decision Briefs, scenario comparison, agreement heatmaps, propagation analysis, transcripts, reruns, and follow-up questions on the results page.
- Generates, browses, and forks population datasets.
- Exposes sample runs that work without an API key.

## Execution Pipeline

| Preset | Backend phases | Purpose |
| --- | --- | --- |
| `quick` | `society_pulse -> synthesis` | Fast first-pass judgment |
| `standard` | `society_pulse -> council -> synthesis` | Default analysis flow |
| `deep` | `society_pulse -> multi_perspective -> council -> pm_analysis -> synthesis` | Deeper analysis with PM review |
| `research` | `society_pulse -> issue_mining -> multi_perspective -> intervention -> synthesis` | Issue mining and intervention comparison |
| `baseline` | dedicated baseline execution | Single-LLM baseline |

Legacy mode names are normalized internally. For example, `unified -> standard`, `society_first -> research`, and `single -> quick`.

The current implementation works like this:

- Society Pulse builds a large synthetic population from config, selects 100 agents, and runs activation plus evaluation.
- Council selects up to 6 citizen representatives and 4 experts, then runs a 3-round debate.
- Synthesis combines social responses and council output into a Decision Brief.

## Screens

| Route | Screen | Main contents |
| --- | --- | --- |
| `/` | LaunchPad | template selection, guided wizard, prompt input, file upload, recent runs |
| `/sim/:id` | Live Simulation | SSE progress, Simulation Progress, Colony / Society views, 3D graph |
| `/sim/:id/results` | Results | Decision Brief, scenario comparison, propagation analysis, transcript, follow-ups |
| `/sample/:id` | Sample Result | sample result viewer |
| `/populations` | Populations | population generation, listing, forking |

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
        ORCH["Simulation dispatcher / unified orchestrator"]
        SOC["Society services"]
        LLM["Multi-LLM routing"]
        DB["Async SQLAlchemy"]
    end

    subgraph Data["Data / Infra"]
        SQLITE["SQLite (local default)"]
        POSTGRES["PostgreSQL (Compose)"]
        REDIS["Redis (Compose)"]
        CFG["config/*.yaml + templates/ja/*.yaml"]
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
```

Notes:

- The production `frontend` container is served by Nginx and proxies `/api` plus SSE to `backend:8000`.
- On startup, the `backend` seeds templates from `templates/ja/*.yaml`.
- SQLite is the default local database. Docker Compose uses PostgreSQL.

## API Quick Start

### 1. Create a simulation from a prompt

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

### 2. Stream progress over SSE

```bash
curl -N http://localhost:8000/simulations/SIM_ID/stream
```

### 3. Fetch the final report

```bash
curl http://localhost:8000/simulations/SIM_ID/report
```

### Key endpoints

```text
GET  /health
GET  /templates

POST /projects
GET  /projects/{project_id}
POST /projects/{project_id}/documents
GET  /projects/{project_id}/documents

POST /simulations
GET  /simulations
GET  /simulations/samples
GET  /simulations/samples/{sample_id}
GET  /simulations/{sim_id}
GET  /simulations/{sim_id}/stream
GET  /simulations/{sim_id}/graph
GET  /simulations/{sim_id}/graph/history
GET  /simulations/{sim_id}/report
GET  /simulations/{sim_id}/timeline
POST /simulations/{sim_id}/followups
POST /simulations/{sim_id}/rerun
GET  /simulations/{sim_id}/backtest
POST /simulations/{sim_id}/backtest

GET  /society/populations
POST /society/populations/generate
GET  /society/populations/{pop_id}
POST /society/populations/{pop_id}/fork
GET  /society/simulations/{sim_id}/activation
GET  /society/simulations/{sim_id}/meeting
GET  /society/simulations/{sim_id}/evaluation
GET  /society/simulations/{sim_id}/narrative
GET  /society/simulations/{sim_id}/demographics
GET  /society/simulations/{sim_id}/propagation
GET  /society/simulations/{sim_id}/social-graph
GET  /society/simulations/{sim_id}/agents
GET  /society/simulations/{sim_id}/agents/{agent_id}
GET  /society/simulations/{sim_id}/transcript
GET  /society/simulations/{sim_id}/conversations

GET  /runs
POST /runs
GET  /runs/{run_id}
GET  /runs/{run_id}/stream
GET  /runs/{run_id}/report
GET  /runs/{run_id}/timeline
GET  /runs/{run_id}/events
GET  /runs/{run_id}/graph
POST /runs/{run_id}/followups
POST /runs/{run_id}/rerun

GET  /admin/costs
GET  /admin/quality-metrics
```

## Local Development

### Minimal setup

`.env.example` points to SQLite by default, so you can boot the backend without extra infrastructure.

```bash
cp .env.example .env

cd backend
uv sync --extra dev
uv run uvicorn src.app.main:app --reload --host 0.0.0.0 --port 8000
```

In another terminal:

```bash
cd frontend
pnpm install
pnpm dev
```

- Frontend dev server: http://localhost:5173
- Vite proxies `/api` to `http://localhost:8000`

### With PostgreSQL and Redis

```bash
docker compose up -d postgres redis
```

To match the Docker stack more closely, set `.env` like this:

```bash
DATABASE_URL=postgresql+asyncpg://agentai:agentai@localhost:5432/agentai
REDIS_URL=redis://localhost:6379/0
```

## Tests

```bash
# backend
cd backend
uv run pytest -q

# frontend unit
cd frontend
pnpm build
pnpm test:unit

# frontend e2e
pnpm exec playwright install --with-deps chromium
pnpm test:e2e
```

CI runs backend tests, frontend build, frontend unit tests, and Playwright E2E.

## Configuration

### Main environment variables

| Variable | Purpose |
| --- | --- |
| `OPENAI_API_KEY` | live execution with the OpenAI provider |
| `GOOGLE_API_KEY` | Gemini provider |
| `ANTHROPIC_API_KEY` | Anthropic provider |
| `LLM_MODEL` | base model setting; task-specific overrides live in `config/models.yaml` |
| `DATABASE_URL` | database connection; `.env.example` uses SQLite, Compose uses PostgreSQL |
| `REDIS_URL` | Redis connection; enabled in Compose |
| `BACKEND_HOST` / `BACKEND_PORT` | FastAPI bind settings |
| `VITE_API_BASE_URL` | frontend API base URL |
| `COGNITIVE_MODE` | `legacy` or `advanced` |
| `MAX_ACTIVE_AGENTS` | max cognitive agents |
| `MAX_CONCURRENT_AGENTS` | concurrent cognitive cycles |
| `MAX_CONCURRENT_COLONIES` | concurrent multi-perspective / colony jobs |
| `LLM_CACHE_TTL` | cache TTL in seconds |

### Main config files

| File | Purpose |
| --- | --- |
| `config/models.yaml` | provider and task-level model selection |
| `config/llm_providers.yaml` | OpenAI / Gemini / Anthropic definitions and fallback order |
| `config/population_mix.yaml` | population size, attribute distributions, per-layer provider weights |
| `config/cognitive.yaml` | cognition, communication, and scheduling settings |
| `config/graphrag.yaml` | knowledge graph extraction config |
| `templates/ja/*.yaml` | analysis templates used by LaunchPad |

### Templates

On startup, YAML files under `templates/ja` are loaded as templates. The current repo includes:

- `business_analysis`
- `market_entry`
- `policy_impact`
- `policy_simulation`
- `scenario_exploration`

There are also helper templates under `templates/ja/pm_board` and `templates/ja/experts`.

## Repository Layout

```text
.
├── backend/
│   ├── src/app/api/routes/      # FastAPI routes
│   ├── src/app/services/        # orchestration, society, cognition, GraphRAG
│   ├── src/app/llm/             # LLM clients and adapters
│   ├── tests/                   # pytest
│   └── pyproject.toml
├── frontend/
│   ├── src/pages/               # LaunchPad / Simulation / Results / Sample / Populations
│   ├── src/components/          # UI components
│   ├── src/stores/              # Pinia stores
│   ├── tests/e2e/               # Playwright
│   └── package.json
├── config/                      # YAML configuration
├── templates/                   # analysis templates
├── sample_results/              # sample runs without API keys
├── docker-compose.yml
├── README.md
└── README.en.md
```

## Contributing

See [CONTRIBUTING.md](CONTRIBUTING.md).

## License

[AGPL-3.0](LICENSE)
