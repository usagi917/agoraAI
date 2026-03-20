# Agent AI

[![日本語](https://img.shields.io/badge/lang-日本語-green.svg)](README.md)
[![License: AGPL-3.0](https://img.shields.io/badge/License-AGPL--3.0-blue.svg)](LICENSE)
[![Python 3.11+](https://img.shields.io/badge/python-3.11%2B-blue.svg)](backend/pyproject.toml)
[![Node.js 20+](https://img.shields.io/badge/node-20%2B-339933.svg)](frontend/package.json)
[![Docker Compose](https://img.shields.io/badge/docker-compose-2496ED.svg)](docker-compose.yml)

> A FastAPI + Vue 3 application that turns prompts or `.txt` / `.md` / `.pdf` documents into a world model, then drives live simulations, scenario comparison, PM-style synthesis, and 3D knowledge-graph visualization.

[Quick Start](#quick-start) · [Local Development](#local-development) · [Frontend](#frontend) · [Backend](#backend) · [Configuration](#configuration) · [API](#api)

## Overview

Agent AI is a full-stack app built with a FastAPI backend and a Vue 3 + Vite frontend. On startup it seeds `templates/ja/*.yaml` into the database, then uses prompts or uploaded documents to build a world model. During live execution it streams progress and graph diffs over SSE, and the results UI exposes reports, scenario distributions, PM Board output, cognitive state, timelines, and 3D graph history.

The standard UI launch flow always starts `pipeline`. The API can also execute `single`, `swarm`, `hybrid`, and `pm_board` directly.

### Execution Modes

| Mode | Purpose |
| --- | --- |
| `pipeline` | Default mode that runs `single -> swarm -> pm_board` in sequence |
| `single` | Runs world-building, round progression, and report generation in a single pass |
| `swarm` | Runs multiple Colonies for multi-perspective validation and aggregates scenarios plus agreement |
| `hybrid` | Multi-Colony execution exposed through the same unified API as `swarm` |
| `pm_board` | Evaluates a business or product idea with PM personas plus a Chief PM synthesis |

### Execution Profiles

Default profile values are taken from `config/swarm_profiles.yaml`.

| Profile | Single Rounds | Swarm Colonies | Swarm Rounds |
| --- | --- | --- | --- |
| `preview` | 2 | 3 | 2 |
| `standard` | 4 | 5 | 4 |
| `quality` | 6 | 8 | 6 |

## Quick Start

Bring up the full stack with Docker Compose.

```bash
docker compose up --build
```

- App: `http://localhost:3000`
- FastAPI docs: `http://localhost:8000/docs`
- Built-in sample results without an API key: `http://localhost:3000/sample/sample-business-001`, `http://localhost:3000/sample/sample-pmboard-001`
- The stack also starts without `OPENAI_API_KEY`. In that case sample browsing still works, but live simulation stays disabled in the UI

To enable live simulation as well:

```bash
OPENAI_API_KEY=sk-... docker compose up --build
```

Or create a repo-local `.env` with `OPENAI_API_KEY=...`. Docker Compose automatically picks up either the shell environment or `.env`.

The `frontend` container serves a static production-style bundle through Nginx. For hot-reload frontend work, use the local development flow below instead.

## Local Development

Prerequisites:

- Python 3.11+
- `uv`
- Node.js 20+
- `pnpm`
- Docker Desktop or Docker Compose

If you only want infrastructure services in Docker:

```bash
docker compose up postgres redis
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
- The Vite dev server proxies `/api` to `http://localhost:8000`

If you do not want PostgreSQL locally, switch `DATABASE_URL` in `.env` to an SQLite `aiosqlite` URL. The backend creates the parent directory automatically.

## Frontend

The frontend uses Vue Router + Pinia, with `3d-force-graph` and `three` for the graph surface.

| Route | Screen | What it does |
| --- | --- | --- |
| `/` | LaunchPad | Template selection, `preview` / `standard` / `quality`, prompt input, document upload, recent runs, sample result links |
| `/sim/:id` | Live Simulation | Visualizes SSE-driven progress, Colony status, activity feed, and graph diffs |
| `/sim/:id/results` | Results | Shows reports, scenario comparison, agreement heatmap, PM Board output, cognitive views, follow-up Q&A, and reruns |
| `/sample/:id` | Sample Result | Renders bundled `sample_results/*.json` through the API |

The frontend uses `VITE_API_BASE_URL` when provided and falls back to `/api` otherwise. In local development, Vite proxies `/api`; in Docker, `frontend/nginx.conf` proxies `/api` to the backend container.

## Backend

The backend is built on FastAPI + async SQLAlchemy. On startup it initializes the database and seeds templates, and `POST /simulations` creates unified Simulation records that `simulation_dispatcher.py` routes into the appropriate execution flow.

Key implementation points:

- `backend/src/app/services/pipeline_orchestrator.py`
  Runs the three-stage `single -> swarm -> pm_board` pipeline
- `backend/src/app/services/simulator.py`
  Handles single-run world building, GraphRAG, round progression, and report generation
- `backend/src/app/services/swarm_orchestrator.py`
  Handles Colony fan-out and aggregation
- `backend/src/app/services/pm_board_orchestrator.py`
  Handles PM persona analysis and Chief PM synthesis
- `config/graphrag.yaml`
  Ships with `enabled: true`, so document-backed runs can execute the GraphRAG pipeline
- `config/cognitive.yaml`
  Ships with `cognitive.mode: advanced`, which feeds the cognitive SSE events and result tabs

## Configuration

### Important Environment Variables

| Variable | Purpose |
| --- | --- |
| `OPENAI_API_KEY` | Required for live LLM-backed execution |
| `LLM_MODEL` | Fallback model when `config/models.yaml` does not override a task |
| `DATABASE_URL` | PostgreSQL by default; SQLite (`aiosqlite`) is also supported |
| `BACKEND_HOST` / `BACKEND_PORT` | Bind settings when launching `uvicorn` manually |
| `VITE_API_BASE_URL` | Explicit frontend API base URL; defaults to `/api` |
| `MAX_CONCURRENT_COLONIES` | Upper bound for parallel Colony execution |
| `MAX_CONCURRENT_AGENTS` | Concurrency cap used by the LLM client; Game Master limits mainly come from `config/cognitive.yaml` |
| `COGNITIVE_MODE` | Fallback only when `config/cognitive.yaml` does not define a mode |
| `MAX_ACTIVE_AGENTS` | Present in `.env.example`, but the current Game Master path mainly reads `config/cognitive.yaml` |
| `REDIS_URL` | Present in `.env.example` and Docker Compose, but not directly consumed by the checked-in application code |

### Main Configuration Files

| File | Purpose |
| --- | --- |
| `.env.example` | Environment template |
| `config/models.yaml` | Task-level model routing |
| `config/cognitive.yaml` | BDI, Memory, ToM, Game Master, and scheduling settings |
| `config/graphrag.yaml` | GraphRAG extraction, deduplication, and community settings |
| `config/swarm_profiles.yaml` | Colony counts and round counts per profile |
| `config/perspectives.yaml` | Perspective definitions assigned to Colonies |
| `templates/ja/*.yaml` | User-facing analysis templates |
| `templates/ja/pm_board/*.yaml` | Persona-specific PM Board templates |

## API

The recommended surface is the unified `/simulations` API.

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
GET  /simulations/{sim_id}/colonies
GET  /simulations/{sim_id}/timeline
POST /simulations/{sim_id}/followups
POST /simulations/{sim_id}/feedback
POST /simulations/{sim_id}/rerun

GET  /admin/costs
```

Legacy `/runs` and `/swarms` routers still exist for backward compatibility, but new usage should target `/simulations`.

Create a simulation:

```bash
curl -X POST http://localhost:8000/simulations \
  -H "Content-Type: application/json" \
  -d '{
    "template_name": "business_analysis",
    "execution_profile": "standard",
    "mode": "pipeline",
    "prompt_text": "Analyze a market-entry strategy for the EV battery market"
  }'
```

## Development Checks

Backend:

```bash
cd backend
uv run pytest
```

Frontend:

```bash
cd frontend
pnpm build
```

At the time of this README update there is no dedicated frontend test suite in the repo, so a successful build is the minimum verification path on the UI side.

## Project Structure

```text
.
├── backend/              # FastAPI, SQLAlchemy, orchestration, tests
├── frontend/             # Vue 3, Vite, Pinia, 3D graph UI
├── config/               # models / cognition / GraphRAG / swarm profiles
├── templates/ja/         # analysis templates and PM Board templates
├── sample_inputs/        # sample input documents
├── sample_results/       # sample outputs without an API key
├── data/                 # local data directory when using SQLite
├── docker-compose.yml
└── README.md
```

## Contributing

See [CONTRIBUTING.md](CONTRIBUTING.md) for workflow and toolchain rules.

## License

This project is distributed under [AGPL-3.0](LICENSE).
