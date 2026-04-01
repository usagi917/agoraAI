# Task: Real-Time Agent Visualization Enhancement

> Plan: `plans/kind-prancing-beaver.md`
> Created: 2026-03-31

---

## Phase 1: AgentActivityTicker (最優先)

### Store拡張 (Red -> Green -> Refactor)
- [x] agentVisualizationStore.spec.ts: tickerEvents computed テスト追加
- [x] agentVisualizationStore.spec.ts: addDialogueEvent テスト追加
- [x] agentVisualizationStore.ts: TickerEvent interface + dialogueEvents + addDialogueEvent + tickerEvents 実装
- [x] テスト通過確認 (15/15)

### AgentActivityTicker コンポーネント (Red -> Green -> Refactor)
- [x] AgentActivityTicker.spec.ts: テスト作成
- [x] AgentActivityTicker.vue: コンポーネント実装
- [x] テスト通過確認 (7/7)

### SSE統合 + SimulationPage統合
- [x] useCognitiveSSE.ts: debate_result/conversation の通信フロー充実化
- [x] useSimulationSSE.ts: meeting_dialogue で addDialogueEvent 呼び出し
- [x] SimulationPage.vue: AgentActivityTicker 配置
- [x] 型チェック通過

## Phase 2: LiveDialogueStream

### コンポーネント (Red -> Green -> Refactor)
- [x] LiveDialogueStream.spec.ts: テスト作成
- [x] LiveDialogueStream.vue: コンポーネント実装
- [x] テスト通過確認 (4/4)

### ページ統合
- [x] layoutRules.ts: dialogue タブ追加
- [x] SimulationPage.vue: LiveDialogueStream 統合
- [x] 型チェック通過

## Phase 3: Communication Pulse Lines

### Composable (Red -> Green -> Refactor)
- [x] useCommunicationPulse.spec.ts: テスト作成
- [x] useCommunicationPulse.ts: composable 実装
- [x] テスト通過確認 (5/5)

### グラフ統合
- [x] SimulationPage.vue: useCommunicationPulse 統合 + communicationFlows watch
- [x] 型チェック通過

## Phase 4: DigitalWorkspaceBackground

### コンポーネント (Red -> Green -> Refactor)
- [x] DigitalWorkspaceBackground.spec.ts: テスト作成
- [x] DigitalWorkspaceBackground.vue: コンポーネント実装
- [x] テスト通過確認 (4/4)
- [x] SimulationPage.vue: graph-empty-backdrop 置換
- [x] 型チェック通過

## 最終検証
- [x] pnpm test 全通過 (81/81 passed, 18 test files)
- [x] pnpm build エラーなし (367ms)
