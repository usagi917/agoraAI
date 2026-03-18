<script setup lang="ts">
import { computed } from 'vue'
import { useCognitiveStore } from '../stores/cognitiveStore'

const store = useCognitiveStore()

const network = computed(() => store.socialNetwork)
const coalitions = computed(() => store.coalitions)

function edgeColor(type: string): string {
  switch (type) {
    case 'ally': return '#27ae60'
    case 'rival': return '#e74c3c'
    case 'neutral': return '#95a5a6'
    default: return '#3498db'
  }
}

function coalitionColor(idx: number): string {
  const colors = ['#3498db', '#e74c3c', '#27ae60', '#f39c12', '#9b59b6', '#1abc9c']
  return colors[idx % colors.length]
}
</script>

<template>
  <div class="social-network-dynamics">
    <h3>社会ネットワーク</h3>

    <div v-if="network.nodes.length === 0" class="no-data">
      ネットワークデータがありません
    </div>

    <div v-else>
      <!-- ノード一覧 -->
      <div class="network-summary">
        <span class="stat">ノード: {{ network.nodes.length }}</span>
        <span class="stat">エッジ: {{ network.edges.length }}</span>
        <span class="stat" v-if="coalitions.length > 0">同盟: {{ coalitions.length }}</span>
      </div>

      <!-- 関係マトリックス -->
      <div class="relationship-list">
        <div
          v-for="edge in network.edges"
          :key="`${edge.source}-${edge.target}`"
          class="edge-item"
        >
          <span class="edge-source">{{ edge.source }}</span>
          <span class="edge-arrow" :style="{ color: edgeColor(edge.type) }">&mdash;{{ edge.type }}&rarr;</span>
          <span class="edge-target">{{ edge.target }}</span>
          <span class="edge-strength">強度: {{ ((edge.strength || 0.5) * 100).toFixed(0) }}%</span>
          <span class="edge-trust">信頼: {{ ((edge.trust || 0.5) * 100).toFixed(0) }}%</span>
        </div>
      </div>

      <!-- 同盟グループ -->
      <div v-if="coalitions.length > 0" class="coalitions-section">
        <h4>検出された同盟</h4>
        <div
          v-for="(coalition, idx) in coalitions"
          :key="idx"
          class="coalition-card"
          :style="{ borderLeftColor: coalitionColor(idx) }"
        >
          <div class="coalition-label" :style="{ color: coalitionColor(idx) }">
            同盟 {{ idx + 1 }}
          </div>
          <div class="coalition-members">
            <span v-for="member in coalition" :key="member" class="member-badge">
              {{ member }}
            </span>
          </div>
        </div>
      </div>
    </div>
  </div>
</template>

<style scoped>
.social-network-dynamics {
  padding: 1rem;
}
.no-data {
  text-align: center;
  color: #999;
  padding: 2rem;
}
.network-summary {
  display: flex;
  gap: 1.5rem;
  margin-bottom: 1.5rem;
}
.stat {
  padding: 0.4rem 0.8rem;
  background: #f8f9fa;
  border-radius: 6px;
  font-size: 0.85rem;
}
.relationship-list {
  margin-bottom: 2rem;
}
.edge-item {
  display: flex;
  align-items: center;
  gap: 0.75rem;
  padding: 0.5rem;
  border-bottom: 1px solid #f0f0f0;
}
.edge-source, .edge-target {
  font-weight: 500;
}
.edge-arrow {
  font-size: 0.8rem;
}
.edge-strength, .edge-trust {
  font-size: 0.8rem;
  color: #888;
}
.coalitions-section {
  margin-top: 1rem;
}
.coalition-card {
  padding: 0.75rem;
  margin-bottom: 0.5rem;
  background: #f8f9fa;
  border-radius: 6px;
  border-left: 4px solid;
}
.coalition-label {
  font-weight: 600;
  margin-bottom: 0.4rem;
}
.coalition-members {
  display: flex;
  gap: 0.5rem;
  flex-wrap: wrap;
}
.member-badge {
  padding: 0.2rem 0.5rem;
  background: white;
  border: 1px solid #e0e0e0;
  border-radius: 4px;
  font-size: 0.85rem;
}
</style>
