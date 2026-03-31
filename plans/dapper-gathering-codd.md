# エージェント可視化改善 実装計画

## Context

エージェントAIシミュレーションのフロントエンド可視化が不十分。エージェントの見栄え、思考プロセス、エージェント間の通信が見えない。調査の結果、**バックエンドは既にリッチな認知データ（BDI状態、推論チェーン、メモリ、信頼マップ等）を生成しているが、SSEイベントとして発行していない/フロントエンドが表示していない**ことが判明。

### 核心的なギャップ
1. `cognitive_agent.py:_save_state()` (L312-333) — DB保存のみ、SSE未発行。`useCognitiveSSE.ts:29` は `agent_state_updated` を期待しているのに受信データなし
2. `sse/manager.py` の `publish_conversation_event()` (L104), `publish_debate_result()` (L108) — 定義済みだが呼び出し箇所なし
3. `cognitiveStore.ts` に `agentStates`, `memoryEntries`, `reflections`, `tomRelations` が格納されるが、ライブUIでの表示コンポーネントがゼロ
4. `useForceGraph.ts` にはSocietyモードのようなステータスリング機構がない

---

## Phase 1: バックエンド SSE — 欠落イベントの発行

### 1-1: `agent_state_updated` イベント追加

**テスト (RED)**: `backend/tests/test_cognitive_agent_sse.py`
- `_save_state()` 完了後に `sse_manager.publish("agent_state_updated", ...)` が呼ばれることを検証
- ペイロードに `agent_id`, `agent_name`, `round`, `beliefs`, `desires`, `intentions`, `reasoning_chain`, `trust_map` が含まれることを検証

**実装 (GREEN)**: `backend/src/app/services/cognition/cognitive_agent.py`
- `_save_state()` の `session.add(state)` (L333) 直後にSSEイベント発行を追加
- `from src.app.sse.manager import sse_manager` をインポート

### 1-2: `agent_thinking_started` / `agent_thinking_completed` イベント追加

**テスト (RED)**: `backend/tests/test_deliberation_sse.py`
- LLM呼び出し前に `agent_thinking_started`、完了後に `agent_thinking_completed` が発行されることを検証

**実装 (GREEN)**: `backend/src/app/services/cognition/deliberation.py`
- `deliberate()` の `llm_client.call_with_retry()` (L61) の前後にSSEイベント発行
- `run_id` は既にパラメータに存在 (L24)

### 1-3: `conversation_*` イベント追加

**テスト (RED)**: `backend/tests/test_conversation_sse.py`

**実装 (GREEN)**: `backend/src/app/services/communication/conversation.py`
- `initiate_conversation()` (L38), `advance_turn()` (L66), `conclude_channel()` (L78) から `sse_manager.publish_conversation_event()` を呼び出し
- run_idの伝播方法: ConversationManagerの初期化時またはGameMasterから呼び出し時に渡す

### 1-4: `debate_result` イベント追加

**テスト (RED)**: `backend/tests/test_debate_sse.py`

**実装 (GREEN)**: `backend/src/app/services/communication/debate_protocol.py`
- `run_debate()` の `return debate_result` 前に `sse_manager.publish_debate_result()` を呼び出し
- ペイロード: `channel_id`, `topic`, `winner_agent_id`, `judge_reasoning`, `arguments`概要

### 検証
```bash
cd backend && uv run pytest tests/test_cognitive_agent_sse.py tests/test_deliberation_sse.py tests/test_conversation_sse.py tests/test_debate_sse.py -v
```

---

## Phase 2: フロントエンド Store — agentVisualizationStore

### 2-1: 新Store作成

**テスト (RED)**: `frontend/src/stores/__tests__/agentVisualizationStore.spec.ts`

**実装 (GREEN)**: `frontend/src/stores/agentVisualizationStore.ts`

```typescript
// 主要な型
type AgentVisualStatus = 'idle' | 'thinking' | 'executing' | 'speaking' | 'debating'

interface RecentThought {
  agentId: string; agentName: string; reasoningChain: string; chosenAction: string; timestamp: number
}

interface CommunicationFlow {
  sourceId: string; targetId: string; messageType: string; content: string; timestamp: number
}

// 状態
agentStatusMap: Record<string, AgentVisualStatus>
thinkingAgentId: string | null
recentThoughts: RecentThought[]  // 最大20件
communicationFlows: CommunicationFlow[]  // 最大50件
```

### 2-2: SSEイベントハンドラー拡張

**テスト (RED)**: `frontend/src/composables/__tests__/useCognitiveSSE.spec.ts`

