<script setup lang="ts">
import { computed } from 'vue'
import { useSocietyGraphStore, STANCE_COLORS } from '../stores/societyGraphStore'
import { useKGEvolutionStore } from '../stores/kgEvolutionStore'

const props = defineProps<{
  nodeId: string
}>()

const emit = defineEmits<{
  close: []
  highlightAgents: [agentIds: string[]]
}>()

const societyGraphStore = useSocietyGraphStore()
const kgStore = useKGEvolutionStore()

const isKGNode = computed(() => props.nodeId.startsWith('kg-'))

// Agent node data
const agent = computed(() => {
  if (isKGNode.value) return null
  return societyGraphStore.liveAgents.get(props.nodeId) ?? null
})

// KG entity node data
const kgEntity = computed(() => {
  if (!isKGNode.value) return null
  return kgStore.entities.get(props.nodeId) ?? null
})

// Related KG entities for an agent
const relatedEntities = computed(() => {
  if (isKGNode.value) return []
  const entityIds = kgStore.getEntitiesForAgent(props.nodeId)
  return entityIds
    .map((id) => kgStore.entities.get(id))
    .filter(Boolean) as Array<{ id: string; label: string; type: string; importanceScore: number }>
})

// Related agents for a KG entity
const relatedAgents = computed(() => {
  if (!isKGNode.value) return []
  const agentIds = kgStore.getAgentsForEntity(props.nodeId)
  return agentIds
    .map((id) => {
      const a = societyGraphStore.liveAgents.get(id)
      if (!a) return null
      return { id: a.id, label: a.displayName || a.label, stance: a.stance, confidence: a.confidence }
    })
    .filter(Boolean) as Array<{ id: string; label: string; stance: string | null; confidence: number }>
})

// Related KG edges for a KG entity
const relatedRelations = computed(() => {
  if (!isKGNode.value) return []
  const rels: Array<{ id: string; source: string; target: string; relationType: string; weight: number }> = []
  for (const r of kgStore.relations.values()) {
    if (r.source === props.nodeId || r.target === props.nodeId) {
      const otherSide = r.source === props.nodeId ? r.target : r.source
      const otherEntity = kgStore.entities.get(otherSide)
      rels.push({
        id: r.id,
        source: r.source === props.nodeId ? kgEntity.value?.label || '' : otherEntity?.label || otherSide,
        target: r.target === props.nodeId ? kgEntity.value?.label || '' : otherEntity?.label || otherSide,
        relationType: r.relationType,
        weight: r.weight,
      })
    }
  }
  return rels
})

function handleHighlightAgents() {
  const agentIds = relatedAgents.value.map((a) => a.id)
  emit('highlightAgents', agentIds)
}

const TYPE_LABELS: Record<string, string> = {
  concept: '概念',
  risk: 'リスク',
  opportunity: '機会',
  stakeholder: '利害関係者',
  metric: '指標',
  policy: '政策',
  organization: '組織',
  person: '人物',
  market: '市場',
  technology: '技術',
  resource: '資源',
  event: 'イベント',
}
</script>

