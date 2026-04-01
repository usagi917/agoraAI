# Design Refresh — 残りタスク実装プラン

## Context

agoraAI デザインリフレッシュの初期フェーズ(Phase 1-4)が完了。5コミットで基盤が整った。
このプランは残りのタスクを優先度順に整理し、実装可能な単位に落とし込む。

ブランチ: `feat/design-refresh`

## 完了済み (5 commits)

| Commit | 内容 |
|--------|------|
| `9dd20e0` | Phase 1: デザイントークン(type scale, spacing, ボタンバリアント, print styles) |
| `bc377a1` | Phase 2: LaunchPad日本語化、空状態、仕組み折りたたみ |
| `7323cba` | Phase 3a-BE: 5 Theater SSEイベント + 34テスト |
| `804d8aa` | Phase 3a-FE: theaterStore, useTheaterSSE, DebateCards, タブ統合 |
| `5e13533` | Phase 4: html2canvas+jsPDF PDFダウンロードボタン |

## 残りタスク — 実装プラン

### Batch A: 3Dアニメーション (高優先度)

#### A1. シェーダーパルスアニメーション
- **ファイル:** `frontend/src/composables/useForceGraph.ts`
- **やること:** `nodeThreeObject` コールバック内で SphereGeometry を共有化。ShaderMaterial に `u_pulse` uniform を追加し、theaterStore の `latestClaim` 変化時にパルス発火
- **既存コード:** `useForceGraph.ts:80-120` の nodeThreeObject、`theaterStore.ts` の claims reactive
- **テスト:** 手動確認(ブラウザでシミュレーション実行)

#### A2. カメラフォーカス優先度キュー
- **ファイル:** `frontend/src/composables/useForceGraph.ts`
- **やること:** Theater イベント受信時にカメラを対象ノードへ 500ms ease-out で遷移。優先度: decision_locked > alliance_formed > stance_shifted > claim_made。同時発火時は最高優先度のみ
- **既存コード:** `useForceGraph.ts` の graph インスタンスの `cameraPosition()` メソッド
- **テスト:** 手動確認

### Batch B: Results 画面改善 (高優先度)

#### B1. Decision Brief カード型レイアウト
- **ファイル:** `frontend/src/components/DecisionBrief.vue`
- **やること:** 既存の Decision Brief 表示をカード型に再構成。1文結論 + 信頼度ゲージ(上部) → 詳細セクション(下部)。新デザイントークン(--text-*, --space-*)適用
- **既存コード:** `DecisionBrief.vue` の既存テンプレート、`ResultsPage.vue` の unifiedReport computed
- **テスト:** `ResultsPage.spec.ts` 拡張

#### B2. @media print レポート最適化
- **ファイル:** `frontend/src/pages/ResultsPage.vue`, `frontend/src/components/DecisionBrief.vue`
- **やること:** Results ページ固有の print スタイル追加。`.no-print` でナビ/ボタン非表示。Decision Brief を A4 に収まるレイアウトに。グラフは Canvas→PNG スナップショット
- **既存コード:** `style.css` の `@media print` 基盤(Phase 1で追加済み)
- **テスト:** ブラウザ Cmd+P で印刷プレビュー確認

### Batch C: UX改善 (中優先度)

#### C1. ブラウザ通知 (Notification API)
- **ファイル:** `frontend/src/composables/useSimulationSSE.ts`
- **やること:** `simulation_completed` イベント受信時に `Notification.requestPermission()` → `new Notification('分析完了', ...)` 発火。SimulationPage の onMounted で権限リクエスト
- **テスト:** `useSimulationSSE.spec.ts` でモック検証

#### C2. SSE再接続後の最新状態リカバリ
- **ファイル:** `frontend/src/composables/useSimulationSSE.ts`
- **やること:** EventSource の onerror で自動再接続(最大3回、指数バックオフ)。再接続成功後に `GET /api/simulations/{id}` で最新状態を取得しストアに反映
- **既存コード:** `useSimulationSSE.ts:40-60` の EventSource 生成部分
- **テスト:** `useSimulationSSE.spec.ts` でモック検証

