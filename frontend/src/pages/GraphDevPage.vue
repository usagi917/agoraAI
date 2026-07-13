<script setup lang="ts">
import { onMounted, onUnmounted } from 'vue'
import { useRoute } from 'vue-router'
import LiveSocietyGraph from '../components/LiveSocietyGraph.vue'
import SocialGraphWorkspace from '../components/SocialGraphWorkspace.vue'
import { useSocietyGraphStore, type PropagationChange } from '../stores/societyGraphStore'
import { useSimulationStore } from '../stores/simulationStore'
import { useSocialGraphActivityStore } from '../stores/socialGraphActivityStore'
import { useSocialGraphTopologyStore } from '../stores/socialGraphTopologyStore'
import type {
  GraphActivityEvent,
  GraphActivityKind,
  SocialGraphNode,
  SocialGraphEdge,
} from '../api/client'

const societyGraphStore = useSocietyGraphStore()
const simulationStore = useSimulationStore()
const graphActivityStore = useSocialGraphActivityStore()
const topologyStore = useSocialGraphTopologyStore()
const route = useRoute()

const STANCES = ['賛成', '条件付き賛成', '中立', '条件付き反対', '反対']
const RELATIONS = ['friend', 'family', 'colleague', 'neighbor', 'acquaintance']
let cancelled = false
let graphEventId = 2

function emitGraphActivity(
  kind: GraphActivityKind,
  phase: string,
  options: Partial<GraphActivityEvent> = {},
) {
  const event: GraphActivityEvent = {
    id: graphEventId++,
    simulation_id: 'dev-sim',
    occurred_at: `2026-07-13T00:00:${String(graphEventId).padStart(2, '0')}Z`,
    phase,
    round: options.round ?? 0,
    kind,
    source_id: options.source_id,
    target_id: options.target_id,
    edge_id: options.edge_id,
    payload: options.payload ?? {},
  }
  graphActivityStore.receive(event, topologyStore.applyEvent)
}

function sleep(ms: number) {
  return new Promise((r) => setTimeout(r, ms))
}

/** ?pop=N で全人口レイヤー + 疑似伝播を再現する（例: /__dev__/graph?pop=10000） */
async function runPopulationHarness(populationSize: number) {
  if (cancelled) return
  const nodes = Array.from({ length: populationSize }, (_, i) => ({
    id: `agent-${i}`,
    agent_index: i,
  }))

  // WS 風: リング近傍 k=4 + 決定論的なリワイヤリング
  const edges: Array<[number, number, number]> = []
  for (let i = 0; i < populationSize; i++) {
    edges.push([i, (i + 1) % populationSize, 0.3 + ((i * 7) % 50) / 100])
    if ((i * 13) % 10 < 3) {
      edges.push([i, (i * 137 + 11) % populationSize, 0.3 + ((i * 11) % 50) / 100])
    } else {
      edges.push([i, (i + 2) % populationSize, 0.3 + ((i * 3) % 50) / 100])
    }
  }

  if (cancelled) return
  societyGraphStore.setPopulationNetwork({
    population_id: 'pop-dev',
    node_count: nodes.length,
    edge_count: edges.length,
    nodes,
    edges,
  })
  topologyStore.setPopulationNetwork({
    population_id: 'pop-dev',
    node_count: nodes.length,
    edge_count: edges.length,
    nodes,
    edges,
  })

  // 隣接リストを作って 101 アンカーから BFS で「波」を作る
  const adjacency = new Map<number, number[]>()
  for (const [s, t] of edges) {
    if (!adjacency.has(s)) adjacency.set(s, [])
    if (!adjacency.has(t)) adjacency.set(t, [])
    adjacency.get(s)!.push(t)
    adjacency.get(t)!.push(s)
  }

  const stanceOf = new Map<number, string>()
  const anchorCount = Math.min(101, populationSize)
  const anchors = new Set<number>()
  for (let i = 0; i < anchorCount; i++) {
    const anchor = Math.floor(i * populationSize / anchorCount)
    anchors.add(anchor)
    stanceOf.set(anchor, STANCES[i % STANCES.length])
  }
  let frontier = [...anchors]

  for (let round = 0; round < 8 && frontier.length; round++) {
    if (cancelled) return
    const next: number[] = []
    const changes: PropagationChange[] = []
    for (const idx of frontier) {
      const stance = stanceOf.get(idx)!
      for (const nb of adjacency.get(idx) ?? []) {
        if (stanceOf.has(nb)) continue
        stanceOf.set(nb, stance)
        changes.push({ i: nb, s: stance })
        next.push(nb)
      }
    }
    if (changes.length) {
      societyGraphStore.applyPropagationRound(changes)
    }
    frontier = next
    await sleep(700)
    if (cancelled) return
  }
}