<template>
  <div class="node-detail-panel">
    <div class="panel-header">
      <div class="panel-title-row">
        <span v-if="isKGNode" class="panel-type-badge kg">{{ TYPE_LABELS[kgEntity?.type || ''] || kgEntity?.type }}</span>
        <span v-else class="panel-type-badge agent">Agent</span>
        <h4>{{ isKGNode ? kgEntity?.label : (agent?.displayName || agent?.label) }}</h4>
      </div>
      <button class="btn-close" @click="emit('close')">&times;</button>
    </div>

    <!-- Agent detail -->
    <template v-if="agent && !isKGNode">
      <div class="detail-meta">
        <span v-if="agent.region" class="meta-chip">{{ agent.region }}</span>
        <span v-if="agent.occupation" class="meta-chip">{{ agent.occupation }}</span>
        <span v-if="agent.age" class="meta-chip">{{ agent.age }}歳</span>
      </div>
      <div v-if="agent.stance" class="detail-stance">
        <span class="stance-badge" :style="{ background: STANCE_COLORS[agent.stance] || '#a3a3a3' }">
          {{ agent.stance }}
        </span>
        <span class="confidence">{{ Math.round(agent.confidence * 100) }}%</span>
      </div>
      <div v-if="agent.speakingText" class="detail-speech">
        <p>{{ agent.speakingText }}</p>
      </div>

      <!-- Related KG entities -->
      <div v-if="relatedEntities.length" class="detail-section">
        <h5>関連する概念</h5>
        <div class="entity-chips">
          <span
            v-for="e in relatedEntities"
            :key="e.id"
            class="entity-chip"
          >
            {{ e.label }}
          </span>
        </div>
      </div>
    </template>

    <!-- KG Entity detail -->
    <template v-if="kgEntity && isKGNode">
      <div class="detail-meta">
        <span class="meta-chip">importance: {{ Math.round(kgEntity.importanceScore * 100) }}%</span>
        <span class="meta-chip">round {{ kgEntity.round }}</span>
      </div>

      <!-- Related agents -->
      <div v-if="relatedAgents.length" class="detail-section">
        <div class="section-header">
          <h5>言及したエージェント ({{ relatedAgents.length }})</h5>
          <button class="btn-highlight" @click="handleHighlightAgents">Highlight</button>
        </div>
        <div class="agent-list">
          <div v-for="a in relatedAgents" :key="a.id" class="agent-row">
            <span class="agent-name">{{ a.label }}</span>
            <span
              v-if="a.stance"
              class="stance-dot"
              :style="{ background: STANCE_COLORS[a.stance] || '#a3a3a3' }"
            />
          </div>
        </div>
      </div>

      <!-- Related KG relations -->
      <div v-if="relatedRelations.length" class="detail-section">
        <h5>関連するエッジ</h5>
        <div class="relation-list">
          <div v-for="r in relatedRelations" :key="r.id" class="relation-row">
            <span class="relation-label">{{ r.source }}</span>
            <span class="relation-type">{{ r.relationType }}</span>
            <span class="relation-label">{{ r.target }}</span>
            <span class="relation-weight">{{ Math.round(r.weight * 100) }}%</span>
          </div>
        </div>
      </div>
    </template>
  </div>
</template>