**実装 (GREEN)**: `frontend/src/composables/useCognitiveSSE.ts`
- switch文に追加: `agent_thinking_started`, `agent_thinking_completed`, `conversation_started`, `conversation_turn_advanced`, `conversation_concluded`, `debate_result`
- 各イベントで `agentVisualizationStore` を更新

**実装 (GREEN)**: `frontend/src/composables/useSimulationSSE.ts`
- `eventTypes` 配列に上記イベントタイプを追加

### 検証
```bash
cd frontend && npx vitest run src/stores/__tests__/agentVisualizationStore.spec.ts src/composables/__tests__/useCognitiveSSE.spec.ts
```

---

## Phase 3: ThinkingPanel — エージェント思考プロセスビューアー

### 3-1: layoutRules拡張

**対象**: `frontend/src/pages/layoutRules.ts`

- `LiveSecondaryTab` 型に `'thinking'` を追加
- `LiveLayoutContext` に `hasCognitiveData: boolean` を追加
- `getLiveSecondaryTabs()` (L103-118): `hasCognitiveData` が true なら `'thinking'` タブを追加

### 3-2: ThinkingPanel コンポーネント

**テスト (RED)**: `frontend/src/components/__tests__/ThinkingPanel.spec.ts`
- 空状態、推論ストリーム表示、BDIカード表示、メモリタイムライン表示を検証

**実装 (GREEN)**: `frontend/src/components/ThinkingPanel.vue`

3つのセクション:

1. **ReasoningStream** — 最新の `reasoningChain` をタイプライター効果で表示
   - `var(--font-mono)` 等幅、`var(--bg-elevated)` 背景、左ボーダー `var(--accent)`

2. **BDIStateCard** — 選択エージェントの信念/欲求/意図ミニカード
   - 信念: confidence のプログレスバー
   - 欲求: priority ソート + 色で重要度表現
   - 意図: commitment_strength のバー
   - データソース: `cognitiveStore.selectedAgent`

3. **MemoryTimeline** — メモリ+リフレクションの時系列
   - エピソード: `var(--accent)` ドット
   - リフレクション: `var(--warning)` ドット + インデント
   - データソース: `cognitiveStore.selectedAgentMemories`, `cognitiveStore.selectedAgentReflections`

### 3-3: SimulationPage統合

**対象**: `frontend/src/pages/SimulationPage.vue`

- ThinkingPanel のインポートと `cognitiveStore` の利用
- サイドパネルのタブ切り替え部分（L843-920付近）に thinking タブのコンテンツ追加
- `liveSecondaryTabs` の computed で `hasCognitiveData` を算出

### 検証
```bash
cd frontend && npx vitest run src/components/__tests__/ThinkingPanel.spec.ts
```

---

## Phase 4: 3Dグラフ強化 — エージェントステータス可視化

### 4-1: ステータスリング追加

**テスト (RED)**: `frontend/src/composables/__tests__/useForceGraph.spec.ts`

**実装 (GREEN)**: `frontend/src/composables/useForceGraph.ts`
- `createNodeThreeObject()` で `type === 'agent'` ノードにステータスリング追加
- `useLiveSocietyGraph.ts` (L17-29) の `createStatusRing()` パターンを再利用
- ステータスカラーマップ:
  - `idle`: 透明, `thinking`: `#3b82f6`（青パルス）, `executing`: `#22c55e`（緑）, `debating`: `#f59e0b`（琥珀）, `speaking`: `#ffd740`（黄）
- アニメーションループ内で `agentVisualizationStore.agentStatusMap` 参照、`thinking` 時は `opacity` パルス

### 4-2: コミュニケーションアーク

**テスト (RED)**: `frontend/src/composables/__tests__/useCommunicationArcs.spec.ts`

**実装 (GREEN)**: `frontend/src/composables/useCommunicationArcs.ts`（新規）
- `agentVisualizationStore.communicationFlows` を watch
- 新フロー追加時: ソース→ターゲットの `QuadraticBezierCurve3` + 移動パーティクル
- メッセージタイプ別の色: `say`=青, `argue`=琥珀, `propose/accept`=緑, `reject`=赤
- 3秒後フェードアウト + `dispose()` でメモリリーク防止

### 4-3: useForceGraphへの統合

- `useCommunicationArcs` を `useForceGraph` 内で初期化
- `onUnmounted` で明示的クリーンアップ

### 検証
```bash
cd frontend && npx vitest run src/composables/__tests__/useForceGraph.spec.ts src/composables/__tests__/useCommunicationArcs.spec.ts
```

---

## Phase 5: プログレス表示の強化

### 5-1: SimulationProgress強化

**対象**: `frontend/src/components/SimulationProgress.vue` (226行)

