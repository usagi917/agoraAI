# エージェント可視化改善 タスクリスト

## Phase 1: バックエンド SSE — 欠落イベントの発行

### 1-1: agent_state_updated
- [x] RED: `test_cognitive_agent_sse.py` テスト作成
- [x] GREEN: `cognitive_agent.py` `_save_state()` にSSE発行追加
- [x] REFACTOR: ペイロードサイズ最適化（beliefs[:20], mental_models[:5]）

### 1-2: agent_thinking_started / agent_thinking_completed
- [x] RED: `test_deliberation_sse.py` テスト作成
- [x] GREEN: `deliberation.py` LLM前後にSSE発行追加
- [x] REFACTOR: 失敗時の status="failed" 対応

### 1-3: conversation_* イベント
- [x] RED: `test_conversation_sse.py` テスト作成
- [x] GREEN: `conversation.py` にSSE発行追加 + async化 + run_idパラメータ追加
- [x] REFACTOR: process_conversation_round もasync対応

### 1-4: debate_result イベント
- [x] RED: `test_debate_sse.py` テスト作成
- [x] GREEN: `debate_protocol.py` にSSE発行追加
- [x] REFACTOR: arguments概要のシリアライズ

## Phase 2: フロントエンド Store — agentVisualizationStore

### 2-1: 新Store作成
- [x] RED: `agentVisualizationStore.spec.ts` テスト作成（9テスト）
- [x] GREEN: `agentVisualizationStore.ts` 実装
- [x] REFACTOR: 型定義の整理

### 2-2: SSEイベントハンドラー拡張
- [x] GREEN: `useCognitiveSSE.ts` に新イベントハンドラー追加（thinking, conversation, debate）
- [x] GREEN: `useSimulationSSE.ts` に新イベントタイプ追加 + ActivityFeedエントリ追加

## Phase 3: ThinkingPanel — 思考プロセスビューアー

### 3-1: layoutRules拡張
- [x] `layoutRules.ts` に `thinking` タブ追加 + `hasCognitiveData` フラグ

### 3-2: ThinkingPanel コンポーネント
- [x] GREEN: `ThinkingPanel.vue` 実装（ReasoningStream + BDIStateCard + MemoryTimeline）

### 3-3: SimulationPage統合
- [x] `SimulationPage.vue` に ThinkingPanel タブ追加 + cognitiveStore/vizStore統合

## Phase 4: 3Dグラフ強化

### 4-1: ステータスリング
- [x] GREEN: `useAgentStatusRing.ts` コンポーザブル作成
- [x] GREEN: SimulationPage.vue に統合（nodeExtension + animationLoop）

### 4-2: コミュニケーションアーク
- [ ] `useCommunicationArcs.ts` 実装（次回の改善で対応）

## Phase 5: プログレス表示の強化

### 5-1: SimulationProgress強化
- [x] セグメント型パイプライン実装（expand active, check completed, pending dimmed）

### 5-2: ColonyGrid強化
- [x] アクセントライン + スパークライン + イベント数 + チェックバッジ追加

### 5-3: 空状態の改善
- [x] リングアニメーション追加（ring-expand keyframes）
