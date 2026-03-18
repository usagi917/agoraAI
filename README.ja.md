# Agent AI - リアルタイムグラフ マルチエージェント シミュレーション

入力文書から世界モデルを構築し、複数エージェントによるシミュレーションを実行、リアルタイムグラフ可視化と日本語分析レポートを生成する分析ツール。

## 起動方法

```bash
cp .env.example .env
# .env に OPENAI_API_KEY を設定
docker compose up
```

- フロントエンド: http://localhost:5173
- バックエンド API: http://localhost:8000
- API ドキュメント: http://localhost:8000/docs

## ローカル開発

### バックエンド

```bash
cd backend
uv sync
uv run uvicorn src.app.main:app --reload --port 8000
```

### フロントエンド

```bash
cd frontend
pnpm install
pnpm dev
```

## 機能

- **文書入力**: text / markdown / pdf（複数ファイル対応）
- **テンプレート**: ビジネス分析、政策シミュレーション、シナリオ探索
- **実行プロファイル**: プレビュー（2R）/ スタンダード（4R）/ クオリティ（6R）
- **リアルタイムグラフ**: Cytoscape.js による diff ベース更新
- **SSE ストリーミング**: シミュレーション進捗のリアルタイム配信
- **分析レポート**: 11セクション構成の日本語レポート
- **フォローアップ**: レポートに対する追加質問
- **再実行**: 同一入力での再シミュレーション
- **コスト追跡**: LLM トークン使用量の記録

## 技術スタック

| 層 | 技術 |
|---|---|
| フロントエンド | Vue 3 + Vite + TypeScript |
| 状態管理 | Pinia |
| グラフ | Cytoscape.js |
| バックエンド | FastAPI + Uvicorn |
| DB | SQLAlchemy async + aiosqlite (SQLite) |
| LLM | litellm |
| 通信 | SSE (Server-Sent Events) |

## サンプル入力

`sample_inputs/` ディレクトリに3つのサンプルが用意されています:

- `business_case/` - EV バッテリー市場参入分析
- `policy_case/` - 炭素税導入政策の影響分析
- `scenario_case/` - AI 規制の将来シナリオ分析