onMounted(async () => {
  simulationStore.mode = 'unified'
  simulationStore.status = 'running'
  simulationStore.unifiedPhase = 'society_pulse'

  // 1. 選抜 (SSE: society_selection_completed)
  societyGraphStore.setSelectedAgents(
    Array.from({ length: 101 }, (_, i) => ({
      id: `agent-${i}`,
      agent_index: i,
      name: `Agent-${i}`,
      occupation: ['会社員', '自営業', '学生', '主婦', '医師'][i % 5],
      age: 20 + (i % 60),
      region: ['北海道', '東北', '関東', '関西', '九州'][i % 5],
    })),
  )

  // 2. ソーシャル構造の早期投入 (SSE: society_social_graph_structure)
  //    意見(stance)確定より前に、本物の関係性エッジだけを入れて開始直後から輪を描く。
  const edges: SocialGraphEdge[] = Array.from({ length: 140 }, (_, i) => ({
    id: `edge-${i}`,
    source: `agent-${i % 101}`,
    target: `agent-${(i * 9 + 5) % 101}`,
    relation_type: RELATIONS[i % RELATIONS.length],
    strength: 0.4 + (i % 6) / 10,
  })) as unknown as SocialGraphEdge[]

  // 異常系: 存在しないノードを参照するエッジ（選抜外エージェント / 未到着 KG エンティティ相当）
  edges.push({
    id: 'edge-missing',
    source: 'agent-0',
    target: 'agent-9999',
    relation_type: 'friend',
    strength: 0.9,
  } as unknown as SocialGraphEdge)

  societyGraphStore.setSocialEdges(edges)

  const earlyNodes = Array.from({ length: 101 }, (_, i) => ({
    id: `agent-${i}`,
    agent_index: i,
    stance: '',
    confidence: 0.5,
    demographics: {
      occupation: ['会社員', '自営業', '学生', '主婦', '医師'][i % 5],
      age: 20 + (i % 60),
      region: ['北海道', '東北', '関東', '関西', '九州'][i % 5],
    },
  })) as unknown as SocialGraphNode[]
  topologyStore.hydrate({
    simulation_id: 'dev-sim',
    population_id: 'pop-dev',
    nodes: earlyNodes,
    edges,
    population_network: {
      population_id: 'pop-dev',
      node_count: 0,
      edge_count: 0,
      nodes: [],
      edges: [],
    },
    current_phase: 'selection',
    current_round: 0,
    latest_event_id: 1,
  })
  graphActivityStore.beginBuffering('dev-sim')
  graphActivityStore.hydrateHistory([{
    id: 1,
    simulation_id: 'dev-sim',
    occurred_at: '2026-07-13T00:00:01Z',
    phase: 'population',
    round: 0,
    kind: 'phase_changed',
    payload: { phase: 'population', agent_count: 10000 },
  }], 1)
  graphActivityStore.completeBuffering([], topologyStore.applyEvent)
  emitGraphActivity('phase_changed', 'selection', { payload: { phase: 'selection' } })
  for (let i = 0; i < 101; i++) {
    emitGraphActivity('node_status', 'selection', {
      source_id: `agent-${i}`,
      payload: { status: 'selected', agent_index: i },
    })
  }

  // ?stage=early で「意見未確定・暖色グロー＋実エッジの輪」の初期状態を固定表示する
  if (route.query.stage === 'early') return
  await sleep(600)
  if (cancelled) return
  emitGraphActivity('phase_changed', 'activation', { payload: { phase: 'activation' } })

  // 3. 活性化進捗 (SSE: society_activation_progress)
  for (let done = 10; done <= 101; done += 30) {
    if (cancelled) return
    societyGraphStore.updateActivationProgress(Math.min(done, 101), 101)
    await sleep(120)
    if (cancelled) return
  }

  // 4. ソーシャルグラフ hydrate (SSE: social graph / stance 確定)
  const nodes: SocialGraphNode[] = Array.from({ length: 101 }, (_, i) => ({
    id: `agent-${i}`,
    agent_index: i,
    stance: STANCES[i % STANCES.length],
    confidence: 0.4 + (i % 6) / 10,
    demographics: { occupation: '会社員', age: 30 + (i % 40), region: '関東' },
  })) as unknown as SocialGraphNode[]

  societyGraphStore.hydrateWithSocialGraph(nodes, edges)
  for (const node of nodes) {
    emitGraphActivity('node_status', 'activation', {
      source_id: node.id,
      payload: {
        status: 'activated',
        stance: node.stance,
        confidence: node.confidence,
      },
    })
  }
  await sleep(400)
  if (cancelled) return

  // 5. 評議会フェーズ (SSE: council round)
  simulationStore.unifiedPhase = 'council'
  societyGraphStore.appendMeetingDialogue(3, {
    participant_name: '松田 章太',
    participant_index: 0,
    role: 'representative',
    argument: '結局のところ数字が示していることは…',
  })
  emitGraphActivity('phase_changed', 'meeting', {
    round: 3,
    payload: { phase: 'meeting', round_name: '最終立場表明' },
  })
  emitGraphActivity('dialogue', 'meeting', {
    round: 3,
    source_id: 'agent-0',
    target_id: 'agent-5',
    edge_id: 'edge-0',
    payload: {
      participant_name: '松田 章太',
      participant_index: 0,
      argument: '結局のところ数字が示していることは…',
      addressed_to: 'Agent-5',
    },
  })
  await sleep(350)
  if (cancelled) return
  emitGraphActivity('influence', 'population_propagation', {
    round: 4,
    source_id: 'agent-0',
    target_id: 'agent-5',
    edge_id: 'edge-0',
    payload: {
      primary_influencer_id: 'agent-0',
      before_stance: '中立',
      after_stance: '条件付き賛成',
      opinion_delta: 0.18,
      edge_strength: 0.8,
    },
  })
  emitGraphActivity('stance_shift', 'population_propagation', {
    round: 4,
    source_id: 'agent-5',
    payload: {
      before_stance: '中立',
      after_stance: '条件付き賛成',
      opinion_delta: 0.18,
      reason: 'network propagation',
    },
  })
  emitGraphActivity('relationship_changed', 'relationship_evolution', {
    round: 4,
    source_id: 'agent-0',
    target_id: 'agent-5',
    edge_id: 'edge-0',
    payload: {
      relation_type: 'friend',
      before_strength: 0.4,
      after_strength: 0.8,
      delta: 0.4,
      is_new: false,
    },
  })

  // 6. 全人口レイヤー（?pop=N 指定時のみ）
  const popSize = Number(route.query.pop)
  if (Number.isFinite(popSize) && popSize > 0) {
    await sleep(400)
    if (cancelled) return
    await runPopulationHarness(Math.min(popSize, 10000))
  }
  emitGraphActivity('phase_changed', 'completed', {
    round: 4,
    payload: { phase: 'completed' },
  })
})

onUnmounted(() => {
  cancelled = true
})
</script>

<template>
  <div style="position: fixed; inset: 60px 0 0">
    <SocialGraphWorkspace simulation-id="dev-sim" mode="live" :auto-bootstrap="false">
      <template #legacy-fallback>
        <LiveSocietyGraph simulation-id="dev-sim" />
      </template>
    </SocialGraphWorkspace>
  </div>
</template>
