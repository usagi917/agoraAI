# Agent AI

[![日本語](https://img.shields.io/badge/lang-日本語-green.svg)](README.md)
[![CI](https://github.com/usagi917/agoraAI/actions/workflows/ci.yml/badge.svg)](https://github.com/usagi917/agoraAI/actions/workflows/ci.yml)
[![License: AGPL-3.0](https://img.shields.io/badge/License-AGPL--3.0-blue.svg)](LICENSE)
[![Python 3.11+](https://img.shields.io/badge/python-3.11%2B-blue.svg)](backend/pyproject.toml)
[![Node.js 20+](https://img.shields.io/badge/node-20%2B-339933.svg)](frontend/package.json)

> A multi-agent analysis app that turns one question into synthetic population reactions, council debate, and a final Decision Brief.

## What It Is

- Start from a free-form prompt, one of four guided question builders, or seeded analysis templates on the LaunchPad.
- The API accepts five presets: `quick`, `standard`, `deep`, `research`, and `baseline`; the UI exposes `standard` and `research`.
- Attach `.txt`, `.md`, and `.pdf` files to a project and run evidence-aware analysis on top of them.
- Follow progress live over SSE with activity feed, social response views, conversations, and graph updates.
- Review Decision Briefs, scenario comparison, propagation analysis, transcripts, the graph panel (Social / Knowledge Graph, collapsible), reruns, and Codex Review Agent questions on the results page.
- Use `/validate/:id?` to check stance-distribution accuracy against holdout survey data.
- Generate, inspect, and fork synthetic populations from `/populations`.
- Start Decision Lab from `/compare`, then run two scenarios against the same population side by side to compare opinion shifts, coalition changes, and audit trails.
- Theater UI shows debate cards, live dialogue streams, and real-time stance shifts during simulation.
- `config/` and `templates/` centralize providers, cognitive settings, population mix, and LaunchPad templates.

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

- Users choose a question, guided builder, file attachments, and analysis mode on the LaunchPad.
- The backend normalizes API input to `quick`, `standard`, `deep`, `research`, or `baseline`, then runs only the required phases.
- Runtime state is streamed over SSE, and frontend Pinia stores reflect it in the Activity Feed, social graph, dialogue views, and Theater UI.
- Results can be reused as Decision Briefs, scenario comparisons, propagation analysis, transcripts, and follow-up questions.

## Screens And Workflow

| Route | Purpose | Main contents |
| --- | --- | --- |
| `/` | LaunchPad | guided question builders, free-form prompt, file upload, analysis mode selection, run history |
| `/sim/:id` | Live Simulation | SSE progress, activity feed, social response views, conversations, live graph, Theater UI (debate cards, dialogue stream) |
| `/sim/:id/results` | Results | Decision Brief, scenario comparison, propagation, transcript, graph panel (Social / Knowledge Graph, collapsible), Codex Review |
| `/validate/:id?` | Validation | holdout survey topic selection, diagnostic simulation, distribution comparison, hit/partial/miss verdict |
| `/populations` | Populations | generation, listing, detail view, forking |
| `/compare` | Compare Setup | configure two scenarios, execution presets, and population settings for comparison |
| `/scenario/:id` | Decision Lab | scenario pair comparison, opinion shift table, coalition map, audit timeline |

The main execution flow has three stages:

1. `Society Pulse`
Build a large synthetic population from config and aggregate reactions from selected agents.
2. `Council`
Pick citizen representatives and experts, then run a structured multi-round debate.
3. `Synthesis`
Combine social signals, debate output, and quality metadata into a Decision Brief and comparable scenarios.

### Presets

These presets are available through the API. The LaunchPad advanced settings expose `standard` and `research` for day-to-day use.

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
| Validation API against holdout surveys | `backend/src/app/api/routes/validation.py`, `backend/src/app/evaluation/diagnostic.py` |
| Execution preset definitions and legacy mode mapping | `backend/src/app/models/simulation.py` |
| Dispatch between `baseline` and unified execution | `backend/src/app/services/simulation_dispatcher.py` |
| `Society Pulse -> Council -> Synthesis` orchestration | `backend/src/app/services/unified_orchestrator.py` |
| Synthetic populations, social networks, reactions, propagation, evaluation | `backend/src/app/services/society/` |
| LLM task routing, provider adapters, fallback | `backend/src/app/llm/` |
| Frontend route definitions | `frontend/src/router.ts` |
| REST API client and TypeScript types | `frontend/src/api/client.ts` |
| SSE subscription and live state updates | `frontend/src/composables/useSimulationSSE.ts` |
| Stores for execution state, graphs, society data, and Decision Lab | `frontend/src/stores/` |
| Main and validation screens | `frontend/src/pages/` |
| Visualization and result components | `frontend/src/components/` |

## Architecture

### System Overview

```mermaid
flowchart LR
    User["User"] --> Frontend

    subgraph Frontend["Frontend"]
        LaunchPad["LaunchPad / Compare / Populations / Validate"]
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
        LLM["OpenAI-compatible APIs / Anthropic adapter / Ollama"]
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

## Prerequisites

- Python 3.11+
- uv
- Node.js 20+
- pnpm
- Docker / Docker Compose if you want PostgreSQL, Redis, or full container startup

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

### One-command local startup

After installing dependencies, you can start the backend and frontend together.

```bash
cp .env.example .env

cd backend
uv sync

cd ../frontend
pnpm install

cd ..
./scripts/dev.sh
```

- Backend: `http://localhost:8000`
- Frontend: `http://localhost:5173`
- Custom ports: `./scripts/dev.sh --backend-port 8001 --frontend-port 5174`

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
uv sync
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
- The Docker frontend serves nginx on `:3000` and forwards `/api` to the backend
- nginx disables buffering for the SSE endpoint `/api/simulations/:id/stream`

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
| Population mix | `config/population_mix.yaml` |
| GraphRAG / grounding | `config/graphrag.yaml`, `config/grounding/` |
| LaunchPad templates | `templates/ja/*.yaml` |
| Codex Review settings | `.env` variables `CODEX_REVIEW_ENABLED`, `CODEX_BIN`, `CODEX_REVIEW_TRANSPORT`, `CODEX_REVIEW_TIMEOUT_SECONDS`, `CODEX_REVIEW_MOCK`, `CODEX_REVIEW_MAX_CONTEXT_CHARS`, `CODEX_REVIEW_WORKDIR` |

To use the AI check feature, install the Codex CLI, log in, start the backend with `CODEX_REVIEW_ENABLED=true`, and let the backend launch `codex app-server --listen stdio://` over stdio. v1 uses stdio only and limits Codex to read-only checks against completed reports. The legacy `AGORAAI_CODEX_*` variables are still read as compatibility aliases.

## Main API

| Method | Endpoint | Purpose |
| --- | --- | --- |
| `GET` | `/health` | service status |
| `GET` | `/templates` | list templates |
| `POST` | `/projects` | create a project for attachments |
| `GET` | `/projects/{project_id}` | get project details |
| `POST` | `/projects/{project_id}/documents` | add documents |
| `GET` | `/projects/{project_id}/documents` | list attached documents |
| `GET` | `/validation/topics` | list holdout validation topics |
| `POST` | `/simulations` | create a simulation |
| `GET` | `/simulations` | list simulations |
| `GET` | `/simulations/{sim_id}` | get status |
| `GET` | `/simulations/{sim_id}/stream` | SSE progress |
| `GET` | `/simulations/{sim_id}/timeline` | timeline data |
| `GET` | `/simulations/{sim_id}/graph` | latest graph |
| `GET` | `/simulations/{sim_id}/graph/history` | graph history by round |
| `GET` | `/simulations/{sim_id}/report` | final report |
| `GET` | `/simulations/{sim_id}/validation-report` | distribution comparison report against holdout surveys |
| `GET` | `/simulations/{sim_id}/colonies` | colony-level execution state |
| `GET/POST` | `/simulations/{sim_id}/backtest` | read or run backtests |
| `GET` | `/simulations/{sim_id}/audit-trail` | audit trail for scenario comparison |
| `GET` | `/codex/health` | Codex App Server connection status |
| `POST` | `/simulations/{sim_id}/codex-review` | ask Codex review questions against a completed report |
| `POST` | `/simulations/{sim_id}/rerun` | rerun with the same conditions |
| `POST` | `/scenario-pairs` | start a scenario comparison |
| `GET` | `/scenario-pairs/{scenario_pair_id}` | get scenario comparison status |
| `GET` | `/scenario-pairs/{scenario_pair_id}/comparison` | get comparison output |
| `POST` | `/populations/{population_id}/snapshot` | create a population snapshot for scenario comparison |

### Runs / legacy compatibility

| Method | Endpoint | Purpose |
| --- | --- | --- |
| `GET` | `/runs` | list runs |
| `POST` | `/runs` | create a run |
| `GET` | `/runs/{run_id}` | get run status |
| `GET` | `/runs/{run_id}/report` | get run report |
| `GET` | `/runs/{run_id}/timeline` | get run timeline |
| `GET` | `/runs/{run_id}/events` | get run events |
| `GET` | `/runs/{run_id}/graph` | get run graph |
| `POST` | `/runs/{run_id}/rerun` | rerun a run |

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
| `GET` | `/society/simulations/{sim_id}/evaluation/summary` | evaluation summary |
| `GET` | `/society/simulations/{sim_id}/narrative` | narrative output |
| `GET` | `/society/simulations/{sim_id}/demographics` | demographic summary |
| `GET` | `/society/simulations/{sim_id}/propagation` | propagation data |
| `GET` | `/society/simulations/{sim_id}/social-graph` | society graph |
| `GET` | `/society/simulations/{sim_id}/population-network` | full population network (compact form for rendering) |
| `GET` | `/society/simulations/{sim_id}/agents` | list agents |
| `GET` | `/society/simulations/{sim_id}/agents/{agent_id}` | agent details |
| `GET` | `/society/simulations/{sim_id}/transcript` | transcript data |
| `GET` | `/society/simulations/{sim_id}/conversations` | conversation data |
| `GET` | `/society/simulations/{sim_id}/time-axis` | time-axis analysis |
| `GET` | `/society/simulations/{sim_id}/ensemble` | ensemble output |
| `GET` | `/society/simulations/{sim_id}/report` | society report |
| `GET` | `/admin/costs` | token and cost aggregation |
| `GET` | `/admin/quality-metrics` | quality and fallback aggregation |

## Testing

CI runs the following:

```bash
cd backend
uv sync
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

### Optional quality checks

```bash
cd backend
uv run ruff check src
uv run deptry .
```

```bash
cd frontend
pnpm check:dead
```

## Repository Layout

```text
.
├── backend/        # FastAPI API, SSE, orchestration, society services, tests
├── frontend/       # Vue 3 + Vite UI, Pinia stores, charts, E2E tests
├── config/         # provider / model / cognitive / profile / grounding settings
├── templates/      # seeded LaunchPad templates and expert / PM personas
├── experiments/    # validation experiments and aggregation scripts
├── evaluation/     # baseline snapshots
├── docs/           # focused implementation notes
├── amplifier/      # separate Amplifier package checkout; not part of Agent AI runtime
├── data/           # local runtime data
├── scripts/dev.sh  # local backend + frontend launcher
├── DESIGN.md       # extra design notes
└── CONTRIBUTING.md
```

### Folder Notes

| Folder | Integrated into this README |
| --- | --- |
| `backend/` | FastAPI startup, DB initialization, template seeding, SSE, simulation/runs/projects/society/admin APIs, SQLite/PostgreSQL switching |
| `frontend/` | LaunchPad, Live Simulation, Results, Populations, Compare Setup, Decision Lab, `/api` proxy, Vitest, Playwright |
| `config/` | provider/model settings, fallback, GraphRAG, population mix, cognitive/communication/scheduling, grounding data |
| `templates/` | `business_analysis`, `market_entry`, `policy_impact`, `policy_simulation`, `scenario_exploration`, expert/PM personas |
| `experiments/` | `swarm_validation` runner, aggregation, and HTML report |
| `docs/` | focused implementation and bug-fix notes |
| `amplifier/` | standalone Microsoft Amplifier uv package. It is not required by Agent AI's Docker Compose or FastAPI/Vue runtime |

## More Docs

- Design notes: [DESIGN.md](DESIGN.md)
- Contributing: [CONTRIBUTING.md](CONTRIBUTING.md)
- Code of conduct: [CODE_OF_CONDUCT.md](CODE_OF_CONDUCT.md)
- Frontend README: [frontend/README.md](frontend/README.md)
- Amplifier README: [amplifier/README.md](amplifier/README.md)

## License

Agent AI is AGPL-3.0. See [LICENSE](LICENSE) for details.

`amplifier/` is a bundled separate project and follows its own [amplifier/LICENSE](amplifier/LICENSE).
