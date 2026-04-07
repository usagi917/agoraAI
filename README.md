# Agent AI

[![English](https://img.shields.io/badge/lang-English-blue.svg)](README.en.md)
[![CI](https://github.com/usagi917/agoraAI/actions/workflows/ci.yml/badge.svg)](https://github.com/usagi917/agoraAI/actions/workflows/ci.yml)
[![License: AGPL-3.0](https://img.shields.io/badge/License-AGPL--3.0-blue.svg)](LICENSE)
[![Python 3.11+](https://img.shields.io/badge/python-3.11%2B-blue.svg)](backend/pyproject.toml)
[![Node.js 20+](https://img.shields.io/badge/node-20%2B-339933.svg)](frontend/package.json)

> 1つの問いから、社会反応シミュレーション、代表評議会ディベート、Decision Brief 生成までを一気通貫で回せるマルチエージェント分析アプリです。`frontend` は Vue 3 + Vite、`backend` は FastAPI + async SQLAlchemy を中心に構成されています。

## 概要

- LaunchPad から4種類の質問テンプレート、または自由入力のプロンプトで分析を開始できます。
- `quick` / `standard` / `deep` / `research` / `baseline` の5つのプリセットで、速度と深さを切り替えられます。
- `.txt` / `.md` / `.pdf` をプロジェクトに添付し、エビデンス付きの分析フローに載せられます。
- ライブ画面では SSE で進捗を配信し、Activity Feed、社会反応、会話、グラフの変化を追跡できます。
- 結果画面では Decision Brief、シナリオ比較、伝播分析、Transcript、再実行、フォローアップ質問を扱えます。
- `/populations` では人口生成、一覧確認、世代 fork ができます。
- Decision Lab では2つのシナリオを同一人口で並行実行し、意見シフト・連合変動・監査証跡を比較できます。
- Theater UI ではディベートカード、ライブ対話ストリーム、スタンス変化をリアルタイムに可視化します。

## Frontend / Backend の実装要点

| 領域 | 実装 | README に反映しておくポイント |
| --- | --- | --- |
| `frontend/` | Vue 3 + TypeScript + Vite + Pinia + Axios | API の基準パスは `VITE_API_BASE_URL` 未指定時 `/api`。ローカル開発では Vite proxy、Docker では Nginx proxy を使います。 |
| `frontend/` | `3d-force-graph` / `three` / `html2canvas` / `jspdf` | ライブグラフ表示とレポート系 UI を同じ SPA で扱います。 |
| `backend/` | FastAPI + async SQLAlchemy + LiteLLM | REST API と SSE を同じアプリから配信します。 |
| `backend/` | SQLite（ローカル既定）/ PostgreSQL（Compose）/ Redis（任意） | ローカル最小構成は SQLite のみで動作し、Compose は PostgreSQL + Redis を使います。 |
| `backend/` | `templates/ja/*.yaml` を起動時 seed | LaunchPad のテンプレート一覧は DB ではなく YAML 定義から供給されます。 |

## 画面と実行フロー

| Route | 役割 | 主な内容 |
| --- | --- | --- |
| `/` | LaunchPad | 質問テンプレート、自由入力、ファイル添付、プリセット選択、実行履歴 |
| `/sim/:id` | Live Simulation | SSE 進捗、Activity Feed、社会反応、会話、ライブグラフ、Theater UI（ディベートカード・対話ストリーム） |
| `/sim/:id/results` | Results | Decision Brief、シナリオ比較、Propagation、Transcript、Follow-up |
| `/populations` | Populations | 人口生成、人口一覧、詳細表示、fork |
| `/compare` | Compare Setup | 比較用の政策介入条件、母集団、プリセットの入力 |
| `/scenario/:id` | Decision Lab | シナリオペア比較、意見シフト表、連合マップ、監査タイムライン |

実行時の大まかな流れは次の3段です。

1. `Society Pulse`
人口設定に基づいて大規模な合成人口を生成し、選抜されたエージェント群の反応を集約します。
2. `Council`
市民代表と専門家を選び、複数ラウンドの構造化議論を行います。
3. `Synthesis`
社会反応、議論、品質情報をまとめて Decision Brief と比較可能なシナリオを生成します。

補足:

- 旧ルート `/run/:id`、`/report/:id`、`/swarm*` は新しい `/sim/*` 系にリダイレクトされます。
- 開発時のみ `/__e2e__/sse` が有効になり、Playwright から SSE 動作確認に使われます。

### プリセット

| Preset | 主なフェーズ | 用途 |
| --- | --- | --- |
| `quick` | `society_pulse -> synthesis` | 一次判断を高速に得たいとき |
| `standard` | `society_pulse -> council -> synthesis` | 既定の分析フロー |
| `deep` | `society_pulse -> multi_perspective -> council -> pm_analysis -> synthesis` | 多視点と PM 分析まで含めて深掘りしたいとき |
| `research` | `society_pulse -> issue_mining -> multi_perspective -> intervention -> synthesis` | 論点抽出と介入比較を重視したいとき |
| `baseline` | 単一 LLM のベースライン実行 | 比較・検証用 |

旧モード名は内部で正規化されます。たとえば `unified -> standard`、`society_first -> research`、`single -> quick` です。

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
        ORCH["Simulation dispatcher / orchestrators"]
        SOC["Society services"]
        LLM["Task router + multi-provider adapters"]
        DB["Async SQLAlchemy"]
    end

    subgraph Data["Data / Infra"]
        SQLITE["SQLite (local default)"]
        POSTGRES["PostgreSQL (Compose)"]
        REDIS["Redis (optional / Compose)"]
        CFG["config/*.yaml"]
        TMPL["templates/ja/*.yaml"]
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
    API --> TMPL
```

補足:

- Docker の `frontend` は Nginx で配信され、`/api` を `backend:8000` にプロキシします。
- `backend` 起動時に `templates/ja/*.yaml` を読み込み、テンプレートを DB に seed します。
- ローカル最小構成は SQLite 前提、Docker Compose は PostgreSQL + Redis 前提です。

## Prerequisites

- Node.js 20+
- `pnpm` 10 系
- Python 3.11+
- `uv`
- Docker / Docker Compose（Compose 起動を使う場合）

## Quick Start

### Docker Compose で起動

```bash
cp .env.example .env
# provider が openai のままなら OPENAI_API_KEY を設定
docker compose up --build
```

- App: `http://localhost:3000`
- API docs: `http://localhost:8000/docs`
- Health check: `http://localhost:8000/health`

注意:

- `config/models.yaml` の既定 provider は `openai` です。この状態で新規シミュレーションを実行するには `OPENAI_API_KEY` が必要です。
- `GOOGLE_API_KEY` と `ANTHROPIC_API_KEY` は、`config/llm_providers.yaml` 側で対象 provider を使うときに必要です。
- API キー未設定でもアプリ自体は起動しますが、新規ライブ実行は無効になります。

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

### 1. バックエンド

`.env.example` は SQLite を指しているので、追加インフラなしでバックエンドだけ起動できます。

```bash
cp .env.example .env

cd backend
uv sync --extra dev
uv run uvicorn src.app.main:app --reload --host 0.0.0.0 --port 8000
```

### 2. フロントエンド

別ターミナルで起動します。

```bash
cd frontend
pnpm install
pnpm dev
```

- Frontend dev server: `http://localhost:5173`
- Vite は `/api` を `http://localhost:8000` に proxy します。
- `VITE_API_BASE_URL` を明示したい場合だけ、`frontend/.env.local` か起動時のシェル変数で上書きしてください。

### 3. PostgreSQL / Redis を使う場合

```bash
docker compose up -d postgres redis
```

`.env` を Docker 構成に寄せるなら次の値を使います。

```bash
DATABASE_URL=postgresql+asyncpg://agentai:agentai@localhost:5432/agentai
REDIS_URL=redis://localhost:6379/0
```

## 設定ポイント

### 主要な環境変数

| 変数 | 役割 |
| --- | --- |
| `OPENAI_API_KEY` | 既定 provider (`openai`) の実行キー |
| `GOOGLE_API_KEY` | Gemini の OpenAI 互換 endpoint を使う場合のキー |
| `ANTHROPIC_API_KEY` | Anthropic provider 用キー |
| `LLM_MODEL` | デフォルトモデル。`config/models.yaml` でタスク別上書き可能 |
| `DATABASE_URL` | ローカルは SQLite、Compose は PostgreSQL を想定 |
| `REDIS_URL` | Redis 利用時のみ必要 |
| `COGNITIVE_MODE` | `legacy` / `advanced` の認知モード切り替え |
| `MAX_ACTIVE_AGENTS` | 同時に管理する認知エージェント上限 |
| `MAX_CONCURRENT_AGENTS` | 認知サイクルの同時実行上限 |
| `MAX_CONCURRENT_COLONIES` | Colony の同時実行上限 |

### 実装上よく触る設定ファイル

| ファイル | 内容 |
| --- | --- |
| `config/models.yaml` | 既定 provider、既定モデル、タスク別モデル割り当て |
| `config/llm_providers.yaml` | Society 側の provider 定義、API キー参照名、fallback 順 |
| `config/cognitive.yaml` | BDI / ToM / scheduling / rate limiting の詳細 |
| `config/swarm_profiles.yaml` | Colony 数や round 数などの profile 設定 |
| `templates/ja/*.yaml` | LaunchPad のテンプレート定義。起動時に DB へ seed |

## API 概要

### 基本フロー

| Method | Endpoint | 役割 |
| --- | --- | --- |
| `GET` | `/health` | 稼働状態と live execution 可否の確認 |
| `GET` | `/templates` | 利用可能なテンプレート一覧 |
| `POST` | `/projects` | ドキュメント添付用のプロジェクト作成 |
| `POST` | `/projects/{project_id}/documents` | `.txt` / `.md` / `.pdf` のアップロード |
| `POST` | `/simulations` | 新規シミュレーション作成 |
| `GET` | `/simulations/{sim_id}` | 状態・メタデータ取得 |
| `GET` | `/simulations/{sim_id}/stream` | SSE 進捗ストリーム |
| `GET` | `/simulations/{sim_id}/timeline` | タイムライン取得 |
| `GET` | `/simulations/{sim_id}/graph` | 最新グラフ取得 |
| `GET` | `/simulations/{sim_id}/graph/history` | ラウンドごとのグラフ履歴 |
| `GET` | `/simulations/{sim_id}/report` | 最終レポート取得 |
| `POST` | `/simulations/{sim_id}/followups` | 結果に対する follow-up 質問 |
| `POST` | `/simulations/{sim_id}/rerun` | 同条件で再実行 |
| `GET` | `/simulations/{sim_id}/audit-trail` | エージェントごとの監査イベント取得 |

### Society / 運用系

| Method | Endpoint | 役割 |
| --- | --- | --- |
| `GET` | `/society/populations` | 人口一覧 |
| `POST` | `/society/populations/generate` | 人口生成 |
| `GET` | `/society/populations/{pop_id}` | 人口詳細 |
| `POST` | `/society/populations/{pop_id}/fork` | 人口 fork |
| `GET` | `/society/simulations/{sim_id}/activation` | activation 結果 |
| `GET` | `/society/simulations/{sim_id}/meeting` | meeting 結果 |
| `GET` | `/society/simulations/{sim_id}/evaluation` | 評価メトリクス |
| `GET` | `/society/simulations/{sim_id}/propagation` | 伝播データ |
| `GET` | `/society/simulations/{sim_id}/transcript` | 発話 Transcript |
| `GET` | `/admin/costs` | トークン・コスト集計 |
| `GET` | `/admin/quality-metrics` | 品質・fallback 集計 |

### Scenario comparison

| Method | Endpoint | 役割 |
| --- | --- | --- |
| `POST` | `/scenario-pairs` | ベースラインと介入シナリオを同時作成 |
| `GET` | `/scenario-pairs/{scenario_pair_id}` | シナリオ比較ジョブの状態確認 |
| `GET` | `/scenario-pairs/{scenario_pair_id}/comparison` | 比較 Decision Brief と差分取得 |
| `POST` | `/populations/{population_id}/snapshot` | 比較用の母集団スナップショット作成 |

補足:

- `/runs/*` は旧来の single-run API で、後方互換のため残っています。
- `/simulations/{sim_id}/backtest` は `society_first` 系の互換 API です。

## テスト

CI では以下を実行しています。

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

## リポジトリ構成

```text
.
├── backend/            # FastAPI app, async SQLAlchemy, tests, Dockerfile
├── frontend/           # Vue 3 + Vite app, Playwright/Vitest, Dockerfile
├── config/             # LLM / cognitive / grounding / swarm profiles
├── templates/          # 起動時に seed されるテンプレート
├── data/               # ローカル DB や実行データ
├── docker-compose.yml  # frontend + backend + postgres + redis
├── README.md           # 日本語 README
└── README.en.md        # English README
```

## Contributing

- 開発フローや参加ルールは [CONTRIBUTING.md](CONTRIBUTING.md) を参照してください。
- 行動規範は [CODE_OF_CONDUCT.md](CODE_OF_CONDUCT.md) にあります。

## License

AGPL-3.0. 詳細は [LICENSE](LICENSE) を参照してください。
