# Agent AI

[![English](https://img.shields.io/badge/lang-English-blue.svg)](README.en.md)
[![CI](https://github.com/usagi917/agoraAI/actions/workflows/ci.yml/badge.svg)](https://github.com/usagi917/agoraAI/actions/workflows/ci.yml)
[![License: AGPL-3.0](https://img.shields.io/badge/License-AGPL--3.0-blue.svg)](LICENSE)
[![Python 3.11+](https://img.shields.io/badge/python-3.11%2B-blue.svg)](backend/pyproject.toml)
[![Node.js 20+](https://img.shields.io/badge/node-20%2B-339933.svg)](frontend/package.json)

> ひとつの問いを入力すると、合成人口の反応、評議会ディベート、Decision Brief までを一気通貫で生成するマルチエージェント分析アプリです。

## これは何か

- `frontend`: Vue 3 + Vite の SPA
- `backend`: FastAPI + async SQLAlchemy + LiteLLM
- 主な用途: 市場参入、政策影響、シナリオ比較、論点探索
- 実行モード: `quick` / `standard` / `deep` / `research` / `baseline`

## アーキテクチャ

### システム全体

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

### 分析パイプライン

```mermaid
flowchart TB
    Input["1. 質問入力 + ファイル添付"] --> Create["2. POST /simulations"]
    Create --> Dispatch["3. Dispatcher が mode を選択"]

    Dispatch -->|quick / standard / deep / research| Pulse["4. Society Pulse<br/>人口生成 → 選抜 → 活性化 → 評価"]
    Pulse --> Council["5. Council<br/>代表者選出 → 反証役設定 → 3 ラウンド議論"]
    Council --> Synthesis["6. Synthesis<br/>Decision Brief / report 生成"]

    Dispatch -->|baseline| BaselinePath["4b. 単一 LLM ベースライン分析"]

    Pulse --> Stream["SSE / graph / timeline 更新"]
    Council --> Stream
    Synthesis --> Stream
    BaselinePath --> Stream

    Synthesis --> Results["7. Results / follow-up / rerun"]
    BaselinePath --> Results
```

- `baseline` はマルチエージェント討議を通さず、単一 LLM で比較用の Decision Brief を生成します。
- `scenario-pairs` は同じ母集団スナップショットから 2 本の simulation を並列実行し、比較結果をまとめます。

## 使い方

1. LaunchPad で質問を入力します。
2. 必要ならファイルを添付します。
3. シミュレーションを開始すると、ライブ画面で SSE ベースの進捗を確認できます。
4. 完了後はレポートを確認し、follow-up や rerun を実行できます。
5. 比較が必要な場合は `scenario-pairs` でシナリオ比較を実行できます。

## Quick Start

### Docker Compose

```bash
cp .env.example .env
docker compose up --build
```

- App: `http://localhost:3000`
- API docs: `http://localhost:8000/docs`
- Health check: `http://localhost:8000/health`

注意:

- 既定 provider は `openai` です。
- 新規シミュレーションを動かすには通常 `OPENAI_API_KEY` が必要です。
- API キーがなくてもアプリは起動しますが、ライブ実行は無効になります。

### 最小 API 例

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

```bash
curl -N http://localhost:8000/simulations/SIM_ID/stream
```

```bash
curl http://localhost:8000/simulations/SIM_ID/report
```

## ローカル開発

### Backend

```bash
cp .env.example .env

cd backend
uv sync --extra dev
uv run uvicorn src.app.main:app --reload --host 0.0.0.0 --port 8000
```

ローカル既定の `DATABASE_URL` は SQLite なので、追加インフラなしでも起動できます。

### Frontend

```bash
cd frontend
pnpm install
pnpm dev
```

- Frontend dev server: `http://localhost:5173`
- `VITE_API_BASE_URL` 未指定時は `/api` を使います
- Vite が `/api` を `http://localhost:8000` にプロキシします

### PostgreSQL / Redis を使う場合

```bash
docker compose up -d postgres redis
```

必要なら `.env` を次の値に切り替えます。

```bash
DATABASE_URL=postgresql+asyncpg://agentai:agentai@localhost:5432/agentai
REDIS_URL=redis://localhost:6379/0
```

## よく触る設定

| 項目 | 場所 |
| --- | --- |
| API キーや DB 接続先 | `.env` |
| 既定 provider とモデル | `config/models.yaml` |
| provider 定義と fallback | `config/llm_providers.yaml` |
| 認知・スケジューリング設定 | `config/cognitive.yaml` |
| 実行プロファイル | `config/swarm_profiles.yaml` |
| LaunchPad テンプレート | `templates/ja/*.yaml` |

## 主要 API

| Method | Endpoint | 役割 |
| --- | --- | --- |
| `GET` | `/health` | 稼働状態の確認 |
| `GET` | `/templates` | テンプレート一覧 |
| `POST` | `/projects` | 添付用プロジェクト作成 |
| `POST` | `/projects/{project_id}/documents` | ドキュメント追加 |
| `POST` | `/simulations` | シミュレーション作成 |
| `GET` | `/simulations/{sim_id}` | 状態取得 |
| `GET` | `/simulations/{sim_id}/stream` | SSE 進捗 |
| `GET` | `/simulations/{sim_id}/report` | 最終レポート |
| `POST` | `/simulations/{sim_id}/followups` | follow-up 質問 |
| `POST` | `/simulations/{sim_id}/rerun` | 再実行 |
| `POST` | `/scenario-pairs` | シナリオ比較開始 |

## リポジトリ構成

```text
.
├── backend/       # FastAPI app, services, tests
├── frontend/      # Vue app
├── config/        # provider / cognitive / profile settings
├── templates/     # seeded prompt templates
├── data/          # local runtime data
├── DESIGN.md      # 補足設計メモ
└── CONTRIBUTING.md
```

## 詳細ドキュメント

- 設計メモ: [DESIGN.md](DESIGN.md)
- コントリビュート: [CONTRIBUTING.md](CONTRIBUTING.md)
- 行動規範: [CODE_OF_CONDUCT.md](CODE_OF_CONDUCT.md)

## License

AGPL-3.0. 詳細は [LICENSE](LICENSE) を参照してください。
