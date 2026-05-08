# QA Report — agoraAI

| Field | Value |
|-------|-------|
| Date | 2026-04-07 |
| URL | http://localhost:3000 |
| Branch | scenario-comparison-validation-20260407 |
| Mode | Diff-aware (feature branch) |
| Tier | Standard |
| Duration | ~15 min |
| Pages tested | 6 (/, /compare, /scenario/:id, /populations, /sim/:id/results, /scenario/invalid) |
| Screenshots | 16 |
| Framework | Vue 3 SPA + FastAPI backend |

## Health Score

| Category | Score | Weight | Weighted |
|----------|-------|--------|----------|
| Console | 100 | 15% | 15.0 |
| Links | 100 | 10% | 10.0 |
| Visual | 92 | 10% | 9.2 |
| Functional | 85 | 20% | 17.0 |
| UX | 85 | 15% | 12.75 |
| Performance | 100 | 10% | 10.0 |
| Content | 100 | 5% | 5.0 |
| Accessibility | 92 | 15% | 13.8 |

**Baseline Health Score: 93 → Final Health Score: 97**

## Top 3 Things Fixed

1. **SimulationProgress が比較ページで機能しない** — SSE 接続と切り離されたシングルトンストアを参照していたため、常に IDLE 表示。SSE イベントベースのインラインプログレスに置き換え。
2. **不正 ID アクセス時に英語エラー表示** — "Request failed with status code 404" → 「比較データが見つかりません」
3. **CompareSetupPage の送信ボタンが空入力でも有効** — LaunchPadPage と一貫して、テーマ未入力時に disabled に変更。

## Issues

### ISSUE-001: SimulationProgress が ScenarioComparisonPage で常に IDLE
- **Severity:** HIGH
- **Category:** Functional
- **Fix Status:** verified
- **Commit:** cde5fde
- **Files Changed:** `frontend/src/pages/ScenarioComparisonPage.vue`
- **Description:** `SimulationProgress` コンポーネントは `useSimulationStore()` シングルトンに依存。ScenarioComparisonPage は `useScenarioPairSSE` を使用しており、ストアとの接続がなかった。結果として両パネルが常に IDLE 表示。
- **Fix:** SSE イベントストリームから最新イベントラベルを表示するインライン進捗インジケーターに置き換え。
- **Before:** screenshots/scenario-progress.png (IDLE 表示)
- **After:** screenshots/issue001-after.png (接続中... + アニメーション付きプログレスバー)

### ISSUE-002: 不正シナリオ ID 時のエラーメッセージが英語
- **Severity:** MEDIUM
- **Category:** UX / Content
- **Fix Status:** verified
- **Commit:** d3d7c81
- **Files Changed:** `frontend/src/pages/ScenarioComparisonPage.vue`
- **Description:** Axios の raw エラーメッセージ "Request failed with status code 404" がそのまま表示。ターゲットユーザー（低デジタルリテラシーの地方議員）にとって不親切。
- **Fix:** 404 の場合は「比較データが見つかりません」、その他は「比較データの読み込みに失敗しました」と日本語メッセージに変更。
- **Before:** screenshots/scenario-invalid.png
- **After:** screenshots/issue002-after.png

### ISSUE-003: CompareSetupPage の送信ボタンが空入力時も有効
- **Severity:** MEDIUM
- **Category:** UX
- **Fix Status:** verified
- **Commit:** 08535a9
- **Files Changed:** `frontend/src/pages/CompareSetupPage.vue`
- **Description:** LaunchPadPage では「分析を開始」ボタンがプロンプト未入力時に disabled になるが、CompareSetupPage の「この条件で比較する」は常に有効で、クリック後にインラインエラーが表示される動作。
- **Fix:** `canSubmit` computed を追加し、`decisionContext` が空のときにボタンを disabled に。
- **Before:** screenshots/compare-empty-submit.png
- **After:** screenshots/issue003-after.png

### ISSUE-004: モバイルでの Stage ラベル文字詰まり (deferred)
- **Severity:** LOW
- **Category:** Visual
- **Fix Status:** deferred
- **Description:** 375px ビューポートでシナリオ比較ページの Stage ラベル（"Stage 2: 多視点検証"）が詰まって読みにくい。ISSUE-001 の修正で SimulationProgress を除去したため、この問題はシナリオ比較ページでは解消。ただし SimulationPage での同様の問題は残存。
- **Screenshot:** screenshots/scenario-mobile.png

### ISSUE-005: THREE.js 非推奨警告 (deferred)
- **Severity:** LOW
- **Category:** Console
- **Fix Status:** deferred
- **Description:** 結果ページで THREE.Clock の非推奨警告。機能には影響なし。
- **Screenshot:** screenshots/completed-sim.png

## Summary

- Total issues found: 5
- Fixes applied: verified: 3, best-effort: 0, reverted: 0
- Deferred issues: 2 (both LOW severity)
- Health score delta: 93 → 97

**PR Summary:** QA found 5 issues, fixed 3, health score 93 → 97.

## Console Health

- Landing page: 0 errors
- Compare setup: 0 errors
- Scenario comparison: 0 errors
- Populations: 0 errors
- Results page: 1 warning (THREE.js deprecation)
- Invalid scenario: 1 expected 404 network error
