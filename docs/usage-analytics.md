# 発表デモの利用ログ

Agent AI は、個人を特定するアカウントやブラウザ・フィンガープリントを使わず、
ブラウザごとのランダムな匿名 ID とタブセッション ID で利用状況を記録する。

## 記録する内容

- セッション開始と閲覧ページ
- シミュレーションの開始、完了、失敗
- 結果画面への到達
- 選択した分析モード、テンプレート、入力方法
- シミュレーションの処理時間と入力内容

利用イベントには入力本文、Cookie、IP アドレスを含めない。入力本文は従来どおり
`simulations.prompt_text` に保存され、集計 API では専用トークンがある場合だけ最大
500 文字のプレビューを返す。Cloudflare のアクセスログは別途保持される。

## 2026年7月16日（木）の集計

JST の 2026-07-16 00:00〜24:00 は UTC の 2026-07-15 15:00〜2026-07-16 15:00。
本番 VPS 上で次を実行する。トークン値は表示しない。

```bash
cd /home/deploy/agentai-thursday
set -a
source .env
set +a
curl -sS \
  -H "X-Analytics-Token: ${ANALYTICS_ADMIN_TOKEN}" \
  "http://127.0.0.1:3300/api/analytics/summary?start=2026-07-15T15:00:00Z&end=2026-07-16T15:00:00Z"
```

レスポンスには次が含まれる。

- `unique_visitors`: 匿名利用者数
- `sessions`: セッション数
- `event_counts`: 操作別件数
- `top_paths`: 閲覧ページ
- `simulations`: 実行数、完了率、失敗数、処理時間中央値
- `by_mode`, `by_template`, `by_input_method`: 使い方の内訳
- `simulation_details`: 入力プレビューと各実行の結果

## 告知

入力画面には次の文言を表示する。

> デモ改善のため、アクセス情報・匿名の利用状況・入力内容を記録します。個人情報や機密情報は入力しないでください。
