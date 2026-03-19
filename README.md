<div align="center">

# Agent AI

### 1000の認知エージェントが議論し、集合知で意思決定を導く

[![License: AGPL-3.0](https://img.shields.io/badge/License-AGPL%20v3-blue.svg)](LICENSE)
[![Python 3.11+](https://img.shields.io/badge/python-3.11%2B-blue.svg)](backend/pyproject.toml)
[![Node 20](https://img.shields.io/badge/node-20-339933.svg)](frontend/package.json)
[![Docker Compose](https://img.shields.io/badge/docker-compose-2496ED.svg)](docker-compose.yml)
[![English](https://img.shields.io/badge/lang-English-blue.svg)](README.en.md)

**BDI認知アーキテクチャ × GraphRAG × SwarmMind**
— ChatGPT に聞いても、いつも同じ視点。Agent AI は 20人以上の AI エージェントが、それぞれ独自の信念・欲求・意図を持って議論し、多角的な意思決定を支援します。

[クイックスタート](#クイックスタート) · [アーキテクチャ](#アーキテクチャ) · [機能](#機能) · [デモ](#デモ) · [ドキュメント](#ドキュメント)

</div>

---

## なぜ Agent AI？

| 従来のLLM | Agent AI |
|-----------|----------|
| 1つのモデルが1つの視点で回答 | **複数エージェントが独立した認知モデルで議論** |
| 毎回同じ思考パターン | **BDI（信念・欲求・意図）で多様な思考を生成** |
| 文脈を忘れる | **3層メモリ（エピソード・意味・手続き）で記憶を保持** |
| 他者の視点を考慮しない | **Theory of Mind で互いの思考を推論** |
| 平坦な出力 | **構造化討論 + GraphRAG で根拠のある分析** |

## クイックスタート

```bash
git clone https://github.com/yourname/agent-ai
cd agent-ai
cp .env.example .env   # OPENAI_API_KEY を設定
docker compose up
```

ブラウザで `http://localhost:5173` を開く → ドキュメントをアップロード → 分析開始。

> API Key なしでも、同梱のサンプル結果でデモ体験できます。

## アーキテクチャ

```
┌─────────────────────────────────────────────────────────────────┐
│                        Agent AI Platform                         │
├─────────────────────────────────────────────────────────────────┤
│                                                                  │
│  ┌──────────────┐   ┌──────────────┐   ┌──────────────────────┐ │
│  │   入力層      │   │  GraphRAG    │   │   SwarmMind          │ │
│  │              │   │              │   │                      │ │
│  │ .txt .md .pdf│──▶│ エンティティ  │──▶│ N個のColonyが並列実行  │ │
│  │ プロンプト    │   │ 関係抽出      │   │ 視点多様性を担保      │ │
│  │              │   │ コミュニティ   │   │ 主張抽出・クラスタリング│ │
│  └──────────────┘   └──────────────┘   └──────────────────────┘ │
│                                                                  │
│  ┌───────────────────────────────────────────────────────────┐   │
│  │                BDI 認知アーキテクチャ                       │   │
│  │                                                           │   │
│  │  ┌─────────┐  ┌─────────┐  ┌──────────┐  ┌────────────┐  │   │
│  │  │  信念    │  │  欲求    │  │   意図    │  │ Theory of  │  │   │
│  │  │ Beliefs │  │ Desires │  │Intentions│  │   Mind     │  │   │
│  │  └────┬────┘  └────┬────┘  └────┬─────┘  └─────┬──────┘  │   │
│  │       │            │            │               │         │   │
│  │  ┌────▼────────────▼────────────▼───────────────▼──────┐  │   │
│  │  │              3層メモリシステム                        │  │   │
│  │  │  エピソード記憶 │ 意味記憶 │ 手続き記憶 │ 省察       │  │   │
│  │  └────────────────────────────────────────────────────┘  │   │
│  │                                                           │   │
│  │  ┌──────────────────────────────────────────────────────┐ │   │
│  │  │            構造化討論プロトコル                        │ │   │
│  │  │  Game Master │ 因果推論 │ 社会的影響モデル            │ │   │
│  │  └──────────────────────────────────────────────────────┘ │   │
│  └───────────────────────────────────────────────────────────┘   │
│                                                                  │
│  ┌───────────────────────────────────────────────────────────┐   │
│  │                    可視化・出力                             │   │
│  │  3Dグラフ │ タイムライン │ シナリオ比較 │ 合意ヒートマップ   │   │
│  │  BDI状態  │ 記憶ストリーム │ ToMマップ │ KGエクスプローラ   │   │
│  └───────────────────────────────────────────────────────────┘   │
└─────────────────────────────────────────────────────────────────┘
```

## 機能

### 3つの実行モード

| モード | 説明 |
|--------|------|
| **Single** | 1つのシミュレーションで深い分析 |
| **Swarm** | 複数Colonyが並列実行、シナリオ分布を集約 |
| **Hybrid** | Swarmの多様性 + Singleの深さを両立 |

### 10の分析ビュー

| ビュー | 内容 |
|--------|------|
| レポート | 構造化された分析レポート（11セクション） |
| シナリオ比較 | 複数シナリオの確率分布と比較 |
| 合意ヒートマップ | Colony間の合意度マトリクス |
| 3Dグラフ | 時間再生可能な3Dフォースグラフ |
| 認知状態 | エージェントのBDI状態リアルタイム表示 |
| 記憶 | エピソード・意味・手続き記憶のストリーム |
| 評価 | シミュレーション品質評価ダッシュボード |
| ToMマップ | Theory of Mind 関係性ネットワーク |
| 社会NW | 社会ネットワークダイナミクス |
| KG探索 | ナレッジグラフエクスプローラ |

### 認知アーキテクチャの深さ

- **BDI エンジン**: 各エージェントが信念（Beliefs）、欲求（Desires）、意図（Intentions）を保持し、環境変化に応じて更新
- **Theory of Mind**: エージェントが互いの目標と行動を推論し、戦略的に行動
- **3層メモリ**: エピソード記憶（体験）、意味記憶（知識）、手続き記憶（スキル）+ 省察メカニズム
- **構造化討論**: Game Master が矛盾を検出し、因果推論で議論を深化
- **GraphRAG**: 文書からナレッジグラフを自動構築、コミュニティ検出で構造を把握

## デモ

### 最小の体験フロー

1. `http://localhost:5173` を開く
2. 実行モードで `Single` を選択
3. `sample_inputs/business_case/market_entry.md` をアップロード
4. テンプレート `ビジネス分析` を選択
5. プロファイル `Preview` で実行
6. 結果画面で 3D グラフ、レポート、認知状態を確認

### サンプル入力

| サンプル | 内容 |
|---------|------|
| [`market_entry.md`](sample_inputs/business_case/market_entry.md) | EVバッテリー市場参入分析 |
| [`carbon_tax.md`](sample_inputs/policy_case/carbon_tax.md) | 炭素税導入の影響分析 |
| [`ai_regulation.md`](sample_inputs/scenario_case/ai_regulation.md) | AI規制の将来シナリオ分析 |

## ローカル開発

### Backend

```bash
docker compose up postgres redis   # 依存サービス起動
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

### テスト

```bash
cd backend && uv run pytest
cd frontend && pnpm build
```

## テンプレート

| テンプレート | 用途 |
|-------------|------|
| [`business_analysis`](templates/ja/business_analysis.yaml) | 企業・市場・競合・規制の相互作用分析 |
| [`policy_simulation`](templates/ja/policy_simulation.yaml) | 政策に対するステークホルダー反応分析 |
| [`scenario_exploration`](templates/ja/scenario_exploration.yaml) | 不確実性の高い将来分岐の探索 |

## 設定

| ファイル | 内容 |
|---------|------|
| [`.env.example`](.env.example) | API キー、DB、Redis 設定 |
| [`config/models.yaml`](config/models.yaml) | LLM プロバイダ・タスク別モデル設定 |
| [`config/cognitive.yaml`](config/cognitive.yaml) | BDI認知モード、Game Master、ToM設定 |
| [`config/graphrag.yaml`](config/graphrag.yaml) | GraphRAG パイプライン設定 |
| [`config/swarm_profiles.yaml`](config/swarm_profiles.yaml) | Colony数、ラウンド数、温度分布 |
| [`config/perspectives.yaml`](config/perspectives.yaml) | Colony視点フレーム定義 |

## API

統一 `simulations` API を使用してください。

```
POST /simulations              # シミュレーション作成・実行
GET  /simulations              # 一覧取得
GET  /simulations/{id}         # 詳細取得
GET  /simulations/{id}/stream  # SSE ストリーミング
GET  /simulations/{id}/graph   # グラフデータ
GET  /simulations/{id}/report  # レポート取得
POST /simulations/{id}/followups  # フォローアップ質問
```

詳細は `http://localhost:8000/docs`（OpenAPI）を参照。

## プロジェクト構成

```
.
├── backend/           # FastAPI + SQLAlchemy + BDI認知エンジン + GraphRAG
├── frontend/          # Vue 3 + Vite + 3D Force Graph + 10ビューダッシュボード
├── config/            # モデル、認知、GraphRAG、Swarm設定
├── templates/ja/      # 分析テンプレート（YAML）
├── sample_inputs/     # サンプル入力文書
├── docker-compose.yml # PostgreSQL / Redis / Backend / Frontend
└── .env.example       # 環境変数テンプレート
```

## Contributing

[CONTRIBUTING.md](CONTRIBUTING.md) を参照してください。

## License

[AGPL-3.0](LICENSE) — OSSとして自由に使用できます。商用利用についてはお問い合わせください。