#### C3. テンプレートカード差別化 (AI slop防止)
- **ファイル:** `frontend/src/pages/LaunchPadPage.vue`
- **やること:** 4テンプレートカードに個別のアクセントカラーを設定。市場分析=青、製品受容=緑、政策影響=紫、シナリオ比較=オレンジ。カード上部に色付きバーを追加
- **テスト:** 目視確認 + 既存 LaunchPadPage.spec.ts がパスすること

#### C4. prefers-reduced-motion 対応
- **ファイル:** `frontend/src/style.css`
- **やること:** `@media (prefers-reduced-motion: reduce)` でアニメーション duration を 0.01ms に。pulse-dot, breathe, shimmer, slide-in-right を対象
- **テスト:** ブラウザの開発者ツールで reduced-motion を有効にして確認

### Batch D: 低優先度 / 価値検証後

#### D1. LaunchPad 実行履歴「実行中」バッジ
- **ファイル:** `frontend/src/pages/LaunchPadPage.vue`
- **やること:** status=running のシミュレーションに pulse-dot アニメーション付きバッジ

#### D2. プリセットカード Standard ハイライト
- **ファイル:** `frontend/src/pages/LaunchPadPage.vue`
- **やること:** Standard プリセットに「おすすめ」バッジ + 若干大きめのカードサイズ

#### D3. WebGL非対応 2D SVGフォールバック
- **ファイル:** `frontend/src/pages/SimulationPage.vue`
- **やること:** WebGLRenderingContext 未対応時に D3.js force layout で 2D 表示

#### D4. DESIGN.md 作成
- **ファイル:** `DESIGN.md` (新規)
- **やること:** style.css のトークン値を正式ドキュメント化

#### D5. Phase 3b: イベント永続化 + リプレイ
- **ファイル:** backend models, API, frontend timeline
- **条件:** 非技術者ユーザーテスト後にのみ着手

#### D6. Phase 5: Population ビジュアル
- **ファイル:** `frontend/src/pages/PopulationPage.vue`
- **条件:** Batch A-C 完了後

### 最重要: ユーザーテスト
- **条件:** Batch A-B 完了後
- **やること:** 非技術者1人にアプリを見せて反応を記録
- **目的:** 改善前のベースライン取得、Phase 3b (リプレイ) の必要性判断

## 実装順序

```
Batch A (3Dアニメ)  ─→ Batch B (Results) ─→ ユーザーテスト
                                             ↓
Batch C (UX改善)   ─→ (並列可)            判断: D5やるか？
                                             ↓
                                          Batch D (低優先)
```

### 並列化

- **Lane A:** A1 → A2 (useForceGraph.ts, sequential)
- **Lane B:** B1 → B2 (DecisionBrief + ResultsPage, sequential)
- **Lane C:** C1 + C2 (useSimulationSSE.ts, sequential) | C3 + C4 (独立、並列可)

Lane A と Lane B は完全に独立。同時に worktree で並列実行可能。
Lane C は A/B 完了後でも並列実行中でも可。

## Verification

各Batch完了時:
1. `cd frontend && pnpm vitest run` — 全テストパス
2. `cd backend && uv run pytest tests/test_theater_events.py` — Theater テストパス
3. `pnpm dev` でブラウザ確認
4. Batch B後: Cmd+P で印刷プレビュー

## Design Review Additions (plan-design-review)

### Information Hierarchy

```
LaunchPad (/):  1st ヘッドライン + テンプレート4枚 → 2nd プリセット選択 → 3rd 自由入力 → below fold 実行履歴
Live (/sim/:id): 1st 3Dグラフ(60%) → 2nd デベートカード(右25%) → 3rd フェーズプログレス(上部)
Results:         1st Decision Brief サマリ(1文+信頼度) → 2nd 詳細タブ → 3rd アクションバー(PDF/再実行)
```

