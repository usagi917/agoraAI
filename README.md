# Agent AI

[![English](https://img.shields.io/badge/lang-English-blue.svg)](README.en.md)
[![License: AGPL-3.0](https://img.shields.io/badge/License-AGPL--3.0-blue.svg)](LICENSE)
[![Python 3.11+](https://img.shields.io/badge/python-3.11%2B-blue.svg)](backend/pyproject.toml)
[![Node.js 20+](https://img.shields.io/badge/node-20%2B-339933.svg)](frontend/package.json)
[![Docker Compose](https://img.shields.io/badge/docker-compose-2496ED.svg)](docker-compose.yml)

> プロンプトや `.txt` / `.md` / `.pdf` 文書から世界モデルを構築し、ライブシミュレーション、シナリオ比較、PM 観点の統合評価、3D ナレッジグラフ可視化までを一貫して扱う FastAPI + Vue 3 アプリです。

[クイックスタート](#クイックスタート) · [ローカル開発](#ローカル開発) · [フロントエンド](#フロントエンド) · [バックエンド](#バックエンド) · [設定](#設定) · [API](#api)

## 概要

Agent AI は FastAPI バックエンドと Vue 3 + Vite フロントエンドで構成されています。起動時に `templates/ja/*.yaml` を DB に自動シードし、入力プロンプトまたはアップロード文書をもとに世界モデルを構築します。ライブ実行中は SSE で進捗とグラフ差分を配信し、結果画面ではレポート、シナリオ分布、PM Board 評価、認知状態、タイムライン、3D グラフ履歴を確認できます。

フロントエンドの通常起動導線は `pipeline` 固定です。API からは `single` / `swarm` / `hybrid` / `pm_board` を直接実行できます。`society` は引き続き experimental 扱いで、production 推奨導線からは外しています。

### 実行モード

| Mode | 用途 |
| --- | --- |
| `pipeline` | `single -> swarm -> pm_board` を順番に実行する既定モード |
| `single` | 単一ランで世界モデル構築、ラウンド進行、レポート生成まで実行 |
| `swarm` | 複数 Colony で多視点検証し、シナリオ分布と合意度を集約 |
| `hybrid` | `swarm` と同じ統一 API で実行される多 Colony 系モード |
| `pm_board` | PM ペルソナ群と Chief PM で事業・施策を評価 |
| `society` | experimental。合成人口ベースの社会シミュレーション |

### 実行プロファイル

`config/swarm_profiles.yaml` の実値に基づく既定プロファイルです。

| Profile | Single ラウンド数 | Swarm Colony 数 | Swarm ラウンド数 |
| --- | --- | --- | --- |
| `preview` | 2 | 3 | 2 |
| `standard` | 4 | 5 | 4 |
| `quality` | 6 | 8 | 6 |

## クイックスタート

Docker Compose で一式起動できます。

```bash
docker compose up --build
```

- アプリ: `http://localhost:3000`
- FastAPI Docs: `http://localhost:8000/docs`
- API キー不要のサンプル結果: `http://localhost:3000/sample/sample-business-001`, `http://localhost:3000/sample/sample-pmboard-001`
- `OPENAI_API_KEY` 未設定でも起動できます。その場合はサンプル閲覧のみ有効で、ライブ実行ボタンは無効化されます
- LaunchPad からのライブ実行は既定で `strict evidence` を使います。文書なしの prompt-only 実行は `Unsupported` になることがあります

ライブ実行も使う場合:

```bash
OPENAI_API_KEY=sk-... docker compose up --build
```

またはリポジトリ直下に `.env` を置いて `OPENAI_API_KEY=...` を設定してください。Docker Compose はシェル環境変数または `.env` を自動で拾います。

`frontend` コンテナは静的ビルド済みアセットを Nginx で配信します。フロントエンドをホットリロードしながら触る場合は、次のローカル開発手順を使ってください。

## ローカル開発

前提:

- Python 3.11+
- `uv`
- Node.js 20+
- `pnpm`
- Docker Desktop または Docker Compose

依存サービスだけ Docker で起動する場合:

```bash
docker compose up postgres redis
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
- Vite 開発サーバーは `/api` を `http://localhost:8000` にプロキシします

PostgreSQL を使いたくない場合は、`.env` の `DATABASE_URL` を SQLite 用 `aiosqlite` URL に変更してください。バックエンド側で親ディレクトリは自動作成されます。

## フロントエンド

フロントエンドは Vue Router + Pinia 構成で、3D グラフ表示には `3d-force-graph` と `three` を使っています。

| Route | 画面 | 実装内容 |
| --- | --- | --- |
| `/` | LaunchPad | テンプレート選択、`preview` / `standard` / `quality` 切り替え、プロンプト入力、文書アップロード、最近の実行履歴、サンプル結果導線 |
| `/sim/:id` | Live Simulation | SSE で進捗、Colony 状態、アクティビティログ、グラフ差分を受信して可視化 |
| `/sim/:id/results` | Results | レポート、シナリオ比較、合意ヒートマップ、PM Board、認知ビュー、フォローアップ質問、再実行 |
| `/sample/:id` | Sample Result | `sample_results/*.json` を API 経由で表示 |

フロントエンドの API ベース URL は `VITE_API_BASE_URL` があればそれを使い、未指定時は `/api` を使います。ローカル開発では Vite proxy、Docker では `frontend/nginx.conf` のリバースプロキシが `/api` をバックエンドへ中継します。

## バックエンド

バックエンドは FastAPI + SQLAlchemy async 構成です。起動時に DB 初期化とテンプレート投入を行い、`POST /simulations` で作成された統一 Simulation レコードを `simulation_dispatcher.py` がモード別実行フローへ振り分けます。

主な実装ポイント:

- `backend/src/app/services/pipeline_orchestrator.py`
  `single -> swarm -> pm_board` の 3 段階パイプラインを実行
- `backend/src/app/services/simulator.py`
  単一ランの世界モデル構築、GraphRAG、ラウンド進行、レポート生成を担当
- `backend/src/app/services/swarm_orchestrator.py`
  Colony 群の並列実行と集約を担当
- `backend/src/app/services/pm_board_orchestrator.py`
  PM ペルソナ分析と Chief PM 統合を担当
- `backend/src/app/services/quality.py`
  evidence bundle、quality gate、citation 付与を担当
- `backend/src/app/services/verification.py`
  world / report / PM Board / scenario の独立 verification を担当
- `config/graphrag.yaml`
  既定で `enabled: true`。文書入力がある場合に GraphRAG パイプラインを有効化
- `config/cognitive.yaml`
  既定で `cognitive.mode: advanced`。認知系 SSE イベントと結果画面の認知タブに反映

## 設定

### 主要な環境変数

| 変数 | 用途 |
| --- | --- |
| `OPENAI_API_KEY` | ライブ実行時の LLM 呼び出しに必須 |
| `LLM_MODEL` | `config/models.yaml` に明示設定がない場合の既定モデル |
| `DATABASE_URL` | 既定は PostgreSQL。SQLite (`aiosqlite`) も利用可能 |
| `BACKEND_HOST` / `BACKEND_PORT` | 手動で `uvicorn` を起動する時の待受設定 |
| `VITE_API_BASE_URL` | フロントエンドが明示的に使う API ベース URL。未指定時は `/api` |
| `MAX_CONCURRENT_COLONIES` | Swarm 実行時の Colony 並列数上限 |
| `MAX_CONCURRENT_AGENTS` | LLM クライアント側の同時実行上限。Game Master 側は主に `config/cognitive.yaml` を参照 |
| `COGNITIVE_MODE` | `config/cognitive.yaml` に値がない場合のフォールバック |
| `MAX_ACTIVE_AGENTS` | `.env.example` にはあるが、現行の Game Master 設定は主に `config/cognitive.yaml` を参照 |
| `REDIS_URL` | `.env.example` と Docker Compose にはあるが、現行コードでは直接参照されていない |

### 主要な設定ファイル

| ファイル | 内容 |
| --- | --- |
| `.env.example` | 環境変数テンプレート |
| `config/models.yaml` | タスク別モデルルーティング |
| `config/cognitive.yaml` | BDI、Memory、ToM、Game Master、スケジューリング設定 |
| `config/graphrag.yaml` | GraphRAG の抽出・重複解決・コミュニティ設定 |
| `config/swarm_profiles.yaml` | プロファイルごとの Colony 数とラウンド数 |
| `config/perspectives.yaml` | Colony に割り当てる視点定義 |
| `templates/ja/*.yaml` | ユーザー向け分析テンプレート |
| `templates/ja/pm_board/*.yaml` | PM Board 用ペルソナ別テンプレート |

## API

通常は統一された `/simulations` API を使う想定です。

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
GET  /simulations/{sim_id}/colonies
GET  /simulations/{sim_id}/timeline
POST /simulations/{sim_id}/followups
POST /simulations/{sim_id}/feedback
POST /simulations/{sim_id}/rerun

GET  /admin/costs
GET  /admin/quality-metrics
```

後方互換用に `/runs` と `/swarms` ルーターも残っていますが、新規利用は `/simulations` を推奨します。

作成例:

```bash
curl -X POST http://localhost:8000/simulations \
  -H "Content-Type: application/json" \
  -d '{
    "template_name": "business_analysis",
    "execution_profile": "standard",
    "mode": "pipeline",
    "prompt_text": "EVバッテリー市場への新規参入戦略を分析する"
  }'
```

## 開発時の確認

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
pnpm test:e2e
```

## プロジェクト構成

```text
.
├── backend/              # FastAPI, SQLAlchemy, orchestration, tests
├── frontend/             # Vue 3, Vite, Pinia, 3D graph UI
├── config/               # models / cognition / GraphRAG / swarm profiles
├── templates/ja/         # 分析テンプレートと PM Board テンプレート
├── sample_inputs/        # 入力用サンプル文書
├── sample_results/       # API キー不要の結果サンプル
├── data/                 # SQLite 利用時のローカルデータ置き場
├── docker-compose.yml
└── README.en.md
```

## Contributing

開発フローとツール方針は [CONTRIBUTING.md](CONTRIBUTING.md) を参照してください。

## License

このプロジェクトは [AGPL-3.0](LICENSE) の下で提供されています。
