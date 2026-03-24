# Agent AI

[![日本語](https://img.shields.io/badge/lang-日本語-green.svg)](README.md)
[![License: AGPL-3.0](https://img.shields.io/badge/License-AGPL--3.0-blue.svg)](LICENSE)
[![Python 3.11+](https://img.shields.io/badge/python-3.11%2B-blue.svg)](backend/pyproject.toml)
[![Node.js 20+](https://img.shields.io/badge/node-20%2B-339933.svg)](frontend/package.json)
[![Docker Compose](https://img.shields.io/badge/docker-compose-2496ED.svg)](docker-compose.yml)

> A FastAPI + Vue 3 application that defaults to `unified` mode and turns prompts or `.txt` / `.md` / `.pdf` files into social reactions, council deliberation, and a Decision Brief.

[Quick Start](#quick-start) · [Key Features](#key-features) · [Execution Modes](#execution-modes) · [Local Development](#local-development) · [API](#api) · [Configuration](#configuration)

## What It Is

Agent AI is a simulation app that takes a research question or hypothesis and runs it through broad social-response sampling, structured council debate, and decision-oriented synthesis in one flow.

- LaunchPad live runs are fixed to `unified` mode and use `evidence_mode: strict`
- Inputs can be prompt-only or multiple `.txt` / `.md` / `.pdf` attachments
- While a run is active, progress is streamed over SSE, and the results workspace exposes Decision Briefs, scenario comparison, agreement heatmaps, cognitive views, and a 3D graph
- The API also supports `pipeline`, `single`, `swarm`, `hybrid`, `pm_board`, `society`, `society_first`, and `meta_simulation`
- On startup the backend seeds `templates/ja/*.yaml` into the database so the built-in templates are immediately usable

## Quick Start

Docker Compose is the fastest way to run the full stack.

```bash
cp .env.example .env
# Set OPENAI_API_KEY=... in .env if you want live execution enabled
docker compose up --build
```

- App: `http://localhost:3000`
- FastAPI docs: `http://localhost:8000/docs`
- The checked-in default provider is `openai` in `config/models.yaml`

Notes:

- If `OPENAI_API_KEY` is missing while the provider is `openai`, the UI still loads but live execution is disabled and `POST /simulations` returns 400
- Offline demo routes under `/sample/:id` only work when `sample_results/*.json` is present

## Key Features

### Default Flow: `unified`

| Phase | Responsibility | Main Output |
| --- | --- | --- |
| `society_pulse` | Sample broad social reactions at population scale | Aggregation, evaluation, social summary |
| `council` | Run a 10-person named council through 3 rounds of deliberation | Arguments, counters, synthesis notes |
| `synthesis` | Build a ReACT-style decision report | Decision Brief, structured report sections, agreement score |

### UI

- `/` LaunchPad gives you 4 guided question wizards, template selection, free-form input, file upload, and recent runs
- `/sim/:id` shows live SSE progress, Colony status, activity feed, opinion distribution, and the live social graph
- `/sim/:id/results` combines the report with Decision Briefs, scenario comparison, probability charts, agreement heatmaps, memory views, ToM views, social-network views, and the KG explorer
- `/populations` lets you generate, inspect, and fork 1,000-person population snapshots

## Execution Modes

| Mode | Purpose |
| --- | --- |
| `unified` | Default path. Runs `society_pulse -> council -> synthesis` as one integrated workflow |
| `pipeline` | Runs `single -> swarm -> pm_board` in sequence |
| `single` | Produces a report from a single-run world-model workflow |
| `swarm` | Runs multiple Colonies in parallel and aggregates scenario spread plus agreement |
| `hybrid` | Uses the `swarm` API surface with a Deep / Shallow Colony mix |
| `pm_board` | Reviews a product or business idea with PM personas plus a chief synthesis |
| `society` | Focuses on population generation and social-dynamics simulation |
| `society_first` | Starts with broad social reaction, then drills down with Issue Colonies and backtests |
| `meta_simulation` | Runs higher-level multi-cycle orchestration |

LaunchPad only starts `unified` directly. The other modes are mainly intended for API-driven use.

## Main Screens

| Route | Screen | Role |
| --- | --- | --- |
| `/` | LaunchPad | Template selection, question wizard, prompt entry, document upload, recent runs |
| `/sim/:id` | Live Simulation | SSE progress, phase labels, Colony status, live social graph |
| `/sim/:id/results` | Results | Decision Brief, report, comparison views, cognitive views, follow-up flow |
| `/sample/:id` | Sample Result | Optional sample rendering backed by `sample_results/*.json` |
| `/populations` | Population Explorer | Inspect population data for society-oriented flows |

Legacy `/run/:id` and `/swarm/:id` routes redirect to the new route structure.

## API

This is the minimal prompt-only execution flow. The backend auto-creates a project if you omit `project_id`.

1. Create a simulation

```bash
curl -X POST http://localhost:8000/simulations \
  -H "Content-Type: application/json" \
  -d '{
    "mode": "unified",
    "template_name": "business_analysis",
    "execution_profile": "standard",
    "prompt_text": "Analyze whether to enter the EV battery market",
    "evidence_mode": "strict"
  }'
```

2. Stream progress

```bash
curl -N http://localhost:8000/simulations/SIM_ID/stream
```

3. Fetch the report

```bash
curl http://localhost:8000/simulations/SIM_ID/report
```

If you want to attach documents, create a project first and then upload files.

```bash
curl -X POST "http://localhost:8000/projects?name=market-entry"

curl -X POST "http://localhost:8000/projects/PROJECT_ID/documents" \
  -F "file=@/absolute/path/to/evidence.md"
```

### Key Endpoints

```text
GET  /health
GET  /templates

POST /projects
GET  /projects/{project_id}
POST /projects/{project_id}/documents
GET  /projects/{project_id}/documents

POST /simulations
GET  /simulations
GET  /simulations/{sim_id}
GET  /simulations/{sim_id}/stream
GET  /simulations/{sim_id}/graph
GET  /simulations/{sim_id}/graph/history
GET  /simulations/{sim_id}/report
GET  /simulations/{sim_id}/colonies
GET  /simulations/{sim_id}/timeline
POST /simulations/{sim_id}/followups
POST /simulations/{sim_id}/feedback
POST /simulations/{sim_id}/rerun

GET  /society/populations
POST /society/populations/generate
GET  /admin/costs
GET  /admin/quality-metrics
```

Legacy `/runs` and `/swarms` routers still exist for backward compatibility, but new integrations should target `/simulations`.

## Local Development

Prerequisites:

- Python 3.11+
- `uv`
- Node.js 20+
- `pnpm`
- Docker Compose

If you only want infrastructure services:

```bash
docker compose up -d postgres redis
```

Backend:

```bash
cd backend
uv sync --extra dev
uv run uvicorn src.app.main:app --reload --host 0.0.0.0 --port 8000
```

Frontend:

```bash
cd frontend
pnpm install
pnpm dev
```

- Frontend dev server: `http://localhost:5173`
- If you leave `VITE_API_BASE_URL` unset, Vite proxies `/api` to `http://localhost:8000`
- The Docker frontend uses Nginx to proxy `/api` to the backend container

If you do not want local PostgreSQL, you can switch `.env` `DATABASE_URL` to an SQLite `aiosqlite` URL.

## Tests And Checks

Backend:

```bash
cd backend
uv run pytest
```

Frontend:

```bash
cd frontend
pnpm build
pnpm test:unit
pnpm exec playwright install chromium
pnpm test:e2e
```

## Configuration

### Main Environment Variables

| Variable | Purpose |
| --- | --- |
| `OPENAI_API_KEY` | Enables live execution in the default OpenAI-backed setup |
| `GOOGLE_API_KEY` | Required when you use Gemini-style provider entries from `config/llm_providers.yaml` |
| `ANTHROPIC_API_KEY` | Required for Anthropic provider entries |
| `DATABASE_URL` | PostgreSQL by default; can be switched to SQLite (`aiosqlite`) |
| `LLM_MODEL` | Fallback model when `config/models.yaml` does not override a task |
| `COGNITIVE_MODE` | Switch between `legacy` and `advanced` |
| `MAX_CONCURRENT_COLONIES` | Upper bound for Swarm-style Colony parallelism |
| `MAX_CONCURRENT_AGENTS` | Concurrency limit for cognitive agents |
| `MAX_ACTIVE_AGENTS` | Upper bound for total active cognitive agents |
| `VITE_API_BASE_URL` | Override the frontend API base URL when needed |

### Main Config Files

| File | Purpose |
| --- | --- |
| `.env.example` | Environment variable template |
| `config/models.yaml` | Task-level model routing and default provider |
| `config/llm_providers.yaml` | Multi-provider configuration |
| `config/swarm_profiles.yaml` | Colony counts and round counts per execution profile |
| `config/cognitive.yaml` | Cognition, memory, ToM, and Game Master settings |
| `config/graphrag.yaml` | GraphRAG extraction, deduplication, and community settings |
| `templates/ja/*.yaml` | Analysis templates used by LaunchPad and the API |
| `templates/ja/pm_board/*.yaml` | Persona templates for PM Board |

## Project Structure

```text
.
├── backend/              # FastAPI, SQLAlchemy, orchestration, tests
├── frontend/             # Vue 3, Vite, Pinia, 3D graph UI
├── config/               # models / providers / cognition / GraphRAG / profiles
├── templates/ja/         # analysis templates and PM Board templates
├── sample_results/       # optional JSON fixtures for /sample/:id
├── data/                 # local data when using SQLite
├── experiments/          # experiment scripts and validation output
├── plans/                # planning notes
├── docker-compose.yml
├── README.md
└── README.en.md
```

## Contributing

See [CONTRIBUTING.md](CONTRIBUTING.md) for workflow and toolchain rules.

## License

This project is distributed under [AGPL-3.0](LICENSE).
