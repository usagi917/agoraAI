# Agent AI

[![English](https://img.shields.io/badge/lang-English-blue.svg)](README.en.md)
[![License: AGPL-3.0](https://img.shields.io/badge/License-AGPL--3.0-blue.svg)](LICENSE)
[![Python 3.11+](https://img.shields.io/badge/python-3.11%2B-blue.svg)](backend/pyproject.toml)
[![Node.js 20+](https://img.shields.io/badge/node-20%2B-339933.svg)](frontend/package.json)
[![Docker Compose](https://img.shields.io/badge/docker-compose-2496ED.svg)](docker-compose.yml)

> `unified` モードを既定に、プロンプトや `.txt` / `.md` / `.pdf` から社会反応、評議会議論、Decision Brief を生成する FastAPI + Vue 3 アプリです。

[クイックスタート](#クイックスタート) · [主要機能](#主要機能) · [実行モード](#実行モード) · [ローカル開発](#ローカル開発) · [API](#api) · [設定](#設定)

## これは何か

Agent AI は、調査テーマや仮説を入力すると、社会反応の観測、構造化された評議会議論、意思決定向けの要約までを一気通貫で実行するシミュレーションアプリです。

- LaunchPad のライブ実行は `unified` 固定で、`evidence_mode: strict` を使います
- 入力はプロンプト単体、または `.txt` / `.md` / `.pdf` の複数ファイル添付に対応します
- 実行中は SSE で進捗を配信し、結果画面では Decision Brief、シナリオ比較、合意ヒートマップ、認知ビュー、3D グラフを確認できます
- API からは `unified` に加えて `pipeline` / `single` / `swarm` / `hybrid` / `pm_board` / `society` / `society_first` / `meta_simulation` を呼べます
- 起動時に `templates/ja/*.yaml` を DB に seed するので、テンプレート選択式でそのまま試せます

## クイックスタート

フルスタックを最短で立ち上げるなら Docker Compose が一番簡単です。

```bash
cp .env.example .env
# .env に OPENAI_API_KEY=... を設定するとライブ実行まで有効になります
docker compose up --build
```

- アプリ: `http://localhost:3000`
- FastAPI Docs: `http://localhost:8000/docs`
- 既定の provider は `config/models.yaml` の `openai` です

補足:

- `OPENAI_API_KEY` が未設定で provider が `openai` の場合、UI は起動しますがライブ実行は無効になり、`POST /simulations` は 400 を返します
- `/sample/:id` のオフラインデモは `sample_results/*.json` があるときだけ利用できます

## 主要機能

### 既定フロー: `unified`

| Phase | 役割 | 主な出力 |
| --- | --- | --- |
| `society_pulse` | 1,000 人規模の社会反応を集めて論点を要約 | 反応集計、評価、社会サマリー |
| `council` | 名前付きの代表者 10 人で 3 ラウンド議論 | 主張、反証、統合コメント |
| `synthesis` | ReACT ベースで意思決定向けレポートを生成 | Decision Brief、セクション別レポート、合意スコア |

### UI

- `/` の LaunchPad では 4 種類の質問ウィザード、テンプレート選択、自由入力、ファイルアップロード、最近の実行履歴を使えます
- `/sim/:id` では SSE 進捗、Colony 状態、Activity Feed、意見分布、ライブ社会グラフを見られます
- `/sim/:id/results` では Decision Brief、シナリオ比較、確率分布、合意ヒートマップ、メモリ、ToM、社会ネットワーク、KG Explorer を扱えます
- `/populations` では 1,000 人人口の生成、一覧、fork、詳細確認ができます

## 実行モード

| Mode | 用途 |
| --- | --- |
| `unified` | 既定導線。`society_pulse -> council -> synthesis` の 3 フェーズで統合分析 |
| `pipeline` | `single -> swarm -> pm_board` を順番に実行 |
| `single` | 単一ランで世界モデル構築からレポート生成まで実行 |
| `swarm` | 複数 Colony を並列実行してシナリオ分布と合意を集約 |
| `hybrid` | `swarm` 系の API で Deep / Shallow Colony を混在させるモード |
| `pm_board` | PM ペルソナ群と Chief PM で事業案をレビュー |
| `society` | 人口生成と社会反応ダイナミクスを重視するモード |
| `society_first` | 社会反応を先に広く観測し、Issue Colony と backtest に進むモード |
| `meta_simulation` | 複数サイクルを回すメタオーケストレーション |

LaunchPad から直接起動するのは `unified` です。その他のモードは主に API から使う想定です。

## 主要画面

| Route | 画面 | 役割 |
| --- | --- | --- |
| `/` | LaunchPad | テンプレート選択、質問ウィザード、プロンプト入力、文書アップロード、最近の実行履歴 |
| `/sim/:id` | Live Simulation | SSE 進捗、フェーズ表示、Colony 状態、ライブ社会グラフ |
| `/sim/:id/results` | Results | Decision Brief、レポート、比較、認知ビュー、フォローアップ |
| `/sample/:id` | Sample Result | `sample_results/*.json` を使った任意のサンプル表示 |
| `/populations` | Population Explorer | Society 系の人口データ確認 |

レガシーの `/run/:id` や `/swarm/:id` は新ルートへリダイレクトされます。

## API

最小の prompt-only 実行例です。`project_id` がなくてもバックエンド側で自動作成されます。

1. シミュレーションを作成する

```bash
curl -X POST http://localhost:8000/simulations \
  -H "Content-Type: application/json" \
  -d '{
    "mode": "unified",
    "template_name": "business_analysis",
    "execution_profile": "standard",
    "prompt_text": "EVバッテリー市場に参入すべきか分析する",
    "evidence_mode": "strict"
  }'
```

2. SSE で進捗を監視する

```bash
curl -N http://localhost:8000/simulations/SIM_ID/stream
```

3. レポートを取得する

```bash
curl http://localhost:8000/simulations/SIM_ID/report
```

文書を添付したい場合は、先にプロジェクトを作成してからファイルをアップロードします。

```bash
curl -X POST "http://localhost:8000/projects?name=market-entry"

curl -X POST "http://localhost:8000/projects/PROJECT_ID/documents" \
  -F "file=@/absolute/path/to/evidence.md"
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

GET  /society/populations
POST /society/populations/generate
GET  /admin/costs
GET  /admin/quality-metrics
```

後方互換のために `/runs` と `/swarms` も残っていますが、新規利用は `/simulations` を推奨します。

## ローカル開発

前提:

- Python 3.11+
- `uv`
- Node.js 20+
- `pnpm`
- Docker Compose

依存サービスだけ起動する場合:

```bash
docker compose up -d postgres redis
```

バックエンド:

```bash
cd backend
uv sync --extra dev
uv run uvicorn src.app.main:app --reload --host 0.0.0.0 --port 8000
```

フロントエンド:

```bash
cd frontend
pnpm install
pnpm dev
```

- フロントエンド開発サーバー: `http://localhost:5173`
- `VITE_API_BASE_URL` を未設定のままにすると、Vite が `/api` を `http://localhost:8000` にプロキシします
- Docker 版フロントエンドは Nginx 経由で `/api` をバックエンドへ中継します

PostgreSQL を使わずに試したい場合は、`.env` の `DATABASE_URL` を SQLite の `aiosqlite` URL に切り替えられます。

## テストと確認

バックエンド:

```bash
cd backend
uv run pytest
```

フロントエンド:

```bash
cd frontend
pnpm build
pnpm test:unit
pnpm exec playwright install chromium
pnpm test:e2e
```

## 設定

### 主な環境変数

| 変数 | 用途 |
| --- | --- |
| `OPENAI_API_KEY` | 既定の OpenAI 構成でライブ実行を有効化 |
| `GOOGLE_API_KEY` | `config/llm_providers.yaml` の Gemini 系 provider を使う場合に必要 |
| `ANTHROPIC_API_KEY` | Anthropic provider を使う場合に必要 |
| `DATABASE_URL` | 既定は PostgreSQL。SQLite (`aiosqlite`) にも切り替え可能 |
| `LLM_MODEL` | `config/models.yaml` に明示設定がない場合のフォールバック |
| `COGNITIVE_MODE` | `legacy` / `advanced` の切り替え |
| `MAX_CONCURRENT_COLONIES` | Swarm 系の Colony 並列数上限 |
| `MAX_CONCURRENT_AGENTS` | 認知エージェントの同時実行上限 |
| `MAX_ACTIVE_AGENTS` | 認知エージェント総数の上限 |
| `VITE_API_BASE_URL` | フロントエンドの API ベース URL を上書きする場合に使用 |

### 主な設定ファイル

| ファイル | 内容 |
| --- | --- |
| `.env.example` | 環境変数テンプレート |
| `config/models.yaml` | タスク別のモデルルーティングと既定 provider |
| `config/llm_providers.yaml` | マルチ provider 設定 |
| `config/swarm_profiles.yaml` | 実行プロファイルごとの Colony 数とラウンド数 |
| `config/cognitive.yaml` | 認知、Memory、ToM、Game Master 設定 |
| `config/graphrag.yaml` | GraphRAG の抽出・重複解決・コミュニティ設定 |
| `templates/ja/*.yaml` | LaunchPad や API から使う分析テンプレート |
| `templates/ja/pm_board/*.yaml` | PM Board 用ペルソナテンプレート |

## プロジェクト構成

```text
.
├── backend/              # FastAPI, SQLAlchemy, orchestration, tests
├── frontend/             # Vue 3, Vite, Pinia, 3D graph UI
├── config/               # models / providers / cognition / GraphRAG / profiles
├── templates/ja/         # 分析テンプレートと PM Board テンプレート
├── sample_results/       # /sample/:id 用の任意 JSON フィクスチャ
├── data/                 # SQLite 利用時のローカルデータ
├── experiments/          # 実験用スクリプトと検証結果
├── plans/                # 計画メモ
├── docker-compose.yml
├── README.md
└── README.en.md
```

## Contributing

開発フローとツール方針は [CONTRIBUTING.md](CONTRIBUTING.md) を参照してください。

## License

このプロジェクトは [AGPL-3.0](LICENSE) の下で提供されています。
