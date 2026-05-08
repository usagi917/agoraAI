# Agent Story Drawer 404 修正案

## 概要

Society モードでエージェントを選択した際、右側の Agent Story Drawer に `Request failed with status code 404` が表示される不具合がある。

原因は、フロントエンドがエージェントの一時IDとして `agent-<agent_index>` を生成して保持している一方、詳細 API は `AgentProfile.id` を前提にエージェントを検索していることにある。

本修正では、選抜完了直後の SSE payload から正規の agent id をフロントへ渡し、以後の UI 内部キーをすべて canonical id に統一する。これにより、評議会進行中でも Agent Story Drawer が正しい agent id で詳細 API を呼べるようにする。

## 現象

### 再現条件

1. Society モードのシミュレーションを開始する
2. `society_selection_completed` 後、評議会進行中の Live Social Graph で任意のエージェントをクリックする
3. Agent Story Drawer が開く
4. Drawer 内で `Request failed with status code 404` が表示される

### 発生経路

1. `LiveSocietyGraph` でノードがクリックされる
2. 選択されたノード id が親コンポーネントへ emit される
3. `AgentStoryDrawer` がその id を `useAgentStory()` に渡す
4. `useAgentStory()` が `/society/simulations/{sim_id}/agents/{agent_id}` を呼ぶ
5. `agent_id` が DB の正規 id ではなく `agent-53` のような仮IDのため、バックエンドが `AgentProfile` を取得できず 404 を返す

## 原因の分解

### 1. 選抜完了 SSE に正規 id が含まれていない

`backend/src/app/services/phases/society_pulse.py`

```python
await sse_manager.publish(simulation_id, "society_selection_completed", {
    "selected_agents": [
        {
            "agent_index": a.get("agent_index", i),
            "name": f"Agent-{a.get('agent_index', i)}",
            "occupation": a.get("demographics", {}).get("occupation", ""),
            "age": a.get("demographics", {}).get("age", 0),
            "region": a.get("demographics", {}).get("region", ""),
        }
        for i, a in enumerate(selected_agents)
    ],
})
```

`backend/src/app/services/society/society_orchestrator.py` にも同様の payload 組み立てがあり、こちらも `id` を送っていない。

### 2. フロントが仮ID `agent-<agent_index>` を生成している

`frontend/src/stores/societyGraphStore.ts`

```ts
function setSelectedAgents(agents: Array<...>) {
  const map = new Map<string, LiveAgentNode>()
  for (const a of agents) {
    const id = `agent-${a.agent_index}`
    map.set(id, {
      id,
      agentIndex: a.agent_index,
      ...
    })
  }
  liveAgents.value = map
}
```

この時点でフロント内部の agent key は DB 上の `AgentProfile.id` ではなく、UI 専用の仮IDになる。

### 3. ノードクリック時に仮IDがそのまま Drawer に渡る

`frontend/src/composables/useLiveSocietyGraph.ts`

```ts
forceGraph.onNodeClick((nodeId: string) => {
  selectedAgentId.value = nodeId
})
```

`frontend/src/components/LiveSocietyGraph.vue`

```ts
watch(selectedAgentId, (id) => {
  if (id && !id.startsWith('kg-')) {
    emit('select-agent', id)
  }
})
```

### 4. Drawer がその仮IDで詳細 API を叩く

`frontend/src/composables/useAgentStory.ts`

```ts
agentDetail.value = await getAgentDetail(simId, id)
```

`frontend/src/api/client.ts`

```ts
export async function getAgentDetail(simId: string, agentId: string) {
  const { data } = await api.get(`/society/simulations/${simId}/agents/${agentId}`)
  return data
}
```

### 5. バックエンドは正規 id 前提で検索している

`backend/src/app/api/routes/society.py`

```python
agent = await session.get(AgentProfile, agent_id)
if not agent:
    raise HTTPException(status_code=404, detail="エージェントが見つかりません")
```

ここで `agent-53` のような値は `AgentProfile.id` と一致しないため、404 になる。

## 影響範囲

### 直接影響

- Live Social Graph から Agent Story Drawer を開く導線
- 評議会中にエージェント詳細を表示する導線

### 間接影響

- `DebateCards`
- `ConversationsTab`
- `ConnectionTimeline`
- 他の `select-agent` イベント発火箇所