- 各フェーズをセグメント表示、アクティブセグメントが `flex-grow: 2` で拡張
- 完了セグメント: `var(--success)` + チェックアイコン
- アクティブセグメント: `var(--accent)` パルス + 内部にラウンド情報
- 未到達: `var(--bg-elevated)` + `opacity: 0.5`

### 5-2: ColonyGrid強化

**対象**: `frontend/src/components/ColonyGrid.vue` (191行)

- 上部にグラデーションアクセントライン
- SVGベースのミニスパークライン（ラウンド進捗）
- 最新イベントスニペット表示
- 実行中カードに微かなパルスアニメーション

### 5-3: 空状態の改善

**対象**: `frontend/src/pages/SimulationPage.vue` (L795-808 `.graph-empty`)

- 静的テキスト → リングアニメーション + フェーズ名表示
- `@keyframes shimmer` 背景グラデーション
- フェーズ別の初期化アニメーション

### 検証
```bash
cd frontend && npx vitest run src/components/__tests__/SimulationProgress.spec.ts src/components/__tests__/ColonyGrid.spec.ts
```

ブラウザでの目視確認: シミュレーション実行中に各フェーズの遷移、エージェントのステータスリング変化、ThinkingPanel の表示を確認

---

## 依存関係と順序

```
Phase 1 (Backend SSE) ──→ Phase 2 (Store) ──→ Phase 3 (ThinkingPanel)
                                           ──→ Phase 4 (3D Graph)
Phase 5 (Progress) --- Phase 1/2 と独立、並行可能
```

## リスクと対策

| リスク | 影響 | 対策 |
|--------|------|------|
| SSEイベント量増大（70+エージェント×毎ラウンド） | キューあふれ | `beliefs[:20]`、`mental_models[:5]` 等でペイロードサイズを制限 |
| Three.jsメモリリーク（アーク生成/破棄） | ブラウザクラッシュ | `dispose()` 明示呼び出し + `onUnmounted` クリーンアップ |
| AgentDetailPanel のTailwind不整合 | スタイル混在 | 新コンポーネントは全てCSS変数パターンに統一 |
| deliberation.py への変更が既存テスト破壊 | CI失敗 | `sse_manager` をモック注入、既存シグネチャ変更なし |

## 変更対象ファイル一覧

### 既存ファイル（修正）
| ファイル | Phase | 変更内容 |
|---------|-------|---------|
| `backend/src/app/services/cognition/cognitive_agent.py` | 1 | `_save_state()` にSSE発行追加 |
| `backend/src/app/services/cognition/deliberation.py` | 1 | LLM前後にSSE thinking イベント |
| `backend/src/app/services/communication/conversation.py` | 1 | ライフサイクルにSSE発行追加 |
| `backend/src/app/services/communication/debate_protocol.py` | 1 | `debate_result` SSE発行追加 |
| `frontend/src/composables/useCognitiveSSE.ts` | 2 | 新イベントハンドラー追加 |
| `frontend/src/composables/useSimulationSSE.ts` | 2 | eventTypes配列に新イベント追加 |
| `frontend/src/composables/useForceGraph.ts` | 4 | ステータスリング + アーク統合 |
| `frontend/src/pages/layoutRules.ts` | 3 | `thinking` タブ追加 |
| `frontend/src/pages/SimulationPage.vue` | 3,5 | ThinkingPanel統合 + 空状態改善 |
| `frontend/src/components/SimulationProgress.vue` | 5 | セグメント型パイプライン |
| `frontend/src/components/ColonyGrid.vue` | 5 | スパークライン + イベント表示 |

### 新規ファイル
| ファイル | Phase | 目的 |
|---------|-------|------|
| `frontend/src/stores/agentVisualizationStore.ts` | 2 | 可視化ブリッジストア |
| `frontend/src/components/ThinkingPanel.vue` | 3 | 思考プロセスビューアー |
| `frontend/src/composables/useCommunicationArcs.ts` | 4 | 通信アークアニメーション |
| `backend/tests/test_cognitive_agent_sse.py` | 1 | SSEテスト |
| `backend/tests/test_deliberation_sse.py` | 1 | SSEテスト |
| `backend/tests/test_conversation_sse.py` | 1 | SSEテスト |
| `backend/tests/test_debate_sse.py` | 1 | SSEテスト |
| `frontend/src/stores/__tests__/agentVisualizationStore.spec.ts` | 2 | ストアテスト |
| `frontend/src/composables/__tests__/useCognitiveSSE.spec.ts` | 2 | ハンドラーテスト |
| `frontend/src/components/__tests__/ThinkingPanel.spec.ts` | 3 | コンポーネントテスト |
| `frontend/src/composables/__tests__/useCommunicationArcs.spec.ts` | 4 | アークテスト |
