# Agent AI

[![English](https://img.shields.io/badge/lang-English-blue.svg)](README.en.md)
[![CI](https://github.com/usagi917/agoraAI/actions/workflows/ci.yml/badge.svg)](https://github.com/usagi917/agoraAI/actions/workflows/ci.yml)
[![License: AGPL-3.0](https://img.shields.io/badge/License-AGPL--3.0-blue.svg)](LICENSE)
[![Python 3.11+](https://img.shields.io/badge/python-3.11%2B-blue.svg)](backend/pyproject.toml)
[![Node.js 20+](https://img.shields.io/badge/node-20%2B-339933.svg)](frontend/package.json)

> ひとつの問いを入力すると、合成人口の反応、評議会ディベート、Decision Brief までを一気通貫で生成するマルチエージェント分析アプリです。

## これは何か

- LaunchPad から4種類の質問テンプレート、または自由入力のプロンプトで分析を開始できます。
- `quick` / `standard` / `deep` / `research` / `baseline` の5つのプリセットで、速度と深さを切り替えられます。
- `.txt` / `.md` / `.pdf` をプロジェクトに添付し、エビデンス付きの分析フローに載せられます。
- ライブ画面では SSE で進捗を配信し、Activity Feed、社会反応、会話、グラフの変化を追跡できます。
- 結果画面では Decision Brief、シナリオ比較、伝播分析、Transcript、再実行、フォローアップ質問を扱えます。
- `/populations` では人口生成、一覧確認、世代 fork ができます。
- Decision Lab では2つのシナリオを同一人口で並行実行し、意見シフト・連合変動・監査証跡を比較できます。
- Theater UI ではディベートカード、ライブ対話ストリーム、スタンス変化をリアルタイムに可視化します。

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
| `POST` | `/scenario-pairs` | シナリオ比較開始 |

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