これらは一部 `agentIndex -> canonical id` 解決を持っているが、`LiveSocietyGraph` は現在の selection payload をそのまま信頼しているため、もっとも影響を受けやすい。

### 症状として観測される付随現象

- 評議会進行中は `102 agents / 0 edges` のように selection payload ベースで仮ノードが見えていても、Drawer 詳細だけ失敗する
- `society_social_graph_ready` 後に hydrate されるまでは canonical id に置き換わらない
- エラーメッセージが API `detail` ではなく axios の汎用文言のまま表示される

## 採用する修正方針

### 基本方針

全ライフサイクルで canonical agent id を唯一の agent key として扱う。

### 方針の要点

- 選抜完了 SSE `selected_agents[]` に `id` を追加する
- フロントは `agent-<agent_index>` を生成しない
- `societyGraphStore.liveAgents` の key を常に canonical id にする
- `agentIndex` は会話ログや theater event の補助解決用として保持する
- `hydrateWithSocialGraph()` は canonical id 前提のままとし、仮ID統合ロジックは追加しない

### この方針を採る理由

- 404 の根本原因は id の不一致であり、API 側で仮IDを解釈するのは対症療法になる
- canonical id を selection 直後から UI に流せば、selection 後と social graph hydration 後のノード識別子が一致し続ける
- ノード重複やマッピング分岐を store 側に持ち込まずに済む

## 実装変更

## 1. Backend: selection payload に canonical id を含める

### 対象箇所

- `backend/src/app/services/phases/society_pulse.py`
- `backend/src/app/services/society/society_orchestrator.py`

### 変更内容

`society_selection_completed.selected_agents[]` に `id` を追加する。

変更後イメージ:

```python
"selected_agents": [
    {
        "id": a["id"],
        "agent_index": a.get("agent_index", i),
        "name": f"Agent-{a.get('agent_index', i)}",
        "occupation": a.get("demographics", {}).get("occupation", ""),
        "age": a.get("demographics", {}).get("age", 0),
        "region": a.get("demographics", {}).get("region", ""),
    }
    for i, a in enumerate(selected_agents)
]
```

### 注意点

- 片方だけ修正しないこと。`society_pulse.py` と `society_orchestrator.py` の両方を同期させる
- `selected_agents` の schema 変更なので、イベント利用側の TypeScript 側型も合わせる

## 2. Frontend Store: 仮ID生成をやめる

### 対象箇所

- `frontend/src/stores/societyGraphStore.ts`

### 変更内容

#### `setSelectedAgents()` の引数型を変更する

現状:

```ts
function setSelectedAgents(agents: Array<{
  agent_index: number
  name: string
  display_name?: string
  occupation: string
  age: number
  region: string
}>)
```

変更後:

```ts
function setSelectedAgents(agents: Array<{
  id: string
  agent_index: number
  name: string
  display_name?: string
  occupation: string
  age: number
  region: string
}>)
```

#### Map key と `LiveAgentNode.id` に canonical id を使う

現状:

```ts
const id = `agent-${a.agent_index}`
```

変更後:

```ts
const id = a.id
```

### 注意点

- `agentIndex` は削除しない。`participant_index` 逆引きや theater 系イベント解決に必要
- `name` と `display_name` の扱いは現状維持でよい
- `status`, `confidence`, `stance` の初期値はそのままでよい

## 3. Frontend Graph / Drawer: canonical id 前提で受け渡す

### 対象箇所

- `frontend/src/composables/useLiveSocietyGraph.ts`
- `frontend/src/components/LiveSocietyGraph.vue`
- `frontend/src/pages/SimulationPage.vue`
- `frontend/src/components/AgentStoryDrawer.vue`

### 変更内容

ここは大きなロジック変更は不要。`societyGraphStore.liveAgents` の key が canonical id になれば、既存の `select-agent` emit と `selectedAgentForStory` の受け渡しだけで API に正しい id が渡る。

### 確認観点

- Live graph node click
- KG node overlay からの `select-agent`
- Spotlight 表示

いずれも `selectedAgentForStory` に入る id が UUID 系の canonical id になることを確認する。

## 4. Frontend: hydrate 後の整合性を保つ

### 対象箇所

- `frontend/src/stores/societyGraphStore.ts`
- `frontend/src/composables/useSimulationSSE.ts`

