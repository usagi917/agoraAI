<script setup lang="ts">
import { onMounted } from 'vue'
import LiveSocietyGraph from '../components/LiveSocietyGraph.vue'
import { useSocietyGraphStore } from '../stores/societyGraphStore'
import { useSimulationStore } from '../stores/simulationStore'
import type { SocialGraphNode, SocialGraphEdge } from '../api/client'

const societyGraphStore = useSocietyGraphStore()
const simulationStore = useSimulationStore()

const STANCES = ['賛成', '条件付き賛成', '中立', '条件付き反対', '反対']
const RELATIONS = ['friend', 'family', 'colleague', 'neighbor', 'acquaintance']

function sleep(ms: number) {
  return new Promise((r) => setTimeout(r, ms))
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

  // 2. 活性化進捗 (SSE: society_activation_progress)
  for (let done = 10; done <= 101; done += 30) {
    societyGraphStore.updateActivationProgress(Math.min(done, 101), 101)
    await sleep(120)
  }

  // 3. ソーシャルグラフ hydrate (SSE: social graph / stance 確定)
  const nodes: SocialGraphNode[] = Array.from({ length: 101 }, (_, i) => ({
    id: `agent-${i}`,
    agent_index: i,
    stance: STANCES[i % STANCES.length],
    confidence: 0.4 + (i % 6) / 10,
    demographics: { occupation: '会社員', age: 30 + (i % 40), region: '関東' },
  })) as unknown as SocialGraphNode[]

  const edges: SocialGraphEdge[] = Array.from({ length: 11 }, (_, i) => ({
    id: `edge-${i}`,
    source: `agent-${i}`,
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

  societyGraphStore.hydrateWithSocialGraph(nodes, edges)
  await sleep(400)

  // 4. 評議会フェーズ (SSE: council round)
  simulationStore.unifiedPhase = 'council'
  societyGraphStore.appendMeetingDialogue(3, {
    participant_name: '松田 章太',
    participant_index: 0,
    role: 'representative',
    argument: '結局のところ数字が示していることは…',
  })
})
</script>

<template>
  <div style="position: fixed; inset: 0">
    <LiveSocietyGraph simulation-id="dev-sim" />
  </div>
</template>
