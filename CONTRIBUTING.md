# Contributing to Agent AI

Agent AI へのコントリビューションを歓迎します。

## 開発環境のセットアップ

### 必要なツール

- **Python 3.11+** + [uv](https://docs.astral.sh/uv/)
- **Node.js 20+** + [pnpm](https://pnpm.io/)
- **Docker** + Docker Compose

### セットアップ手順

```bash
# リポジトリをクローン
git clone https://github.com/yourname/agent-ai
cd agent-ai

# 依存サービスを起動
docker compose up postgres redis

# バックエンド
cd backend
uv sync --extra dev
uv run pytest  # テストが通ることを確認

# フロントエンド
cd ../frontend
pnpm install
pnpm build  # ビルドが通ることを確認
pnpm dev    # 開発サーバー起動
```

## パッケージマネージャー

- **Python**: `uv` のみ使用してください（pip, poetry, pipenv は不可）
- **JavaScript/TypeScript**: `pnpm` のみ使用してください（npm, yarn は不可）

## プルリクエスト

1. フォークしてブランチを作成
2. 変更を加え、テストを追加
3. `uv run pytest` と `pnpm build` が通ることを確認
4. プルリクエストを作成

### コミットメッセージ

```
feat: 新機能の説明
fix: バグ修正の説明
docs: ドキュメント変更
refactor: リファクタリング
test: テスト追加・修正
```

## Issue

バグ報告や機能リクエストは GitHub Issues で受け付けています。

## ライセンス

コントリビューションは AGPL-3.0 ライセンスの下で提供されます。
