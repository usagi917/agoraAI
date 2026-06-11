# Agent AI

[![English](https://img.shields.io/badge/lang-English-blue.svg)](README.en.md)
[![CI](https://github.com/usagi917/agoraAI/actions/workflows/ci.yml/badge.svg)](https://github.com/usagi917/agoraAI/actions/workflows/ci.yml)
[![License: AGPL-3.0](https://img.shields.io/badge/License-AGPL--3.0-blue.svg)](LICENSE)
[![Python 3.11+](https://img.shields.io/badge/python-3.11%2B-blue.svg)](backend/pyproject.toml)
[![Node.js 20+](https://img.shields.io/badge/node-20%2B-339933.svg)](frontend/package.json)

> ひとつの問いを入力すると、合成人口の反応、専門家・市民代表の議論、最後の Decision Brief までを作るマルチエージェント分析アプリです。

Agent AI は、事業判断、政策影響、市場参入、将来シナリオなどを「複数の立場から考えたらどう見えるか」として可視化するためのアプリです。ブラウザ画面から質問を入れると、バックエンドが AI エージェントを動かし、途中経過をリアルタイム表示し、最後に判断材料をまとめます。

## まず最初に読むところ

初めて触る人は、この順番だけ見れば大丈夫です。

1. 必要なものを入れる
   - Python 3.11 以上
   - uv
   - Node.js 20 以上
   - pnpm
   - Docker Desktop または Docker Compose（Docker で起動する場合だけ）
2. `.env` を作る
3. `OPENAI_API_KEY` を入れる
4. 起動する
5. ブラウザで `http://localhost:5173` または `http://localhost:3000` を開く

専門用語が分からない場合は、次の理解で十分です。

| 言葉 | ここでの意味 |
| --- | --- |
| backend | AI 実行、DB 保存、API、SSE 配信を担当する Python 側 |
| frontend | ブラウザに表示される Vue 側の画面 |
| `.env` | API キーや DB 接続先を書く設定ファイル |
| API キー | OpenAI などの AI サービスを使うための秘密の文字列 |
| SSE | 実行中の進捗をブラウザへ少しずつ送る仕組み |
| SQLite | ローカルだけで使える軽い DB。最初はこれで十分 |
| PostgreSQL / Redis | Docker 起動時に使う本格運用寄りの DB / キャッシュ |

## いちばん簡単な起動方法

### 方法 A: ローカル開発として起動

普段の開発や動作確認はこれが一番わかりやすいです。初回は依存関係も自動で入ります。

```bash
cp .env.example .env
```

`.env` を開き、少なくとも次を自分の OpenAI API キーに置き換えてください。

```bash
OPENAI_API_KEY=sk-your-key-here
```

起動します。

```bash
./scripts/dev.sh
```

起動できたら、ブラウザで開きます。

- 画面: `http://localhost:5173`
- API docs: `http://localhost:8000/docs`
- Health check: `http://localhost:8000/health`

止めるときは、起動したターミナルで `Ctrl+C` を押します。

ポートを変えたい場合:

```bash
./scripts/dev.sh --backend-port 8001 --frontend-port 5174
```

### 方法 B: Docker Compose で起動

PostgreSQL と Redis もまとめて起動したい場合はこちらです。

```bash
cp .env.example .env
```

`.env` の `OPENAI_API_KEY` を設定してから起動します。

```bash
docker compose up --build
```

起動できたら、ブラウザで開きます。

- 画面: `http://localhost:3000`
- API docs: `http://localhost:8000/docs`
- Health check: `http://localhost:8000/health`

Docker 版では `frontend` は nginx で `:3000` に配信され、`/api` は backend に転送されます。

## 画面での使い方

1. `http://localhost:5173` を開きます。
2. LaunchPad で質問テンプレートを選ぶか、自由入力で質問を書きます。
3. 必要なら `.txt`、`.md`、`.pdf` を添付します。
4. 実行プリセットを選びます。迷ったら `standard` を使います。
5. 実行すると `/sim/:id` に移動し、進捗、会話、社会反応、グラフがリアルタイムで表示されます。
6. 完了後は `/sim/:id/results` で Decision Brief、Transcript、Propagation、再実行、Codex Review を確認できます。
7. 2つの案を比べたい場合は `/compare` から Decision Lab を開始します。

## グラフィックビューの見方

`/sim/:id` の Live Simulation では、中央のグラフィックビューで合成人口、代表者、専門家、ナレッジグラフの関係を確認できます。実行フェーズが進むにつれてノード、エッジ、会話、スタンス変化が追加されます。

| 表示 | 見方 |
| --- | --- |
| ノード | エージェント、人口サンプル、またはナレッジグラフ上のエンティティです。大きいノードやラベル付きノードは、議論や接続の中心になりやすい対象です。 |
| 色 | スタンスや種類を表します。画面内の凡例で、賛成、反対、中立、未確定などの意味を確認します。 |
| エッジ | エージェント同士の関係、会話、またはエージェントとエンティティのつながりです。太い線ほど関係の強さが大きいことを表します。 |
| フェーズ表示 | `Society Pulse`、`Council`、`Synthesis` など、現在どの段階の情報を表示しているかを示します。 |
| agents / edges | 現在表示されているノード数と接続数です。実行が進むほど増えることがあります。 |

基本操作:

- ノードをクリックすると、そのエージェントやエンティティの詳細を開けます。
- エッジにカーソルを合わせると、関係タイプ、対象者、強度が表示されます。
- エッジをクリックすると、その関係に紐づく会話や interaction を確認できます。
- 背景をクリックすると、選択状態を解除できます。
- マウスホイールまたはトラックパッドでズームし、ドラッグで表示位置を動かせます。

右上の `⚙` ではグラフ物理設定を調整できます。ノードが重なって見づらい場合は「反発力」や「ノード間隔」を上げ、全体が広がりすぎる場合は「リンク距離」を下げます。分からなくなったら「リセット」で初期状態に戻します。

レイヤーボタンが出ている場合は、表示対象を切り替えられます。

| ボタン | 意味 |
| --- | --- |
| `P` | 全人口レイヤー。代表者だけでなく、より大きい人口分布を点で表示します。 |
| `S` | ソーシャルエッジ。エージェント間の社会的なつながりを表示します。 |
| `K` | ナレッジグラフ。文書や分析から抽出されたエンティティと関係を表示します。 |
| `L` | エージェントとナレッジグラフのリンクを表示します。 |

見方の目安:

- 最初は色の分布を見て、全体の賛否や中立の偏りを確認します。
- 次に大きいノードや接続の多いノードをクリックし、どの立場が議論を動かしているかを見ます。
- エッジをクリックして、意見が近い集団や対立している集団の会話を確認します。
- `K` と `L` を有効にすると、どの人物・論点・企業・政策がどのエージェントの判断に結びついているかを追いやすくなります。

## 何ができるか

- 5種類の LaunchPad テンプレートから分析を開始できます。
  - `business_analysis`
  - `market_entry`
  - `policy_impact`
  - `policy_simulation`
  - `scenario_exploration`
- `quick` / `standard` / `deep` / `research` / `baseline` の実行プリセットを選べます。
- 添付文書をプロジェクトに保存し、根拠文書として分析に使えます。
- 合成人口の反応、代表者・専門家の議論、意見分布、社会グラフを確認できます。
- Decision Lab で「案 A と案 B」を同じ人口条件で比べられます。
- `/populations` で人口を生成、確認、fork できます。
- Codex CLI を設定すると、完了済みレポートに対して Codex Review を質問できます。

## 全体像

```mermaid
flowchart LR
    Q["問い / テンプレート / 添付文書"] --> F["Frontend<br/>Vue + Vite"]
    F --> A["Backend<br/>FastAPI"]
    A --> P["Project / Document<br/>保存・GraphRAG"]
    A --> D["Dispatcher<br/>preset 正規化"]
    D --> S["Society Pulse<br/>合成人口の反応"]
    S --> C["Council<br/>市民代表 + 専門家"]
    C --> B["Synthesis<br/>Decision Brief"]
    B --> R["Results<br/>判断材料・根拠・次アクション"]
    B --> L["Decision Lab<br/>シナリオ比較"]
    S -. SSE .-> F
    C -. SSE .-> F
    B -. SSE .-> F
```

実行の流れは大きく3段階です。

| 段階 | 内容 |
| --- | --- |
| Society Pulse | 人口設定に基づいて合成人口を作り、代表的な反応を集約します。 |
| Council | 市民代表や専門家が複数ラウンドの議論をします。 |
| Synthesis | 反応、議論、品質情報をまとめて Decision Brief を作ります。 |

## 画面一覧

| URL | 役割 |
| --- | --- |
| `/` | LaunchPad。質問、テンプレート、ファイル、プリセットを選ぶ最初の画面 |
| `/sim/:id` | Live Simulation。実行中の進捗、会話、社会反応、グラフを表示 |
| `/sim/:id/results` | Results。Decision Brief、Transcript、Propagation、再実行、Codex Review |
| `/populations` | Populations。人口生成、一覧、詳細表示、fork |
| `/compare` | Compare Setup。2つのシナリオ比較を開始 |
| `/scenario/:id` | Decision Lab。比較結果、意見シフト、連合マップ、監査タイムライン |

## プリセットの選び方

| Preset | 主なフェーズ | 使う場面 |
| --- | --- | --- |
| `quick` | `society_pulse -> synthesis` | まず早く方向性を見たい |
| `standard` | `society_pulse -> council -> synthesis` | 迷ったらこれ |
| `deep` | `society_pulse -> multi_perspective -> council -> pm_analysis -> synthesis` | 多視点・PM 分析まで深掘りしたい |
| `research` | `society_pulse -> issue_mining -> multi_perspective -> intervention -> synthesis` | 論点抽出や介入比較を重視したい |
| `baseline` | 単一 LLM のベースライン | マルチエージェント結果と比較したい |

旧モード名は内部で変換されます。例: `unified -> standard`、`society_first -> research`、`single -> quick`。

## 設定ファイル

最初に触るのは `.env` だけで十分です。細かく調整したい場合だけ `config/` や `templates/` を見ます。

| やりたいこと | 触る場所 |
| --- | --- |
| API キーを入れる | `.env` |
| ローカル DB を SQLite にする | `.env` の `DATABASE_URL` |
| PostgreSQL を使う | `.env` の `DATABASE_URL` と `docker compose up -d postgres redis` |
| 既定 provider / モデルを変える | `config/models.yaml` |
| OpenAI / Gemini / Anthropic の fallback を変える | `config/llm_providers.yaml` |
| 実行プロファイルを調整する | `config/swarm_profiles.yaml` |
| 人口構成やネットワーク設定を変える | `config/population_mix.yaml` |
| 認知・通信・スケジューリングを変える | `config/cognitive.yaml` |
| GraphRAG / grounding を調整する | `config/graphrag.yaml`, `config/grounding/` |
| LaunchPad のテンプレートを変える | `templates/ja/*.yaml` |

`.env.example` の既定 DB は SQLite です。

```bash
DATABASE_URL=sqlite+aiosqlite:///./data/db.sqlite3
```

PostgreSQL と Redis をローカルで使う場合:

```bash
docker compose up -d postgres redis
```

`.env` を次のようにします。

```bash
DATABASE_URL=postgresql+asyncpg://agentai:agentai@localhost:5432/agentai
REDIS_URL=redis://localhost:6379/0
```

## Codex Review を使う場合

Codex Review は、完了済みレポートを Codex CLI で読み取り専用確認する機能です。通常のシミュレーションには必須ではありません。

使う場合は Codex CLI をインストールしてログインしたうえで、`.env` に設定します。

```bash
CODEX_REVIEW_ENABLED=true
CODEX_BIN=codex
CODEX_REVIEW_TRANSPORT=stdio
CODEX_REVIEW_TIMEOUT_SECONDS=60
CODEX_REVIEW_WORKDIR=/tmp/agora_codex_review_empty
```

v1 は `codex app-server --listen stdio://` の stdio transport のみを使います。旧 `AGORAAI_CODEX_*` 変数も互換 alias として一部読み取ります。

## 開発コマンド

このリポジトリでは Node.js 系は `pnpm`、Python 系は `uv` を使います。`npm`、`yarn`、`pip` は使わないでください。

### Backend

```bash
cd backend
uv sync --extra dev
uv run uvicorn src.app.main:app --reload --host 0.0.0.0 --port 8000
```

テスト:

```bash
cd backend
uv run pytest -q
```

任意の品質チェック:

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

ビルドとテスト:

```bash
cd frontend
pnpm build
pnpm test:unit
pnpm exec playwright install --with-deps chromium
pnpm test:e2e
```

不要ファイルや未使用依存の確認:

```bash
cd frontend
pnpm check:dead
```

## API を直接試す

画面ではなく API を直接試したい場合の最小例です。先に backend を起動してください。

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

返ってきた `id` を `SIM_ID` に入れて進捗を見ます。

```bash
curl -N http://localhost:8000/simulations/SIM_ID/stream
```

完了後のレポート:

```bash
curl http://localhost:8000/simulations/SIM_ID/report
```

## 主要 API

| Method | Endpoint | 役割 |
| --- | --- | --- |
| `GET` | `/health` | 稼働状態と live execution 可否 |
| `GET` | `/templates` | 利用可能なテンプレート一覧 |
| `POST` | `/projects` | ドキュメント添付用プロジェクト作成 |
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
| `POST` | `/simulations/{sim_id}/rerun` | 同条件で再実行 |
| `GET` | `/codex/health` | Codex App Server 接続状態 |
| `POST` | `/simulations/{sim_id}/codex-review` | 完了済みレポートへの Codex review 質問 |
| `POST` | `/scenario-pairs` | シナリオ比較開始 |
| `GET` | `/scenario-pairs/{scenario_pair_id}` | シナリオ比較の状態取得 |
| `GET` | `/scenario-pairs/{scenario_pair_id}/comparison` | 比較結果取得 |
| `POST` | `/populations/{population_id}/snapshot` | シナリオ比較用の人口 snapshot 作成 |

レガシー互換として `/runs` 系の API もあります。

## リポジトリ構成

```text
.
├── backend/        # FastAPI API、SSE、DB、シミュレーション実行、テスト
├── frontend/       # Vue 3 + Vite UI、Pinia stores、可視化、E2E テスト
├── config/         # LLM、認知、人口、GraphRAG、grounding 設定
├── templates/      # LaunchPad テンプレート、専門家、PM ペルソナ
├── scripts/        # ローカル開発補助。主に scripts/dev.sh
├── data/           # ローカル DB などの実行時データ
├── docs/           # 実装メモ、生成 schema
├── experiments/    # single vs swarm などの検証実験
├── evaluation/     # 評価ベースライン
├── plans/          # 開発計画・作業ログ
├── amplifier/      # Agent AI 本体とは別の Amplifier checkout
└── docker-compose.yml
```

### フォルダ別メモ

| フォルダ | 何が入っているか | 初心者向けの注意 |
| --- | --- | --- |
| `backend/` | Python/FastAPI 側。API、SSE、DB、シミュレーション、評価、Codex Review | まずは `uv sync --extra dev` と `uv run uvicorn ...` だけ覚えれば十分です。 |
| `frontend/` | Vue 3 + Vite 側。LaunchPad、Live Simulation、Results、Populations、Decision Lab | ローカルでは `pnpm dev`。`VITE_API_BASE_URL` 未指定時は `/api` を使います。 |
| `config/` | provider、モデル、認知、人口、GraphRAG、grounding データ | 普段は触らなくてよいです。AI モデルや人口条件を変える時だけ見ます。 |
| `templates/` | `business_analysis` などのテンプレート、専門家、PM ペルソナ | テンプレート変更は画面表示と backend seed に影響します。 |
| `scripts/` | 開発用スクリプト | `./scripts/dev.sh` が backend と frontend を同時起動します。 |
| `data/` | SQLite DB などのローカル実行データ | 消すとローカルの履歴や DB が消えることがあります。 |
| `docs/` | 実装メモ、Codex app-server schema | `docs/codex-app-server-schema/` は生成物なので手で直さないでください。 |
| `experiments/` | Swarm 検証実験と集計スクリプト | backend 起動後に実験 runner を使います。 |
| `evaluation/` | 評価ベースライン | リリースや品質確認用の基準データです。 |
| `plans/` | 過去・進行中の実装計画 | 仕様の最終根拠はコードとテストを優先してください。 |
| `amplifier/` | 別プロジェクトの Amplifier パッケージ | Agent AI の起動には不要です。ライセンスも別です。 |

## 実験を動かす

backend を起動してから実行します。

```bash
cd backend
uv run python ../experiments/swarm_validation/run_experiment.py
```

特定ケースだけ実行する場合:

```bash
cd backend
uv run python ../experiments/swarm_validation/run_experiment.py --test-case tc01
```

接続先を変える場合:

```bash
cd backend
uv run python ../experiments/swarm_validation/run_experiment.py --base-url http://localhost:8000
```

集計:

```bash
cd backend
uv run python ../experiments/swarm_validation/aggregate_results.py
```

## CI

GitHub Actions は push / pull request で次を実行します。

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

nightly benchmark は毎日 03:00 JST 相当のスケジュールで backend の retrodiction baseline を作成します。

## よくあるトラブル

| 症状 | 見るところ |
| --- | --- |
| 画面は開くが実行できない | `.env` の `OPENAI_API_KEY` と `http://localhost:8000/health` |
| `http://localhost:5173` が開かない | `./scripts/dev.sh` の frontend ログ、または `cd frontend && pnpm dev` |
| `http://localhost:8000/docs` が開かない | backend ログ、または `cd backend && uv run uvicorn ...` |
| DB エラーが出る | `.env` の `DATABASE_URL`。最初は SQLite のままが簡単です。 |
| Docker で画面は出るが API が動かない | `docker compose ps` と backend healthcheck |
| SSE が途中で止まる | nginx の `/api/simulations/:id/stream` 設定、または Vite proxy |
| E2E が落ちる | `pnpm exec playwright install --with-deps chromium` を実行済みか確認 |

## コードを読む入口

| 知りたいこと | 主なファイル |
| --- | --- |
| アプリ起動、CORS、テンプレート seed、health check | `backend/src/app/main.py` |
| 環境変数、config YAML の読み込み | `backend/src/app/config.py` |
| DB 接続、テーブル作成、SQLite/PostgreSQL 切り替え | `backend/src/app/database.py` |
| API ルート登録 | `backend/src/app/api/routes/__init__.py` |
| シミュレーション作成、SSE、レポート、再実行 | `backend/src/app/api/routes/simulations.py` |
| 実行プリセットの定義と旧モード名の変換 | `backend/src/app/models/simulation.py` |
| `baseline` と unified 実行の振り分け | `backend/src/app/services/simulation_dispatcher.py` |
| `Society Pulse -> Council -> Synthesis` の本体 | `backend/src/app/services/unified_orchestrator.py` |
| 合成人口、社会ネットワーク、反応、伝播、評価 | `backend/src/app/services/society/` |
| LLM の task routing、provider adapter、fallback | `backend/src/app/llm/` |
| フロントエンド route 定義 | `frontend/src/router.ts` |
| REST API client と型定義 | `frontend/src/api/client.ts` |
| SSE 購読とライブ状態更新 | `frontend/src/composables/useSimulationSSE.ts` |
| 実行状態、グラフ、社会、Decision Lab の状態管理 | `frontend/src/stores/` |
| 主要画面 | `frontend/src/pages/` |
| 可視化・結果表示コンポーネント | `frontend/src/components/` |

## 詳細ドキュメント

- 設計メモ: [DESIGN.md](DESIGN.md)
- コントリビュート: [CONTRIBUTING.md](CONTRIBUTING.md)
- 行動規範: [CODE_OF_CONDUCT.md](CODE_OF_CONDUCT.md)
- フロントエンド README: [frontend/README.md](frontend/README.md)
- Amplifier README: [amplifier/README.md](amplifier/README.md)

## License

Agent AI は AGPL-3.0 です。詳細は [LICENSE](LICENSE) を参照してください。

`amplifier/` は同梱された別プロジェクトで、独自の [amplifier/LICENSE](amplifier/LICENSE) に従います。
