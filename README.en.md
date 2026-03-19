<div align="center">

# Agent AI

### 1,000 Cognitive Agents Debate to Deliver Collective Intelligence for Decision-Making

[![License: AGPL-3.0](https://img.shields.io/badge/License-AGPL%20v3-blue.svg)](LICENSE)
[![Python 3.11+](https://img.shields.io/badge/python-3.11%2B-blue.svg)](backend/pyproject.toml)
[![Node 20](https://img.shields.io/badge/node-20-339933.svg)](frontend/package.json)
[![Docker Compose](https://img.shields.io/badge/docker-compose-2496ED.svg)](docker-compose.yml)
[![日本語](https://img.shields.io/badge/lang-日本語-green.svg)](README.md)

**BDI Cognitive Architecture × GraphRAG × SwarmMind**
— ChatGPT gives you one perspective. Agent AI runs 20+ AI agents, each with their own beliefs, desires, and intentions, debating to support multi-faceted decision-making.

[Quick Start](#quick-start) · [Architecture](#architecture) · [Features](#features) · [Demo](#demo) · [Documentation](#documentation)

</div>

---

## Why Agent AI?

| Traditional LLMs | Agent AI |
|-------------------|----------|
| One model, one perspective | **Multiple agents with independent cognitive models debate** |
| Same thinking patterns every time | **BDI (Beliefs-Desires-Intentions) generates diverse thinking** |
| Forgets context | **3-layer memory (episodic, semantic, procedural) retains context** |
| No consideration of others' viewpoints | **Theory of Mind infers each other's thinking** |
| Flat output | **Structured debate + GraphRAG for evidence-based analysis** |

## Quick Start

```bash
git clone https://github.com/yourname/agent-ai
cd agent-ai
cp .env.example .env   # Set your OPENAI_API_KEY
docker compose up
```

Open `http://localhost:5173` → Upload a document → Start analysis.

> You can try the demo with bundled sample results even without an API key.

## Architecture

```
┌─────────────────────────────────────────────────────────────────┐
│                        Agent AI Platform                         │
├─────────────────────────────────────────────────────────────────┤
│                                                                  │
│  ┌──────────────┐   ┌──────────────┐   ┌──────────────────────┐ │
│  │  Input Layer  │   │   GraphRAG   │   │     SwarmMind        │ │
│  │              │   │              │   │                      │ │
│  │ .txt .md .pdf│──▶│ Entity &     │──▶│ N colonies parallel  │ │
│  │ Prompts      │   │ Relation     │   │ Perspective diversity │ │
│  │              │   │ Extraction   │   │ Claim clustering     │ │
│  └──────────────┘   └──────────────┘   └──────────────────────┘ │
│                                                                  │
│  ┌───────────────────────────────────────────────────────────┐   │
│  │              BDI Cognitive Architecture                     │   │
│  │                                                           │   │
│  │  ┌─────────┐  ┌─────────┐  ┌──────────┐  ┌────────────┐  │   │
│  │  │ Beliefs │  │ Desires │  │Intentions│  │ Theory of  │  │   │
│  │  │         │  │         │  │          │  │   Mind     │  │   │
│  │  └────┬────┘  └────┬────┘  └────┬─────┘  └─────┬──────┘  │   │
│  │       │            │            │               │         │   │
│  │  ┌────▼────────────▼────────────▼───────────────▼──────┐  │   │
│  │  │              3-Layer Memory System                    │  │   │
│  │  │  Episodic │ Semantic │ Procedural │ Reflection       │  │   │
│  │  └────────────────────────────────────────────────────┘  │   │
│  │                                                           │   │
│  │  ┌──────────────────────────────────────────────────────┐ │   │
│  │  │          Structured Debate Protocol                   │ │   │
│  │  │  Game Master │ Causal Reasoning │ Social Influence   │ │   │
│  │  └──────────────────────────────────────────────────────┘ │   │
│  └───────────────────────────────────────────────────────────┘   │
│                                                                  │
│  ┌───────────────────────────────────────────────────────────┐   │
│  │                    Visualization & Output                  │   │
│  │  3D Graph │ Timeline │ Scenario Compare │ Agreement Map   │   │
│  │  BDI State│ Memory Stream │ ToM Map │ KG Explorer         │   │
│  └───────────────────────────────────────────────────────────┘   │
└─────────────────────────────────────────────────────────────────┘
```

## Features

### Three Execution Modes

| Mode | Description |
|------|-------------|
| **Single** | Deep analysis with a single simulation run |
| **Swarm** | Multiple colonies run in parallel, aggregating scenario distributions |
| **Hybrid** | Combines Swarm diversity with Single depth |

### 10 Analysis Views

| View | Content |
|------|---------|
| Report | Structured analysis report (11 sections) |
| Scenario Compare | Probability distributions across multiple scenarios |
| Agreement Heatmap | Inter-colony agreement matrix |
| 3D Graph | Time-replayable 3D force-directed graph |
| Cognition | Real-time BDI state display per agent |
| Memory | Episodic, semantic, and procedural memory streams |
| Evaluation | Simulation quality evaluation dashboard |
| ToM Map | Theory of Mind relationship network |
| Social Network | Social network dynamics visualization |
| KG Explorer | Knowledge graph explorer |

### Depth of Cognitive Architecture

- **BDI Engine**: Each agent maintains Beliefs, Desires, and Intentions, updating them as the environment changes
- **Theory of Mind**: Agents infer each other's goals and actions, behaving strategically
- **3-Layer Memory**: Episodic (experiences), Semantic (knowledge), Procedural (skills) + Reflection mechanism
- **Structured Debate**: Game Master detects contradictions, causal reasoning deepens discussions
- **GraphRAG**: Automatically builds knowledge graphs from documents with community detection

## Demo

### Minimal Experience Flow

1. Open `http://localhost:5173`
2. Select `Single` mode
3. Upload `sample_inputs/business_case/market_entry.md`
4. Select `Business Analysis` template
5. Run with `Preview` profile
6. View 3D graph, report, and cognitive states in the results

### Sample Inputs

| Sample | Content |
|--------|---------|
| [`market_entry.md`](sample_inputs/business_case/market_entry.md) | EV battery market entry analysis |
| [`carbon_tax.md`](sample_inputs/policy_case/carbon_tax.md) | Carbon tax impact analysis |
| [`ai_regulation.md`](sample_inputs/scenario_case/ai_regulation.md) | Future AI regulation scenario analysis |

## Local Development

### Backend

```bash
docker compose up postgres redis   # Start dependencies
cd backend
uv sync
uv run uvicorn src.app.main:app --reload --host 0.0.0.0 --port 8000
```

### Frontend

```bash
cd frontend
pnpm install
pnpm dev
```

### Tests

```bash
cd backend && uv run pytest
cd frontend && pnpm build
```

## Templates

| Template | Purpose |
|----------|---------|
| [`business_analysis`](templates/ja/business_analysis.yaml) | Company, market, competitor, and regulatory interaction analysis |
| [`policy_simulation`](templates/ja/policy_simulation.yaml) | Stakeholder reaction analysis to policy changes |
| [`scenario_exploration`](templates/ja/scenario_exploration.yaml) | Exploration of uncertain future scenarios |

## Configuration

| File | Content |
|------|---------|
| [`.env.example`](.env.example) | API keys, DB, Redis settings |
| [`config/models.yaml`](config/models.yaml) | LLM provider and task-specific model config |
| [`config/cognitive.yaml`](config/cognitive.yaml) | BDI cognitive mode, Game Master, ToM settings |
| [`config/graphrag.yaml`](config/graphrag.yaml) | GraphRAG pipeline settings |
| [`config/swarm_profiles.yaml`](config/swarm_profiles.yaml) | Colony counts, rounds, temperature distribution |
| [`config/perspectives.yaml`](config/perspectives.yaml) | Colony perspective frame definitions |

## API

Use the unified `simulations` API:

```
POST /simulations              # Create and run simulation
GET  /simulations              # List all
GET  /simulations/{id}         # Get details
GET  /simulations/{id}/stream  # SSE streaming
GET  /simulations/{id}/graph   # Graph data
GET  /simulations/{id}/report  # Get report
POST /simulations/{id}/followups  # Follow-up questions
```

Full documentation at `http://localhost:8000/docs` (OpenAPI).

## Project Structure

```
.
├── backend/           # FastAPI + SQLAlchemy + BDI Cognitive Engine + GraphRAG
├── frontend/          # Vue 3 + Vite + 3D Force Graph + 10-view Dashboard
├── config/            # Model, cognitive, GraphRAG, Swarm settings
├── templates/ja/      # Analysis templates (YAML)
├── sample_inputs/     # Sample input documents
├── docker-compose.yml # PostgreSQL / Redis / Backend / Frontend
└── .env.example       # Environment variable template
```

## Contributing

See [CONTRIBUTING.md](CONTRIBUTING.md).

## License

[AGPL-3.0](LICENSE) — Free to use as open source. Contact us for commercial licensing.
