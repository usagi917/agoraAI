# Engineering Review: Full-Stack Design Refresh

## Context
agoraAI のUI/UXを非技術者向けに全面リフレッシュする計画のエンジニアリングレビュー。
デザインドキュメント: `~/.gstack/projects/usagi917-agoraAI/you-fix/simulation-numerical-stability-and-dedup-20260331-design-20260401-133454.md`
実装ブランチ: 新規 `feat/design-refresh` を切る（現ブランチとは独立）

## Step 0: Scope — ACCEPTED (フェーズ分割)

5フェーズ → 6フェーズに修正（Phase 3分割）。各フェーズ独立マージ可能。

## What Already Exists

| 領域 | 既存コード | 再利用 |
|-----|----------|-------|
| デザイントークン | `frontend/src/style.css:1-36` | ✓ 拡張 |
| SSEインフラ | `backend/src/app/sse/manager.py` (136イベント対応) | ✓ 追加のみ |
| 3Dグラフ | `frontend/src/composables/useForceGraph.ts` (3d-force-graph + Three.js) | ✓ カスタム拡張 |
| SSEハンドラ | `frontend/src/composables/useSimulationSSE.ts` (888行) | ⚠️ 要分割 |
| ストア群 | `frontend/src/stores/` (9ストア) | ✓ 拡張 |
| テスト | frontend 6テスト, backend 72テスト | ✓ 追加 |

## 修正済みフェーズ順序

Codex指摘を反映: 技術リスクを先行退治 + Phase 3を分割。

```
IMPLEMENTATION ORDER
═══════════════════════════════════════

Phase 1: デザイントークン + 基盤
  ├── style.css にtype scale追加 (--text-xs ~ --text-3xl)
  ├── ボタンバリアント (secondary, ghost, danger)
  ├── Card, Badge, ProgressBar コンポーネント統一
  └── @media print スタイル検証（PDF戦略のスパイク）

Phase 2: LaunchPad リデザイン
  ├── ヒーロービジュアル（3秒で「何ができるか」伝える）
  ├── 質問テンプレート → カード型UI
  ├── プリセット → ビジュアル比較
  └── 実行履歴サムネイル

Phase 3a: ライブ Theater UI（ライブのみ、永続化なし）
  ├── useTheaterSSE.ts 新設（5イベント処理）
  ├── 3Dグラフ: 共有ジオメトリ + シェーダーパルス
  ├── カメラフォーカス（優先度キュー）
  ├── デベートカード（右パネル）
  └── Backend: 5 SSEイベント発火ロジック追加

Phase 3b: イベント永続化 + リプレイ（価値検証後）
  ├── simulation_events テーブル + マイグレーション
  ├── GET /api/simulations/{id}/events
  ├── クライアントサイド タイムライン再生
  └── ※ Phase 3a の価値確認後にのみ着手

Phase 4: Results + PDF
  ├── Decision Brief カード型レイアウト
  ├── シナリオ比較（単一実行内フェーズ間）
  ├── @media print 最適化レポートページ
  └── html2canvas+jsPDF ワンクリックPDFダウンロード

Phase 5: Population + 仕上げ（低優先度）
  └── スキップしてもMVP成立
```

## Architecture Decisions

### 1. SSEハンドラ分割 [P2]
888行の `useSimulationSSE.ts` に直接追加せず、`useTheaterSSE.ts` を新設。
`useCognitiveSSE.ts` が既にこのパターンを示している。

### 2. 3Dグラフ最適化 [P1] — InstancedMesh却下
`3d-force-graph` の `nodeThreeObject` と矛盾するため、代わりに:
- SphereGeometry 共有（1インスタンスを全ノードで参照）
- ShaderMaterial の uniform でパルスアニメーション制御
- LOD: カメラ距離50unit+でラベル非表示
- FPS 25fps以下でアニメーション自動ダウングレード

### 3. alliance_formed 検出 [P2]
- 閾値ベースグルーピング（O(n log n)）
- 連合サイズ上限: エージェント数の50%
- stance差分0.15以内で同一連合判定

### 4. PDF戦略 [P1] — 簡素化
~~Paged.js + html2canvas + Puppeteer~~ →
- `@media print` CSS でHTMLレポートを印刷最適化（ゼロ依存）
- `html2canvas` + `jsPDF` でワンクリックPDFダウンロードボタン
- CJK問題なし（ブラウザが処理）、追加依存最小限

### 5. リプレイ後回し [P1] — Codex推奨
Phase 3aでライブTheaterの価値を検証してから永続化を判断。
未検証機能にバックエンド複雑度を先行投資しない。

## Test Plan

各Phaseで追加するテスト:

| Phase | テストファイル | 内容 |
|-------|-------------|------|
| 1 | `style.spec.ts` | CSS変数の存在チェック |
| 2 | `LaunchPadPage.spec.ts` 拡張 | ヒーロー表示、カードテンプレート |
| 3a | `useTheaterSSE.spec.ts` 新規 | 5イベントの処理、デベートカード更新 |
| 3a | `test_theater_events.py` 新規 | stance_shifted検出、alliance_formed境界値 |
| 4 | `ResultsPage.spec.ts` 拡張 | Decision Brief表示、PDFダウンロードボタン |

## Failure Modes

| 障害 | 対策 |
|-----|------|
| SSE切断中のTheaterイベント | 再接続後に最新状態をGETで取得 |
| alliance_formed 全員同stance | サイズ上限50%で巨大連合を防止 |
| html2canvas CSSレンダリング差異 | @media printを主軸にし、html2canvasは補助 |
| タイムライン0件 | 「イベントなし」プレースホルダー表示 |

## NOT in Scope

- モバイルファースト対応、i18n、Storybook、ダーク/ライト切替
- イベント永続化・リプレイ（Phase 3b、価値検証後）
- デモデプロイ（Phase 4完了後に検討）
- Pinia ストア統合（段階的に）

## Worktree Parallelization

- **Lane A**: Phase 1 → Phase 2 → Phase 3a-FE → Phase 4 (frontend, sequential)
- **Lane B**: Phase 3a-BE (backend SSEイベント発火, independent)

Launch A + B in parallel. Phase 4 は両方完了後。
**Conflict flag**: Phase 3a の FE/BE は `useTheaterSSE.ts` のイベント型定義を共有。
→ イベントスキーマ(TypeScript型)を先に合意してから並行開始。

## Verification

各Phase完了時:
1. `cd frontend && pnpm dev` でローカル確認
2. `cd frontend && pnpm test` でVitest実行
3. `cd backend && uv run pytest` でバックエンドテスト
4. Phase 3a: ブラウザでシミュレーション実行、ライブアニメーション確認
5. Phase 4: Cmd+P で印刷プレビュー、PDFダウンロードボタン確認

## Completion Summary

- Step 0: Scope Challenge — scope accepted with phase split
- Architecture Review: 5 issues found, all resolved
- Code Quality Review: 2 issues found (type scale, button variants)
- Test Review: diagram produced, 15 gaps identified
- Performance Review: 1 issue found (animation priority queue)
- NOT in scope: written
- What already exists: written
- TODOS.md updates: 0 items (no TODOS.md exists, not creating one)
- Failure modes: 1 critical gap flagged (alliance_formed edge case)
- Outside voice: ran (codex), 3 recommendations accepted (Phase 3 split, PDF simplification, replay deferral)
- Parallelization: 2 lanes, 1 parallel / 1 sequential
- Lake Score: 3/3 recommendations chose complete option

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
