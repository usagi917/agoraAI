# Agent AI

[![日本語](https://img.shields.io/badge/lang-日本語-green.svg)](README.md)
[![CI](https://github.com/usagi917/agoraAI/actions/workflows/ci.yml/badge.svg)](https://github.com/usagi917/agoraAI/actions/workflows/ci.yml)
[![License: AGPL-3.0](https://img.shields.io/badge/License-AGPL--3.0-blue.svg)](LICENSE)
[![Python 3.11+](https://img.shields.io/badge/python-3.11%2B-blue.svg)](backend/pyproject.toml)
[![Node.js 20+](https://img.shields.io/badge/node-20%2B-339933.svg)](frontend/package.json)

> A multi-agent analysis app that turns one question into synthetic population reactions, council debate, and a final Decision Brief.

## What It Is

- Start from one of four guided question templates or a free-form prompt on the LaunchPad.
- Switch between five presets: `quick`, `standard`, `deep`, `research`, and `baseline`.
- Attach `.txt`, `.md`, and `.pdf` files to a project and run evidence-aware analysis on top of them.
- Follow progress live over SSE with activity feed, social response views, conversations, and graph updates.
- Review Decision Briefs, scenario comparison, propagation analysis, transcripts, reruns, and follow-up questions on the results page.
- Generate, inspect, and fork synthetic populations from `/populations`.
- Decision Lab runs two scenarios against the same population side-by-side, comparing opinion shifts, coalition changes, and audit trails.
- Theater UI shows debate cards, live dialogue streams, and real-time stance shifts during simulation.

## 30-Second Big Picture

Agent AI takes a question and optional evidence documents, runs them through synthetic population reactions, representative and expert deliberation, and quality checks, then turns the result into a decision-ready Decision Brief.

```mermaid
flowchart LR
    Q["Question / Template / Documents"] --> L["LaunchPad<br/>Vue UI"]
    L --> A["FastAPI<br/>Simulation API"]
    A --> P["Project / Document<br/>storage + GraphRAG"]
    A --> D["Dispatcher<br/>preset normalization"]
    D --> S["Society Pulse<br/>synthetic population reactions"]
    S --> C["Council<br/>representatives + experts"]
    C --> Y["Synthesis<br/>Decision Brief generation"]
    Y --> R["Results<br/>evidence, rationale, next actions"]
    Y --> X["Decision Lab<br/>scenario comparison"]
    S -. SSE .-> V["Live Simulation<br/>progress, dialogue, social graph"]
    C -. SSE .-> V
    Y -. SSE .-> V
```

How to read it:

- Users choose a question, template, file attachments, and execution preset on the LaunchPad.
- The backend normalizes the request to `quick`, `standard`, `deep`, `research`, or `baseline`, then runs only the required phases.
- Runtime state is streamed over SSE, and frontend Pinia stores reflect it in the Activity Feed, social graph, dialogue views, and Theater UI.
- Results can be reused as Decision Briefs, scenario comparisons, propagation analysis, transcripts, and follow-up questions.

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

## Code Reading Map

| What you want to understand | Main files |
| --- | --- |
| App startup, CORS, template seeding, health check | `backend/src/app/main.py` |
| Environment variables and config YAML loading | `backend/src/app/config.py` |
| DB connection, table creation, SQLite/PostgreSQL switching | `backend/src/app/database.py` |
| API router registration | `backend/src/app/api/routes/__init__.py` |
| Simulation creation, SSE, reports, reruns | `backend/src/app/api/routes/simulations.py` |
| Execution preset definitions and legacy mode mapping | `backend/src/app/models/simulation.py` |
| Dispatch between `baseline` and unified execution | `backend/src/app/services/simulation_dispatcher.py` |
| `Society Pulse -> Council -> Synthesis` orchestration | `backend/src/app/services/unified_orchestrator.py` |
| Synthetic populations, social networks, reactions, propagation, evaluation | `backend/src/app/services/society/` |
| LLM task routing, provider adapters, fallback | `backend/src/app/llm/` |
| Frontend route definitions | `frontend/src/router.ts` |
| REST API client and TypeScript types | `frontend/src/api/client.ts` |
| SSE subscription and live state updates | `frontend/src/composables/useSimulationSSE.ts` |
| Stores for execution state, graphs, society data, and Decision Lab | `frontend/src/stores/` |
| Main screens | `frontend/src/pages/` |
| Visualization and result components | `frontend/src/components/` |

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
| `POST` | `/simulations/{sim_id}/followups` | ask follow-up questions against the result |
| `POST` | `/simulations/{sim_id}/rerun` | rerun with the same conditions |
| `POST` | `/scenario-pairs` | start a scenario comparison |

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
