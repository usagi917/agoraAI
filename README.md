# Agent AI

[![English](https://img.shields.io/badge/lang-English-blue.svg)](README.en.md)
[![CI](https://github.com/usagi917/agoraAI/actions/workflows/ci.yml/badge.svg)](https://github.com/usagi917/agoraAI/actions/workflows/ci.yml)
[![License: AGPL-3.0](https://img.shields.io/badge/License-AGPL--3.0-blue.svg)](LICENSE)
[![Python 3.11+](https://img.shields.io/badge/python-3.11%2B-blue.svg)](backend/pyproject.toml)
[![Node.js 20+](https://img.shields.io/badge/node-20%2B-339933.svg)](frontend/package.json)

> ひとつの問いを入力すると、合成人口の反応、評議会ディベート、Decision Brief までを一気通貫で生成するマルチエージェント分析アプリです。

## これは何か

- LaunchPad から5種類の質問テンプレート、または自由入力のプロンプトで分析を開始できます。
- `quick` / `standard` / `deep` / `research` / `baseline` の5つのプリセットで、速度と深さを切り替えられます。
- `.txt` / `.md` / `.pdf` をプロジェクトに添付し、エビデンス付きの分析フローに載せられます。
- ライブ画面では SSE で進捗を配信し、Activity Feed、社会反応、会話、グラフの変化を追跡できます。
- 結果画面では Decision Brief、シナリオ比較、伝播分析、Transcript、再実行、フォローアップ質問を扱えます。
- `/populations` では人口生成、一覧確認、世代 fork ができます。
- `/compare` から Decision Lab を開始し、2つのシナリオを同一人口で並行実行して意見シフト・連合変動・監査証跡を比較できます。
- Theater UI ではディベートカード、ライブ対話ストリーム、スタンス変化をリアルタイムに可視化します。
- `config/` と `templates/` に provider、認知設定、人口構成、LaunchPad テンプレートを集約しています。

## 30秒でわかるポンチ図

Agent AI は「問い」と「任意の根拠文書」を受け取り、合成人口の反応、代表者・専門家の議論、品質チェックを通して、意思決定に使える Decision Brief へ変換します。

```mermaid
flowchart LR
    Q["問い / テンプレート / 添付文書"] --> L["LaunchPad<br/>Vue UI"]
    L --> A["FastAPI<br/>Simulation API"]
    A --> P["Project / Document<br/>保存・GraphRAG"]
    A --> D["Dispatcher<br/>preset 正規化"]
    D --> S["Society Pulse<br/>合成人口の反応"]
    S --> C["Council<br/>代表者 + 専門家の議論"]
    C --> Y["Synthesis<br/>Decision Brief 生成"]
    Y --> R["Results<br/>判断材料・根拠・次アクション"]
    Y --> X["Decision Lab<br/>シナリオ比較"]
    S -. SSE .-> V["Live Simulation<br/>進捗・会話・社会グラフ"]
    C -. SSE .-> V
    Y -. SSE .-> V
```

読み方:

- ユーザーは LaunchPad で質問、テンプレート、ファイル、実行プリセットを選びます。
- バックエンドは `quick` / `standard` / `deep` / `research` / `baseline` に正規化し、必要なフェーズだけを実行します。
- 実行中の状態は SSE で配信され、フロントエンドの Pinia store が Activity Feed、社会グラフ、会話、Theater UI に反映します。
- 結果は Decision Brief、シナリオ比較、伝播分析、Transcript、follow-up 質問として再利用できます。

## 画面と実行フロー

| Route | 役割 | 主な内容 |
| --- | --- | --- |
| `/` | LaunchPad | 質問テンプレート、自由入力、ファイル添付、プリセット選択、実行履歴 |
| `/sim/:id` | Live Simulation | SSE 進捗、Activity Feed、社会反応、会話、ライブグラフ、Theater UI（ディベートカード・対話ストリーム） |
| `/sim/:id/results` | Results | Decision Brief、シナリオ比較、Propagation、Transcript、Follow-up |
| `/populations` | Populations | 人口生成、人口一覧、詳細表示、fork |
| `/compare` | Compare Setup | 2つのシナリオ、実行プリセット、人口設定を指定して比較実行を開始 |
| `/scenario/:id` | Decision Lab | シナリオペア比較、意見シフト表、連合マップ、監査タイムライン |

実行時の大まかな流れは次の3段です。

1. `Society Pulse`
人口設定に基づいて大規模な合成人口を生成し、選抜されたエージェント群の反応を集約します。
2. `Council`
市民代表と専門家を選び、複数ラウンドの構造化議論を行います。
3. `Synthesis`
社会反応、議論、品質情報をまとめて Decision Brief と比較可能なシナリオを生成します。

### プリセット

| Preset | 主なフェーズ | 用途 |
| --- | --- | --- |
| `quick` | `society_pulse -> synthesis` | 一次判断を高速に得たいとき |
| `standard` | `society_pulse -> council -> synthesis` | 既定の分析フロー |
| `deep` | `society_pulse -> multi_perspective -> council -> pm_analysis -> synthesis` | 多視点と PM 分析まで含めて深掘りしたいとき |
| `research` | `society_pulse -> issue_mining -> multi_perspective -> intervention -> synthesis` | 論点抽出と介入比較を重視したいとき |
| `baseline` | 単一 LLM のベースライン実行 | 比較・検証用 |

旧モード名は内部で正規化されます。たとえば `unified -> standard`、`society_first -> research`、`single -> quick` です。

## コードを読む入口

| 知りたいこと | 主なファイル |
| --- | --- |
| アプリ起動、CORS、テンプレート seed、health check | `backend/src/app/main.py` |
| 環境変数、config YAML の読み込み | `backend/src/app/config.py` |
| DB 接続、テーブル作成、SQLite/PostgreSQL 切り替え | `backend/src/app/database.py` |
| API ルート全体の登録 | `backend/src/app/api/routes/__init__.py` |
| シミュレーション作成、SSE、レポート、再実行 | `backend/src/app/api/routes/simulations.py` |
| 実行プリセットの定義と旧モード名の変換 | `backend/src/app/models/simulation.py` |
| `baseline` と unified 実行の振り分け | `backend/src/app/services/simulation_dispatcher.py` |
| `Society Pulse -> Council -> Synthesis` の本体 | `backend/src/app/services/unified_orchestrator.py` |
| 合成人口、社会ネットワーク、反応、伝播、評価 | `backend/src/app/services/society/` |
| LLM の task routing、provider adapter、fallback | `backend/src/app/llm/` |
| フロントエンドの route 定義 | `frontend/src/router.ts` |
| REST API client と型定義 | `frontend/src/api/client.ts` |
| SSE 購読とライブ状態更新 | `frontend/src/composables/useSimulationSSE.ts` |
| 実行状態、グラフ、社会、Decision Lab の状態管理 | `frontend/src/stores/` |
| 主要画面 | `frontend/src/pages/` |
| 可視化・結果表示コンポーネント | `frontend/src/components/` |

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

## 前提

- Python 3.11 以上
- uv
- Node.js 20 以上
- pnpm
- Docker / Docker Compose（PostgreSQL、Redis、またはコンテナ起動を使う場合）

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

### ローカル一括起動

依存関係を入れたあと、バックエンドとフロントエンドを1コマンドで起動できます。

```bash
cp .env.example .env

cd backend
uv sync --extra dev

cd ../frontend
pnpm install

cd ..
./scripts/dev.sh
```

- Backend: `http://localhost:8000`
- Frontend: `http://localhost:5173`
- ポートを変える場合: `./scripts/dev.sh --backend-port 8001 --frontend-port 5174`

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
- Docker 版フロントエンドは nginx で `:3000` を配信し、`/api` を backend に転送します
- SSE の `/api/simulations/:id/stream` は nginx 側で buffering を無効化しています

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
| 人口構成 | `config/population_mix.yaml` |
| GraphRAG / grounding | `config/graphrag.yaml`, `config/grounding/` |
| LaunchPad テンプレート | `templates/ja/*.yaml` |

## 主要 API

| Method | Endpoint | 役割 |
| --- | --- | --- |
| `GET` | `/health` | 稼働状態と live execution 可否の確認 |
| `GET` | `/templates` | 利用可能なテンプレート一覧 |
| `POST` | `/projects` | ドキュメント添付用のプロジェクト作成 |
| `POST` | `/projects/{project_id}/documents` | `.txt` / `.md` / `.pdf` のアップロード |
| `GET` | `/projects/{project_id}/documents` | 添付ドキュメント一覧 |
| `POST` | `/simulations` | 新規シミュレーション作成 |
| `GET` | `/simulations` | シミュレーション一覧 |
| `GET` | `/simulations/{sim_id}` | 状態・メタデータ取得 |
| `GET` | `/simulations/{sim_id}/stream` | SSE 進捗ストリーム |
| `GET` | `/simulations/{sim_id}/timeline` | タイムライン取得 |
| `GET` | `/simulations/{sim_id}/graph` | 最新グラフ取得 |
| `GET` | `/simulations/{sim_id}/graph/history` | ラウンドごとのグラフ履歴 |
| `GET` | `/simulations/{sim_id}/report` | 最終レポート取得 |
| `GET` | `/simulations/{sim_id}/colonies` | colony 単位の実行状態 |
| `GET/POST` | `/simulations/{sim_id}/backtest` | backtest 結果取得・実行 |
| `GET` | `/simulations/{sim_id}/audit-trail` | シナリオ比較用の監査証跡 |
| `POST` | `/simulations/{sim_id}/followups` | 結果に対する follow-up 質問 |
| `POST` | `/simulations/{sim_id}/rerun` | 同条件で再実行 |
| `POST` | `/scenario-pairs` | シナリオ比較開始 |
| `GET` | `/scenario-pairs/{scenario_pair_id}` | シナリオ比較の状態取得 |
| `GET` | `/scenario-pairs/{scenario_pair_id}/comparison` | 比較結果取得 |
| `POST` | `/populations/{population_id}/snapshot` | シナリオ比較用の人口 snapshot 作成 |

### Runs / レガシー互換

| Method | Endpoint | 役割 |
| --- | --- | --- |
| `GET` | `/runs` | run 一覧 |
| `POST` | `/runs` | run 作成 |
| `GET` | `/runs/{run_id}` | run 状態取得 |
| `GET` | `/runs/{run_id}/report` | run レポート取得 |
| `GET` | `/runs/{run_id}/timeline` | run タイムライン取得 |
| `GET` | `/runs/{run_id}/events` | run イベント取得 |
| `GET` | `/runs/{run_id}/graph` | run グラフ取得 |
| `POST` | `/runs/{run_id}/followups` | run への follow-up 質問 |
| `POST` | `/runs/{run_id}/rerun` | run 再実行 |

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
| `GET` | `/society/simulations/{sim_id}/evaluation/summary` | 評価サマリー |
| `GET` | `/society/simulations/{sim_id}/narrative` | narrative 出力 |
| `GET` | `/society/simulations/{sim_id}/demographics` | demographic 集計 |
| `GET` | `/society/simulations/{sim_id}/propagation` | 伝播データ |
| `GET` | `/society/simulations/{sim_id}/social-graph` | society graph |
| `GET` | `/society/simulations/{sim_id}/agents` | エージェント一覧 |
| `GET` | `/society/simulations/{sim_id}/agents/{agent_id}` | エージェント詳細 |
| `GET` | `/society/simulations/{sim_id}/transcript` | 発話 Transcript |
| `GET` | `/society/simulations/{sim_id}/conversations` | 会話データ |
| `GET` | `/society/simulations/{sim_id}/time-axis` | 時系列分析 |
| `GET` | `/society/simulations/{sim_id}/ensemble` | ensemble 結果 |
| `GET` | `/society/simulations/{sim_id}/report` | society report |
| `GET` | `/admin/costs` | トークン・コスト集計 |
| `GET` | `/admin/quality-metrics` | 品質・fallback 集計 |

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

### 任意の品質チェック

```bash
cd backend
uv run ruff check src
uv run deptry .
```

```bash
cd frontend
pnpm check:dead
```

## リポジトリ構成

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
├── DESIGN.md       # 補足設計メモ
└── CONTRIBUTING.md
```

### フォルダ別メモ

| フォルダ | README に統合した内容 |
| --- | --- |
| `backend/` | FastAPI 起動、DB 初期化、テンプレート seed、SSE、simulation/runs/projects/society/admin API、SQLite/PostgreSQL 切り替え |
| `frontend/` | LaunchPad、Live Simulation、Results、Populations、Compare Setup、Decision Lab、`/api` proxy、Vitest、Playwright |
| `config/` | provider/model、fallback、GraphRAG、人口構成、認知・通信・スケジューリング、grounding データ |
| `templates/` | `business_analysis`、`market_entry`、`policy_impact`、`policy_simulation`、`scenario_exploration`、expert/PM persona |
| `experiments/` | `swarm_validation` の実験 runner、集計、HTML レポート |
| `docs/` | 個別の実装・不具合対応メモ |
| `amplifier/` | Microsoft Amplifier の独立した uv パッケージ。Agent AI の Docker Compose や FastAPI/Vue 実行には不要 |

## 詳細ドキュメント

- 設計メモ: [DESIGN.md](DESIGN.md)
- コントリビュート: [CONTRIBUTING.md](CONTRIBUTING.md)
- 行動規範: [CODE_OF_CONDUCT.md](CODE_OF_CONDUCT.md)
- Frontend README: [frontend/README.md](frontend/README.md)
- Amplifier README: [amplifier/README.md](amplifier/README.md)

## License

Agent AI は AGPL-3.0 です。詳細は [LICENSE](LICENSE) を参照してください。

`amplifier/` は同梱された別プロジェクトで、独自の [amplifier/LICENSE](amplifier/LICENSE) に従います。
