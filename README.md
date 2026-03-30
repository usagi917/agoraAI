# Agent AI

[![English](https://img.shields.io/badge/lang-English-blue.svg)](README.en.md)
[![CI](https://github.com/usagi917/agoraAI/actions/workflows/ci.yml/badge.svg)](https://github.com/usagi917/agoraAI/actions/workflows/ci.yml)
[![License: AGPL-3.0](https://img.shields.io/badge/License-AGPL--3.0-blue.svg)](LICENSE)
[![Python 3.11+](https://img.shields.io/badge/python-3.11%2B-blue.svg)](backend/pyproject.toml)
[![Node.js 20+](https://img.shields.io/badge/node-20%2B-339933.svg)](frontend/package.json)

> 社会反応シミュレーション、評議会ディベート、Decision Brief 生成を 1 つの UI で回せるマルチエージェント分析アプリです。`frontend` は Vue 3 + Vite、`backend` は FastAPI + async SQLAlchemy で構成されています。

## Quick Start

```bash
cp .env.example .env
# 必要なら OPENAI_API_KEY を設定
docker compose up --build
```

- App: http://localhost:3000
- API docs: http://localhost:8000/docs
- Health check: http://localhost:8000/health

`OPENAI_API_KEY` が未設定でもアプリは起動します。ライブ実行は無効になりますが、サンプル結果の閲覧や画面確認は可能です。

## できること

- 4 種類の質問ウィザードから分析を開始できます。
  - 市場参入
  - 製品受容性
  - 政策影響
  - 選択肢比較
- フリーテキストに加えて `.txt` / `.md` / `.pdf` をアップロードし、プロジェクト単位で分析できます。
- 5 つのプリセットを実行できます。
  - `quick`
  - `standard`
  - `deep`
  - `research`
  - `baseline`
- ライブ画面で SSE 進捗、Activity Feed、社会反応の分布、3D グラフを追跡できます。
- 結果画面で Decision Brief、シナリオ比較、Agreement Heatmap、Propagation Dashboard、Transcript、再実行、Follow-up 質問を扱えます。
- 人口データを生成・閲覧・fork できます。
- サンプル結果を API キーなしで閲覧できます。

## 実行パイプライン

| Preset | Backend phases | 用途 |
| --- | --- | --- |
| `quick` | `society_pulse -> synthesis` | 高速な一次判断 |
| `standard` | `society_pulse -> council -> synthesis` | 既定の分析フロー |
| `deep` | `society_pulse -> multi_perspective -> council -> pm_analysis -> synthesis` | 多視点と PM 分析を含む深掘り |
| `research` | `society_pulse -> issue_mining -> multi_perspective -> intervention -> synthesis` | 論点抽出と介入比較 |
| `baseline` | 専用ベースライン実行 | 単一 LLM 比較 |

旧モード名は内部でプリセットへ正規化されます。たとえば `unified -> standard`、`society_first -> research`、`single -> quick` です。

実装上の主な流れは次のとおりです。

- Society Pulse は設定ファイルに基づく大規模人口を生成し、100 人を選抜して活性化・評価します。
- Council は最大 6 人の市民代表と 4 人の専門家を選び、3 ラウンドの議論を行います。
- Synthesis は社会反応と評議会結果を統合して Decision Brief を生成します。

## 画面構成

| Route | 画面 | 主な内容 |
| --- | --- | --- |
| `/` | LaunchPad | テンプレート選択、質問ウィザード、プロンプト入力、ファイルアップロード、最近の実行 |
| `/sim/:id` | Live Simulation | SSE 進捗、Simulation Progress、Colony / Society 状態、3D グラフ |
| `/sim/:id/results` | Results | Decision Brief、シナリオ比較、伝播分析、Transcript、Follow-up |
| `/sample/:id` | Sample Result | サンプル結果の閲覧 |
| `/populations` | Populations | 人口生成、一覧、fork |

## アーキテクチャ

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

補足:

- `frontend` の本番コンテナは Nginx で配信され、`/api` と SSE を `backend:8000` へプロキシします。
- `backend` 起動時に `templates/ja/*.yaml` を読み込み、テンプレートを DB に seed します。
- ローカル既定 DB は SQLite です。Docker Compose では PostgreSQL を使います。

## API Quick Start

### 1. プロンプトだけでシミュレーションを作成

```bash
curl -X POST http://localhost:8000/simulations \
  -H "Content-Type: application/json" \
  -d '{
    "mode": "standard",
    "execution_profile": "standard",
    "template_name": "market_entry",
    "prompt_text": "EVバッテリー市場に参入すべきか",
    "evidence_mode": "strict"
  }'
```

### 2. SSE で進捗を見る

```bash
curl -N http://localhost:8000/simulations/SIM_ID/stream
```

### 3. 結果レポートを取得

```bash
curl http://localhost:8000/simulations/SIM_ID/report
```

### 主要エンドポイント

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

## ローカル開発

### 最小構成で起動する

`.env.example` は SQLite を向くので、そのままでもバックエンドを起動できます。

```bash
cp .env.example .env

cd backend
uv sync --extra dev
uv run uvicorn src.app.main:app --reload --host 0.0.0.0 --port 8000
```

別ターミナルで:

```bash
cd frontend
pnpm install
pnpm dev
```

- Frontend dev server: http://localhost:5173
- Vite は `/api` を `http://localhost:8000` へプロキシします。

### PostgreSQL / Redis ありで合わせる

```bash
docker compose up -d postgres redis
```

`.env` を次のようにすると Docker 構成に近い形でローカルバックエンドを動かせます。

```bash
DATABASE_URL=postgresql+asyncpg://agentai:agentai@localhost:5432/agentai
REDIS_URL=redis://localhost:6379/0
```

## テスト

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

CI では backend tests、frontend build、frontend unit tests、Playwright E2E を実行します。

## 設定

### 主な環境変数

| Variable | 用途 |
| --- | --- |
| `OPENAI_API_KEY` | OpenAI provider を使うライブ実行用 |
| `GOOGLE_API_KEY` | Gemini provider 用 |
| `ANTHROPIC_API_KEY` | Anthropic provider 用 |
| `LLM_MODEL` | ベースモデル指定。タスク別設定は `config/models.yaml` が優先 |
| `DATABASE_URL` | DB 接続先。`.env.example` は SQLite、Compose は PostgreSQL |
| `REDIS_URL` | Redis 接続先。Compose では有効 |
| `BACKEND_HOST` / `BACKEND_PORT` | FastAPI bind 設定 |
| `VITE_API_BASE_URL` | フロントエンドが使う API ベース URL |
| `COGNITIVE_MODE` | `legacy` または `advanced` |
| `MAX_ACTIVE_AGENTS` | 認知エージェントの最大数 |
| `MAX_CONCURRENT_AGENTS` | 同時に認知サイクルを回す数 |
| `MAX_CONCURRENT_COLONIES` | multi-perspective / colony 実行の同時数 |
| `LLM_CACHE_TTL` | キャッシュ TTL 秒 |

### 主要設定ファイル

| File | 内容 |
| --- | --- |
| `config/models.yaml` | provider とタスク別モデル選択 |
| `config/llm_providers.yaml` | OpenAI / Gemini / Anthropic の定義と fallback 順序 |
| `config/population_mix.yaml` | 人口サイズ、属性分布、レイヤー別 provider 重み |
| `config/cognitive.yaml` | 認知・通信・スケジューリング関連設定 |
| `config/graphrag.yaml` | KG 抽出設定 |
| `templates/ja/*.yaml` | LaunchPad で使う分析テンプレート |

### テンプレート

起動時に `templates/ja` 以下の YAML がテンプレートとして読み込まれます。現行リポジトリには次が含まれます。

- `business_analysis`
- `market_entry`
- `policy_impact`
- `policy_simulation`
- `scenario_exploration`

加えて `templates/ja/pm_board` と `templates/ja/experts` に補助テンプレートがあります。

## リポジトリ構成

```text
.
├── backend/
│   ├── src/app/api/routes/      # FastAPI ルーター
│   ├── src/app/services/        # オーケストレーション、society、cognition、GraphRAG
│   ├── src/app/llm/             # LLM クライアントと adapter
│   ├── tests/                   # pytest
│   └── pyproject.toml
├── frontend/
│   ├── src/pages/               # LaunchPad / Simulation / Results / Sample / Populations
│   ├── src/components/          # UI コンポーネント
│   ├── src/stores/              # Pinia stores
│   ├── tests/e2e/               # Playwright
│   └── package.json
├── config/                      # YAML 設定
├── templates/                   # 分析テンプレート
├── sample_results/              # API キー不要のサンプル結果
├── docker-compose.yml
├── README.md
└── README.en.md
```

## Contributing

[CONTRIBUTING.md](CONTRIBUTING.md) を参照してください。

## License

[AGPL-3.0](LICENSE)