### 変更内容

`hydrateWithSocialGraph()` は既に `SocialGraphResponse.nodes[*].id` を canonical id として扱っているため、大きな変更は不要。

重要なのは、selection 時点の `liveAgents` の key も同じ canonical id にしておくこと。これにより `society_social_graph_ready` 後に:

- 既存 agent node をそのまま上書きできる
- 仮IDノードと本IDノードの二重化が起きない
- `selectedAgentForStory` や `spotlightAgentId` が途中で無効にならない

## 5. Frontend: エラー表示を API detail 優先にする

### 対象箇所

- `frontend/src/composables/useAgentStory.ts`

### 変更内容

現状:

```ts
catch (e: any) {
  error.value = e?.message ?? 'データの取得に失敗しました'
}
```

変更後方針:

```ts
catch (e: any) {
  error.value =
    e?.response?.data?.detail
    ?? e?.message
    ?? 'データの取得に失敗しました'
}
```

### 目的

- 今回の修正後も、将来別理由で 404 や 500 が起きた場合に API detail がそのまま UI に出るようにする
- `Request failed with status code 404` のような調査しづらい汎用文言を減らす

## テスト計画

## 1. Backend テスト

### 追加確認

- `society_selection_completed` payload の `selected_agents[*].id` が含まれること
- `id` が空文字や `None` でないこと
- `agent_index` と `id` が同時に payload に含まれること

### 対象候補

- SSE payload を検証している既存テストがあればそこへ追加
- なければ society orchestrator 系のテストへ追加

## 2. Frontend Store テスト

### `societyGraphStore.setSelectedAgents()`

確認項目:

- `liveAgents` の key が `a.id` になること
- `agent-<index>` が生成されないこと
- `agentIndex` は保持されること
- 既存の `status: 'selected'` 初期値が維持されること

## 3. Drawer / Composable テスト

### `useAgentStory()`

確認項目:

- `agentId` に canonical id が渡ったとき `getAgentDetail(simId, canonicalId)` が呼ばれること
- API 404 時に `response.data.detail` が表示用 error に入ること

### `AgentStoryDrawer`

確認項目:

- `selectedAgentForStory` が canonical id のまま渡ること
- open 中に agent 切り替えしても再 fetch が正常に動くこと

## 4. Hydration 回帰テスト

### `hydrateWithSocialGraph()`

確認項目:

- selection 後に social graph hydrate を実行しても node 数が重複しないこと
- selection 時のエージェントが hydrate 後も同一 id で更新されること
- `selectedAgentForStory` が hydrate 後も有効なままであること

## 5. 手動確認

### 確認手順

1. Society モードのシミュレーションを開始する
2. `society_selection_completed` 後、評議会中に Live Social Graph のノードをクリックする
3. Drawer が正常にプロフィールと発言履歴を表示することを確認する
4. `DebateCards` からエージェントを選択して Drawer が開くことを確認する
5. `ConversationsTab` からエージェントを選択して Drawer が開くことを確認する
6. `society_social_graph_ready` 後も同じエージェント選択が継続して機能することを確認する

## 受け入れ条件

- 評議会進行中の Live Social Graph からエージェント選択しても 404 が出ない
- Drawer の詳細 API に渡る `agent_id` が canonical id である
- selection 後と social graph hydrate 後で agent key が変化しない
- `DebateCards` と `ConversationsTab` からの選択でも同じ詳細表示が成功する
- API エラー時は `response.data.detail` が優先表示される

## 非採用案

## 1. バックエンドで仮ID `agent-<index>` を解釈する

### 却下理由

- API が UI 専用表現に依存する
- `agent_index` が一意性や永続識別子として扱われる設計に寄ってしまう
- canonical id を統一キーにする方針と逆行する

## 2. フロント側だけで `agent-<index>` を都度 UUID に変換する

### 却下理由

- 変換に必要な対応表を複数箇所で維持する必要がある
- selection 時点と hydrate 後で分岐が増える
- store の key が二重体系になり、重複ノードや参照切れの温床になる

## 3. `hydrateWithSocialGraph()` で仮IDと本IDをマージする

### 却下理由

- 問題発生後に整合させる後追い処理であり、根本解決ではない
- selection 直後から drawer を開くユースケースを救えない
- store の責務が過剰に複雑になる
