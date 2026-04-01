# Design Refresh — Task Checklist

## 完了済み

- [x] Phase 1: デザイントークン + type scale + spacing scale + ボタンバリアント + @media print
- [x] Phase 2: LaunchPad 日本語ヒーロー + テンプレート先行 + 空状態 + 仕組み折りたたみ
- [x] Phase 3a-BE: theater_events.py (claim_made, stance_shifted, alliance_formed, market_moved, decision_locked) + 34テスト
- [x] Phase 3a-FE: theaterStore + useTheaterSSE + DebateCards.vue + SimulationPage統合 + layoutRules更新
- [x] Phase 4: ResultsPage PDFダウンロードボタン (html2canvas + jsPDF)

## Batch A: 3Dアニメーション (高優先度)

- [x] A1: シェーダーパルスアニメーション (useForceGraph.ts — SphereGeometry共有 + ShaderMaterial u_pulse uniform)
- [x] A2: カメラフォーカス優先度キュー (decision_locked > alliance_formed > stance_shifted > claim_made, 500ms ease-out)

## Batch B: Results 画面改善 (高優先度)

- [x] B1-Red: DecisionBrief カード型レイアウトのテスト作成
- [x] B1-Green: DecisionBrief.vue をカード型に再構成 (1文結論+信頼度ゲージ → 詳細セクション)
- [x] B1-Refactor: 新デザイントークン適用、不要CSS削除
- [x] B2: @media print レポートページ最適化 (Results固有 print styles, .no-print, A4収まり)

## Batch C: UX改善 (中優先度)

- [x] C1-Red: Notification API のテスト作成 (useSimulationSSE.spec.ts)
- [x] C1-Green: simulation_completed 時にブラウザ通知発火
- [x] C2-Red: SSE再接続リカバリのテスト作成
- [x] C2-Green: EventSource onerror → 自動再接続(max 3回, 指数バックオフ) + GET最新状態
- [x] C3: テンプレートカード色差別化 (市場=青, 製品=緑, 政策=紫, シナリオ=オレンジ)
- [x] C4: prefers-reduced-motion でアニメーション無効化 (style.css)

## Batch D: 低優先度 / 価値検証後

- [x] D1: LaunchPad 実行履歴「実行中」バッジ (pulse-dot) + ステータス日本語化
- [x] D2: プリセットカード Standard「おすすめ」ハイライト
- [x] D3: WebGL非対応 2D SVGフォールバック (Vue内蔵 force simulation)
- [x] D4: DESIGN.md 作成 (トークン値の正式ドキュメント)
- [ ] D5: Phase 3b: イベント永続化 + リプレイ (ユーザーテスト後に判断)
- [x] D6: Phase 5: Population ビジュアル + fork差分

## ユーザーテスト

- [ ] 非技術者1人にアプリを見せてフィードバック収集 (Batch A+B 完了後)
