# Real-Time Agent Visualization Enhancement

## Context

シミュレーション実行中のフロントエンドが「待ち時間が暇」「エージェントが働いている感じがしない」という課題。バックエンドからは67+のSSEイベントが送られているが、フロントエンドでの可視化が不足しており、ユーザーがタブを切り替えないと情報が見えない。エージェントがデジタル空間で活動・対話している感覚をリアルタイムに提供する。

## 変更概要

4つの機能を優先順位順に実装する:

1. **AgentActivityTicker** - グラフ上に常時表示されるリアルタイム活動ティッカー
2. **LiveDialogueStream** - サイドパネルにチャット形式の対話ビュー追加
3. **Communication Pulse Lines** - 3Dグラフ上にエージェント間通信の光線エフェクト
4. **DigitalWorkspaceBackground** - 待機画面のデジタルワークスペース背景強化

---

## Feature 1: AgentActivityTicker (最優先)

グラフコンテナの下部にオーバーレイとして常時表示。タブ切り替え不要でエージェントの思考・通信・議論がリアルタイムに流れる。

### 新規ファイル
- `frontend/src/components/AgentActivityTicker.vue`
- `frontend/src/components/__tests__/AgentActivityTicker.spec.ts`

### 変更ファイル
- `frontend/src/stores/agentVisualizationStore.ts` - `TickerEvent` interface + `tickerEvents` computed + `addDialogueEvent()` 追加
- `frontend/src/stores/__tests__/agentVisualizationStore.spec.ts` - tickerEvents テスト追加
- `frontend/src/composables/useCognitiveSSE.ts` - debate_result/conversation 時に通信フローデータを充実化
- `frontend/src/composables/useSimulationSSE.ts` - meeting_dialogue イベントで `vizStore.addDialogueEvent()` 呼び出し追加
- `frontend/src/pages/SimulationPage.vue` - `<AgentActivityTicker />` を `.graph-container` 内に配置

### データフロー
```
SSE events → useCognitiveSSE/useSimulationSSE
  → agentVisualizationStore (recentThoughts + communicationFlows + dialogueEvents)
  → tickerEvents (computed: 統合・ソート済み)
  → AgentActivityTicker (表示)
```

### デザイン
- 半透明背景 `rgba(8,10,22,0.85)` + `backdrop-filter: blur(10px)`
- モノスペースフォント、最大8件表示
- `<TransitionGroup>` でスライドイン・フェードアウト
- 上端にスキャンラインシマーエフェクト
- 最小化トグル付き（1行表示モード）

---

## Feature 2: LiveDialogueStream

サイドパネルに「Dialogue」タブ追加。meeting_dialogue や conversation イベントをチャットバブル形式で表示。

### 新規ファイル
- `frontend/src/components/LiveDialogueStream.vue`
- `frontend/src/components/__tests__/LiveDialogueStream.spec.ts`

### 変更ファイル
- `frontend/src/pages/layoutRules.ts` - `LiveSecondaryTab` に `'dialogue'` 追加、`getLiveSecondaryTabs` に条件追加
- `frontend/src/pages/SimulationPage.vue` - LiveDialogueStream インポート・配置、タブラベル追加

### データフロー
```
societyGraphStore.currentArguments (meeting dialogues)
  + agentVisualizationStore.communicationFlows (conversations)
  → LiveDialogueStream
```

### デザイン
- チャットバブル（偶数=左寄せ、奇数=右寄せ）
- 話者名はスタンス色で着色（賛成=緑、反対=赤、中立=灰）
- 信頼度バー、ラウンドバッジ
- スタンスシフトはシステムメッセージ（中央配置）
- 自動スクロール

---

## Feature 3: Communication Pulse Lines

3Dナレッジグラフ上に、エージェント間通信時の一時的な光線エフェクト。既存の `useConversationLines.ts` をベースに実装。

### 新規ファイル
- `frontend/src/composables/useCommunicationPulse.ts`
- `frontend/src/composables/__tests__/useCommunicationPulse.spec.ts`

### 変更ファイル
- `frontend/src/composables/useForceGraph.ts` - `useCommunicationPulse` をインスタンス化、animation loop に `update()` 追加、`addPulseLine` を expose
- `frontend/src/pages/SimulationPage.vue` - `communicationFlows` を watch して `addPulseLine` 呼び出し

### 参照実装
- `frontend/src/composables/useConversationLines.ts` - プール管理、チューブジオメトリ、パーティクルアニメーション

### 仕様
- 通信種別ごとの色: thinking=#3b82f6, communication=#22c55e, debate=#f59e0b
- 4秒で自動消滅（フェードアウト）
- プールサイズ: 20

---

## Feature 4: DigitalWorkspaceBackground

グラフ空状態の背景を「デジタルワークスペース」感のある演出に強化。CSS-only。

### 新規ファイル
- `frontend/src/components/DigitalWorkspaceBackground.vue`
- `frontend/src/components/__tests__/DigitalWorkspaceBackground.spec.ts`

### 変更ファイル
- `frontend/src/pages/SimulationPage.vue` - `.graph-empty-backdrop` を `<DigitalWorkspaceBackground>` に置換

### 3レイヤー構成
1. **データレイン**: CSS-onlyの縦書きマトリックス風文字列 (opacity 0.1-0.2)
2. **スキャンライン**: 水平線が縦にスイープ (6秒ループ)
3. **パルスグリッド**: repeating-linear-gradient のグリッドパターン (opacity アニメーション)

---

## 実装順序 (TDD)

各機能につき Red → Green → Refactor サイクル:

### Phase 1: AgentActivityTicker
1. Store拡張テスト (Red) → Store実装 (Green) → Refactor
2. コンポーネントテスト (Red) → コンポーネント実装 (Green) → Refactor
3. SSEハンドラ修正 + SimulationPage統合

### Phase 2: LiveDialogueStream
4. コンポーネントテスト (Red) → 実装 (Green) → Refactor
5. layoutRules修正 + SimulationPage統合

### Phase 3: Communication Pulse Lines
6. Composableテスト (Red) → 実装 (Green) → Refactor
7. useForceGraph統合 + SimulationPage連携

### Phase 4: DigitalWorkspaceBackground
8. コンポーネントテスト (Red) → 実装 (Green) → Refactor
9. SimulationPage統合

---

## 検証方法

1. `pnpm test` でユニットテスト全通過
2. `pnpm build` でビルドエラーなし
3. ブラウザで `/sim/{id}` を開き:
   - グラフ下部にティッカーが表示され、SSEイベントと連動して更新される
   - サイドパネル「Dialogue」タブでチャットバブルが表示される
   - 3Dグラフでエージェント間に光線が一時的に表示される
   - 空状態でデジタル背景エフェクトが動作する

## 重要ファイル一覧
- `frontend/src/stores/agentVisualizationStore.ts`
- `frontend/src/pages/SimulationPage.vue`
- `frontend/src/pages/layoutRules.ts`
- `frontend/src/composables/useForceGraph.ts`
- `frontend/src/composables/useCognitiveSSE.ts`
- `frontend/src/composables/useSimulationSSE.ts`
- `frontend/src/composables/useConversationLines.ts` (参照)
- `frontend/src/components/ThinkingPanel.vue` (参照)
- `frontend/src/components/ConversationPanel.vue` (参照)