### Interaction States

| Feature | Loading | Empty | Error | Success |
|---------|---------|-------|-------|---------|
| テンプレート | スケルトン4枚 | N/A | API失敗→リトライ | テンプレ表示 |
| 実行履歴 | shimmer 3行 | 「最初の質問を投げてみましょう」 | 静かにスキップ | サムネ付きリスト |
| 3Dグラフ | パーティクル渦巻き | 「エージェント生成中...」 | WebGL非対応→2Dフォールバック | ノード+物理シミュ |
| デベートカード | パルスプレースホルダ | 「議論開始を待機中」 | SSE切断→「再接続中...」 | カード入替アニメ |
| Decision Brief | セクション別shimmer | N/A | 「もう一度実行」ボタン | フルBrief |
| PDF | 「作成中...」バー | N/A | 「Cmd+Pをお試しください」 | DLリンク |

### User Journey Emotional Arc

| Step | Action | Emotion | Design Support |
|------|--------|---------|---------------|
| 1 | LaunchPad着地 | 好奇心 | ヘッドライン+テンプレで即理解 |
| 2 | テンプレ/入力 | 安心 | ウィザードのガイド |
| 3 | プリセット+実行 | 期待 | 時間表示で期待管理 |
| 4 | Live画面 | 驚き | 3Dグラフ初期アニメーション |
| 5 | 議論開始 | 没入 | パルス+デベートカードのリズム |
| 6 | 完了→Results | 達成感 | 完了アニメ+結果サマリ |
| 7 | Brief閲覧 | 理解 | 1文結論+信頼度ゲージ |
| 8 | PDF出力 | 共有意欲 | ワンクリック+プレビュー |

### AI Slop Prevention

- テンプレートカードは均一にしない。質問の性質を色・サイズで差別化
- プリセット5枚は横一列の均一カードを避ける。Standardをデフォルトハイライト
- 分類: APP UI。calm surface hierarchy, dense but readable

### Spacing Scale (Phase 1 追加)

```css
--space-1: 0.25rem; --space-2: 0.5rem; --space-3: 0.75rem;
--space-4: 1rem; --space-6: 1.5rem; --space-8: 2rem;
```

### Responsive Specs

- Desktop (1440px+): 2列テンプレ+サイドプリセット / 3Dグラフ60%+右パネル25% / 2カラムResults
- Tablet (640-900px): 2列テンプレ+下プリセット / 3Dグラフ全幅+下部タブ / 1カラム+タブ
- Mobile (<640px): 1列テンプレ / 3Dグラフ全幅+オーバーレイ / 1カラム+アコーディオン
- タッチターゲット44px最小、`aria-live="polite"` for デベートカード

### Long-Running Simulation UX

Deep(8min)/Research(10min)向け:
- ブラウザ通知(Notification API)で完了通知
- 離脱→復帰時にSSE再接続+最新状態リカバリ
- LaunchPadの実行履歴に「実行中」バッジ表示

## GSTACK REVIEW REPORT

| Review | Trigger | Why | Runs | Status | Findings |
|--------|---------|-----|------|--------|----------|
| CEO Review | `/plan-ceo-review` | Scope & strategy | 0 | — | — |
| Codex Review | `/codex review` | Independent 2nd opinion | 1 | ISSUES_FOUND | 18 findings, 3 accepted |
| Eng Review | `/plan-eng-review` | Architecture & tests (required) | 1 | CLEAR (PLAN) | 8 issues, 1 critical gap |
| Design Review | `/plan-design-review` | UI/UX gaps | 1 | CLEAR (FULL) | score: 4/10 → 8/10, 6 decisions |

**VERDICT:** ENG + DESIGN CLEARED — ready to implement.
