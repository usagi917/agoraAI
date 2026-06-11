# Agent AI

[![日本語](https://img.shields.io/badge/lang-日本語-green.svg)](README.md)
[![CI](https://github.com/usagi917/agoraAI/actions/workflows/ci.yml/badge.svg)](https://github.com/usagi917/agoraAI/actions/workflows/ci.yml)
[![License: AGPL-3.0](https://img.shields.io/badge/License-AGPL--3.0-blue.svg)](LICENSE)
[![Python 3.11+](https://img.shields.io/badge/python-3.11%2B-blue.svg)](backend/pyproject.toml)
[![Node.js 20+](https://img.shields.io/badge/node-20%2B-339933.svg)](frontend/package.json)

> A multi-agent analysis app that turns one question into synthetic population reactions, expert and representative debate, and a final Decision Brief.

Agent AI helps you explore business decisions, policy impact, market entry, and future scenarios from multiple viewpoints. You enter a question in the browser, the backend runs AI agents, progress streams live, and the final screen summarizes the decision material.

## Start Here

If this is your first time using the project, follow only this order.

1. Install the required tools
   - Python 3.11+
   - uv
   - Node.js 20+
   - pnpm
   - Docker Desktop or Docker Compose, only if you want Docker startup
2. Create `.env`
3. Add `OPENAI_API_KEY`
4. Start the app
5. Open `http://localhost:5173` or `http://localhost:3000`

Basic terms:

| Term | Meaning in this project |
| --- | --- |
| backend | Python service that runs AI work, DB storage, API, and SSE streaming |
| frontend | Vue browser UI |
| `.env` | Settings file for API keys and DB URLs |
| API key | Secret string used to call AI services such as OpenAI |
| SSE | The mechanism that streams progress to the browser while a run is active |
| SQLite | Lightweight local DB. Good enough for first local runs |
| PostgreSQL / Redis | Production-style DB / cache used by Docker Compose |

## Easiest Startup

### Option A: Local Development

This is the simplest path for day-to-day development and local checks. On the first run, the helper script installs missing dependencies.

```bash
cp .env.example .env
```

Open `.env` and replace at least this value with your OpenAI API key.

```bash
OPENAI_API_KEY=sk-your-key-here
```

Start the app.

```bash
./scripts/dev.sh
```

Then open:

- UI: `http://localhost:5173`
- API docs: `http://localhost:8000/docs`
- Health check: `http://localhost:8000/health`

Press `Ctrl+C` in the terminal to stop both servers.

Custom ports:

```bash
./scripts/dev.sh --backend-port 8001 --frontend-port 5174
```

### Option B: Docker Compose

Use this when you want PostgreSQL and Redis started together with the app.

```bash
cp .env.example .env
```

Set `OPENAI_API_KEY` in `.env`, then run:

```bash
docker compose up --build
```

Then open:

- UI: `http://localhost:3000`
- API docs: `http://localhost:8000/docs`
- Health check: `http://localhost:8000/health`

In Docker, the frontend is served by nginx on `:3000`, and `/api` is forwarded to the backend.

## How To Use The UI

1. Open `http://localhost:5173`.
2. On the LaunchPad, choose a question template or write a free-form question.
3. Attach `.txt`, `.md`, or `.pdf` files if needed.
4. Choose an execution preset. If unsure, use `standard`.
5. Start the run. The app opens `/sim/:id` and shows live progress, dialogue, social reactions, and graphs.
6. After completion, open `/sim/:id/results` for the Decision Brief, Transcript, Propagation, rerun, and Codex Review.
7. To compare two options, start Decision Lab from `/compare`.

## Reading The Graphic View

On `/sim/:id`, the Live Simulation graphic view shows synthetic population members, representatives, experts, and knowledge-graph entities. As the run advances, the view adds nodes, edges, dialogue, and stance changes.

| Item | How to read it |
| --- | --- |
| Nodes | Agents, population samples, or knowledge-graph entities. Larger or labeled nodes are often central to the debate or graph structure. |
| Colors | Stances or entity types. Use the in-view legend to read support, opposition, neutral, undecided, and related states. |
| Edges | Social ties, conversations, or agent-to-entity links. Thicker lines mean stronger relationships. |
| Phase badge | Shows the current stage, such as `Society Pulse`, `Council`, or `Synthesis`. |
| agents / edges | Current visible node and connection counts. These can grow while a run is active. |

Basic operations:

- Click a node to open details for that agent or entity.
- Hover an edge to see relation type, endpoints, and strength.
- Click an edge to inspect linked conversations and interactions.
- Click the background to clear the current selection.
- Use the mouse wheel or trackpad to zoom, and drag to pan.

Use the `⚙` control to tune graph physics. If nodes overlap, increase repulsion or node spacing. If the graph spreads too far, reduce link distance. Use reset to return to defaults.

When layer buttons appear, they toggle what is visible.

| Button | Meaning |
| --- | --- |
| `P` | Full population layer. Shows the wider population distribution as dots, not only selected representatives. |
| `S` | Social edges. Shows social connections between agents. |
| `K` | Knowledge graph. Shows entities and relations extracted from documents and analysis. |
| `L` | Agent-to-entity links. Shows how agents connect to knowledge-graph items. |

Suggested reading flow:

- Start with the color distribution to see the broad support, opposition, and neutral balance.
- Then click large or highly connected nodes to see which viewpoints are shaping the debate.
- Click edges to inspect conversations inside aligned or conflicting groups.
- Enable `K` and `L` when you want to trace which people, issues, companies, or policies are influencing agent judgments.

## What It Can Do

- Start from five LaunchPad templates:
  - `business_analysis`
  - `market_entry`
  - `policy_impact`
  - `policy_simulation`
  - `scenario_exploration`
- Choose `quick`, `standard`, `deep`, `research`, or `baseline` presets.
- Save attached documents to a project and use them as evidence.
- Inspect synthetic population reactions, representative and expert debate, opinion distributions, and social graphs.
- Compare option A and option B against the same population in Decision Lab.
- Generate, inspect, and fork populations from `/populations`.
- Enable Codex CLI integration to ask review questions against completed reports.

## Big Picture

```mermaid
flowchart LR
    Q["Question / Template / Documents"] --> F["Frontend<br/>Vue + Vite"]
    F --> A["Backend<br/>FastAPI"]
    A --> P["Project / Document<br/>storage + GraphRAG"]
    A --> D["Dispatcher<br/>preset normalization"]
    D --> S["Society Pulse<br/>synthetic population reactions"]
    S --> C["Council<br/>representatives + experts"]
    C --> B["Synthesis<br/>Decision Brief"]
    B --> R["Results<br/>evidence, rationale, next actions"]
    B --> L["Decision Lab<br/>scenario comparison"]
    S -. SSE .-> F
    C -. SSE .-> F
    B -. SSE .-> F
```

The execution flow has three main stages.

| Stage | What happens |
| --- | --- |
| Society Pulse | Build a synthetic population from config and aggregate representative reactions. |
| Council | Citizen representatives and experts debate across multiple rounds. |
| Synthesis | Combine reactions, debate, and quality metadata into a Decision Brief. |

## Screens

| URL | Purpose |
| --- | --- |
| `/` | LaunchPad. Choose the question, template, files, and preset |
| `/sim/:id` | Live Simulation. Progress, dialogue, social reactions, and graphs |
| `/sim/:id/results` | Results. Decision Brief, Transcript, Propagation, rerun, Codex Review |
| `/populations` | Populations. Generate, list, inspect, and fork populations |
| `/compare` | Compare Setup. Start a two-scenario comparison |
| `/scenario/:id` | Decision Lab. Comparison output, opinion shifts, coalition map, audit timeline |

## Presets

| Preset | Main phases | Use when |
| --- | --- | --- |
| `quick` | `society_pulse -> synthesis` | You need a fast first read |
| `standard` | `society_pulse -> council -> synthesis` | You are unsure which preset to choose |
| `deep` | `society_pulse -> multi_perspective -> council -> pm_analysis -> synthesis` | You want deeper multi-perspective and PM analysis |
| `research` | `society_pulse -> issue_mining -> multi_perspective -> intervention -> synthesis` | You care most about issue mining and intervention comparison |
| `baseline` | single-LLM baseline | You want to compare against the multi-agent flow |

Legacy mode names are normalized internally. Examples: `unified -> standard`, `society_first -> research`, `single -> quick`.

## Configuration

For first use, you usually only need `.env`. Look at `config/` and `templates/` only when you want detailed behavior changes.

| Goal | File or folder |
| --- | --- |
| Add API keys | `.env` |
| Use SQLite for local DB | `DATABASE_URL` in `.env` |
| Use PostgreSQL | `DATABASE_URL` in `.env` and `docker compose up -d postgres redis` |
| Change default provider / model | `config/models.yaml` |
| Change OpenAI / Gemini / Anthropic fallback | `config/llm_providers.yaml` |
| Tune execution profiles | `config/swarm_profiles.yaml` |
| Tune population and network settings | `config/population_mix.yaml` |
| Tune cognitive, communication, and scheduling settings | `config/cognitive.yaml` |
| Tune GraphRAG / grounding | `config/graphrag.yaml`, `config/grounding/` |
| Change LaunchPad templates | `templates/ja/*.yaml` |

The `.env.example` default DB is SQLite.

```bash
DATABASE_URL=sqlite+aiosqlite:///./data/db.sqlite3
```

To use PostgreSQL and Redis locally:

```bash
docker compose up -d postgres redis
```

Then set `.env`:

```bash
DATABASE_URL=postgresql+asyncpg://agentai:agentai@localhost:5432/agentai
REDIS_URL=redis://localhost:6379/0
```

## Codex Review

Codex Review is an optional feature that asks Codex CLI to perform read-only checks against completed reports. It is not required for normal simulations.

Install and log in to Codex CLI, then set:

```bash
CODEX_REVIEW_ENABLED=true
CODEX_BIN=codex
CODEX_REVIEW_TRANSPORT=stdio
CODEX_REVIEW_TIMEOUT_SECONDS=60
CODEX_REVIEW_WORKDIR=/tmp/agora_codex_review_empty
```

v1 uses only the stdio transport via `codex app-server --listen stdio://`. Some legacy `AGORAAI_CODEX_*` variables are still accepted as compatibility aliases.

## Development Commands

This repository uses `pnpm` for Node.js work and `uv` for Python work. Do not use `npm`, `yarn`, or `pip`.

### Backend

```bash
cd backend
uv sync --extra dev
uv run uvicorn src.app.main:app --reload --host 0.0.0.0 --port 8000
```

Tests:

```bash
cd backend
uv run pytest -q
```

Optional quality checks:

```bash
cd backend
uv run ruff check src
uv run deptry .
```

### Frontend

```bash
cd frontend
pnpm install
pnpm dev
```

Build and tests:

```bash
cd frontend
pnpm build
pnpm test:unit
pnpm exec playwright install --with-deps chromium
pnpm test:e2e
```

Dead-file and dependency check:

```bash
cd frontend
pnpm check:dead
```

## Minimal API Example

Start the backend first.

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

Use the returned `id` as `SIM_ID` to watch progress.

```bash
curl -N http://localhost:8000/simulations/SIM_ID/stream
```

Final report:

```bash
curl http://localhost:8000/simulations/SIM_ID/report
```

## Main API

| Method | Endpoint | Purpose |
| --- | --- | --- |
| `GET` | `/health` | Service status and live execution availability |
| `GET` | `/templates` | List templates |
| `POST` | `/projects` | Create a project for attachments |
| `POST` | `/projects/{project_id}/documents` | Upload `.txt`, `.md`, or `.pdf` documents |
| `GET` | `/projects/{project_id}/documents` | List attached documents |
| `POST` | `/simulations` | Create a simulation |
| `GET` | `/simulations` | List simulations |
| `GET` | `/simulations/{sim_id}` | Get status and metadata |
| `GET` | `/simulations/{sim_id}/stream` | SSE progress stream |
| `GET` | `/simulations/{sim_id}/timeline` | Timeline data |
| `GET` | `/simulations/{sim_id}/graph` | Latest graph |
| `GET` | `/simulations/{sim_id}/graph/history` | Graph history by round |
| `GET` | `/simulations/{sim_id}/report` | Final report |
| `GET` | `/simulations/{sim_id}/colonies` | Colony-level execution state |
| `GET/POST` | `/simulations/{sim_id}/backtest` | Read or run backtests |
| `GET` | `/simulations/{sim_id}/audit-trail` | Audit trail for scenario comparison |
| `POST` | `/simulations/{sim_id}/rerun` | Rerun with the same conditions |
| `GET` | `/codex/health` | Codex App Server connection status |
| `POST` | `/simulations/{sim_id}/codex-review` | Ask Codex review questions against a completed report |
| `POST` | `/scenario-pairs` | Start scenario comparison |
| `GET` | `/scenario-pairs/{scenario_pair_id}` | Get scenario comparison status |
| `GET` | `/scenario-pairs/{scenario_pair_id}/comparison` | Get comparison output |
| `POST` | `/populations/{population_id}/snapshot` | Create a population snapshot for scenario comparison |

The `/runs` API is still available for legacy compatibility.

## Repository Layout

```text
.
├── backend/        # FastAPI API, SSE, DB, simulation runtime, tests
├── frontend/       # Vue 3 + Vite UI, Pinia stores, visualization, E2E tests
├── config/         # LLM, cognitive, population, GraphRAG, grounding config
├── templates/      # LaunchPad templates, experts, PM personas
├── scripts/        # Local development helpers, mainly scripts/dev.sh
├── data/           # Local runtime data such as SQLite DBs
├── docs/           # Implementation notes and generated schema
├── experiments/    # Validation experiments such as single vs swarm
├── evaluation/     # Evaluation baselines
├── plans/          # Development plans and work logs
├── amplifier/      # Separate Amplifier checkout, not required by Agent AI runtime
└── docker-compose.yml
```

### Folder Notes

| Folder | Contents | Beginner note |
| --- | --- | --- |
| `backend/` | Python/FastAPI API, SSE, DB, simulation, evaluation, Codex Review | Start with `uv sync --extra dev` and `uv run uvicorn ...`. |
| `frontend/` | Vue 3 + Vite LaunchPad, Live Simulation, Results, Populations, Decision Lab | Local dev uses `pnpm dev`. When `VITE_API_BASE_URL` is unset, it uses `/api`. |
| `config/` | Provider, model, cognitive, population, GraphRAG, grounding data | You usually do not need to touch it unless changing model or population behavior. |
| `templates/` | Templates such as `business_analysis`, experts, PM personas | Template edits affect UI choices and backend seed data. |
| `scripts/` | Development scripts | `./scripts/dev.sh` starts backend and frontend together. |
| `data/` | SQLite DB and local runtime data | Deleting files here can remove local history and DB data. |
| `docs/` | Implementation notes and Codex app-server schema | `docs/codex-app-server-schema/` is generated and should not be edited by hand. |
| `experiments/` | Swarm validation experiments and aggregation scripts | Run the experiment runner after the backend is running. |
| `evaluation/` | Evaluation baselines | Used for release and quality checks. |
| `plans/` | Past and active implementation plans | Prefer code and tests as the final source of truth. |
| `amplifier/` | Separate Amplifier package | Not required to start Agent AI. It has its own license. |

## Experiments

Start the backend first.

```bash
cd backend
uv run python ../experiments/swarm_validation/run_experiment.py
```

Run one test case:

```bash
cd backend
uv run python ../experiments/swarm_validation/run_experiment.py --test-case tc01
```

Change backend URL:

```bash
cd backend
uv run python ../experiments/swarm_validation/run_experiment.py --base-url http://localhost:8000
```

Aggregate results:

```bash
cd backend
uv run python ../experiments/swarm_validation/aggregate_results.py
```

## CI

GitHub Actions runs these checks on push and pull request.

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

The nightly benchmark runs around 03:00 JST and creates a backend retrodiction baseline.

## Troubleshooting

| Symptom | Check |
| --- | --- |
| UI opens but simulations cannot start | `.env` `OPENAI_API_KEY` and `http://localhost:8000/health` |
| `http://localhost:5173` does not open | `./scripts/dev.sh` frontend logs, or `cd frontend && pnpm dev` |
| `http://localhost:8000/docs` does not open | backend logs, or `cd backend && uv run uvicorn ...` |
| DB error | `.env` `DATABASE_URL`. SQLite is easiest for first local use. |
| Docker UI opens but API fails | `docker compose ps` and backend healthcheck |
| SSE stream stops | nginx `/api/simulations/:id/stream` config, or Vite proxy |
| E2E fails | Check whether `pnpm exec playwright install --with-deps chromium` has been run |

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
| Frontend routes | `frontend/src/router.ts` |
| REST API client and TypeScript types | `frontend/src/api/client.ts` |
| SSE subscription and live state updates | `frontend/src/composables/useSimulationSSE.ts` |
| Stores for execution state, graphs, society data, and Decision Lab | `frontend/src/stores/` |
| Main pages | `frontend/src/pages/` |
| Visualization and result components | `frontend/src/components/` |

## More Docs

- Design notes: [DESIGN.md](DESIGN.md)
- Contributing: [CONTRIBUTING.md](CONTRIBUTING.md)
- Code of conduct: [CODE_OF_CONDUCT.md](CODE_OF_CONDUCT.md)
- Frontend README: [frontend/README.md](frontend/README.md)
- Amplifier README: [amplifier/README.md](amplifier/README.md)

## License

Agent AI is AGPL-3.0. See [LICENSE](LICENSE) for details.

`amplifier/` is a bundled separate project and follows its own [amplifier/LICENSE](amplifier/LICENSE).