<style scoped>
.node-detail-panel {
  max-width: 18rem;
  max-height: 24rem;
  overflow-y: auto;
  padding: 0.75rem 1rem;
  background: rgba(12, 12, 28, 0.94);
  backdrop-filter: blur(14px);
  border: 1px solid rgba(100, 140, 255, 0.2);
  border-radius: 10px;
  font-size: 0.75rem;
  color: rgba(220, 220, 240, 0.85);
}
.panel-header {
  display: flex;
  justify-content: space-between;
  align-items: flex-start;
  margin-bottom: 0.5rem;
}
.panel-title-row {
  display: flex;
  align-items: center;
  gap: 0.4rem;
  flex: 1;
  min-width: 0;
}
.panel-title-row h4 {
  margin: 0;
  font-size: 0.85rem;
  font-weight: 600;
  color: #fff;
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
}
.panel-type-badge {
  flex-shrink: 0;
  padding: 0.1rem 0.35rem;
  border-radius: 4px;
  font-size: 0.6rem;
  font-weight: 700;
  text-transform: uppercase;
  letter-spacing: 0.03em;
}
.panel-type-badge.agent {
  background: rgba(255, 183, 77, 0.2);
  color: #FFB74D;
  border: 1px solid rgba(255, 183, 77, 0.3);
}
.panel-type-badge.kg {
  background: rgba(186, 104, 200, 0.2);
  color: #CE93D8;
  border: 1px solid rgba(186, 104, 200, 0.3);
}
.btn-close {
  background: none;
  border: none;
  color: rgba(200, 200, 220, 0.5);
  cursor: pointer;
  font-size: 1.1rem;
  line-height: 1;
  padding: 0;
  flex-shrink: 0;
}
.btn-close:hover { color: #fff; }
.detail-meta {
  display: flex;
  flex-wrap: wrap;
  gap: 0.3rem;
  margin-bottom: 0.5rem;
}
.meta-chip {
  padding: 0.1rem 0.4rem;
  background: rgba(100, 100, 200, 0.12);
  border: 1px solid rgba(100, 100, 200, 0.15);
  border-radius: 4px;
  font-size: 0.65rem;
  color: rgba(200, 200, 255, 0.6);
}
.detail-stance {
  display: flex;
  align-items: center;
  gap: 0.5rem;
  margin-bottom: 0.5rem;
}
.stance-badge {
  padding: 0.15rem 0.5rem;
  border-radius: 4px;
  font-size: 0.7rem;
  font-weight: 600;
  color: #fff;
}
.confidence {
  font-size: 0.65rem;
  color: rgba(200, 200, 255, 0.5);
}
.detail-speech {
  margin-bottom: 0.5rem;
  padding: 0.4rem 0.5rem;
  background: rgba(50, 50, 80, 0.3);
  border-radius: 6px;
  border-left: 2px solid rgba(255, 202, 40, 0.4);
}
.detail-speech p {
  margin: 0;
  font-size: 0.7rem;
  line-height: 1.4;
  color: rgba(220, 220, 240, 0.7);
}
.detail-section {
  margin-top: 0.6rem;
  padding-top: 0.5rem;
  border-top: 1px solid rgba(100, 100, 200, 0.1);
}
.detail-section h5 {
  margin: 0 0 0.35rem;
  font-size: 0.7rem;
  font-weight: 600;
  color: rgba(200, 200, 255, 0.5);
  text-transform: uppercase;
  letter-spacing: 0.04em;
}
.section-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-bottom: 0.35rem;
}
.section-header h5 { margin-bottom: 0; }
.btn-highlight {
  padding: 0.1rem 0.4rem;
  background: rgba(186, 104, 200, 0.15);
  border: 1px solid rgba(186, 104, 200, 0.3);
  border-radius: 4px;
  color: #CE93D8;
  font-size: 0.6rem;
  cursor: pointer;
}
.btn-highlight:hover {
  background: rgba(186, 104, 200, 0.25);
}
.entity-chips {
  display: flex;
  flex-wrap: wrap;
  gap: 0.25rem;
}
.entity-chip {
  padding: 0.1rem 0.4rem;
  background: rgba(186, 104, 200, 0.12);
  border: 1px solid rgba(186, 104, 200, 0.2);
  border-radius: 4px;
  font-size: 0.65rem;
  color: #CE93D8;
}
.agent-list {
  display: flex;
  flex-direction: column;
  gap: 0.2rem;
}
.agent-row {
  display: flex;
  align-items: center;
  gap: 0.35rem;
  padding: 0.15rem 0;
}
.agent-name {
  font-size: 0.68rem;
  color: rgba(220, 220, 240, 0.7);
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}
.stance-dot {
  width: 8px;
  height: 8px;
  border-radius: 50%;
  flex-shrink: 0;
}
.relation-list {
  display: flex;
  flex-direction: column;
  gap: 0.2rem;
}
.relation-row {
  display: flex;
  align-items: center;
  gap: 0.3rem;
  font-size: 0.65rem;
}
.relation-label {
  color: rgba(200, 200, 255, 0.6);
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
  max-width: 5rem;
}
.relation-type {
  padding: 0 0.3rem;
  color: rgba(186, 104, 200, 0.7);
  font-size: 0.6rem;
}
.relation-weight {
  color: rgba(200, 200, 255, 0.4);
  font-size: 0.6rem;
  flex-shrink: 0;
}
</style>
