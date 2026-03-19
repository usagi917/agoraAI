<script setup lang="ts">
import { computed } from 'vue'
import { useCognitiveStore } from '../stores/cognitiveStore'

const store = useCognitiveStore()

const network = computed(() => store.socialNetwork)
const coalitions = computed(() => store.coalitions)

function edgeColor(type: string): string {
  switch (type) {
    case 'ally': return 'var(--success)'
    case 'rival': return 'var(--danger)'
    case 'neutral': return 'var(--text-muted)'
    default: return 'var(--accent)'
  }
}

function edgeBadgeClass(type: string): string {
  switch (type) {
    case 'ally': return 'badge-success'
    case 'rival': return 'badge-danger'
    case 'neutral': return 'badge-muted'
    default: return 'badge-accent'
  }
}

function coalitionColor(idx: number): string {
  const colors = ['var(--accent)', 'var(--danger)', 'var(--success)', 'var(--warning)', '#a855f7', '#14b8a6']
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
        <span class="stat">
          <span class="stat-value">{{ network.nodes.length }}</span>
          <span class="stat-label">ノード</span>
        </span>
        <span class="stat">
          <span class="stat-value">{{ network.edges.length }}</span>
          <span class="stat-label">エッジ</span>
        </span>
        <span class="stat" v-if="coalitions.length > 0">
          <span class="stat-value">{{ coalitions.length }}</span>
          <span class="stat-label">同盟</span>
        </span>
      </div>

      <!-- 関係マトリックス -->
      <div class="relationship-list">
        <div
          v-for="edge in network.edges"
          :key="`${edge.source}-${edge.target}`"
          class="edge-item"
        >
          <span class="edge-source">{{ edge.source }}</span>
          <span class="edge-type-badge" :class="edgeBadgeClass(edge.type)">{{ edge.type }}</span>
          <span class="edge-arrow" :style="{ color: edgeColor(edge.type) }">&rarr;</span>
          <span class="edge-target">{{ edge.target }}</span>
          <span class="edge-meta">
            <span class="edge-strength">強度 {{ ((edge.strength || 0.5) * 100).toFixed(0) }}%</span>
            <span class="edge-trust">信頼 {{ ((edge.trust || 0.5) * 100).toFixed(0) }}%</span>
          </span>
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
.social-network-dynamics h3 {
  color: var(--text-primary);
  margin-bottom: 1rem;
}
.social-network-dynamics h4 {
  color: var(--text-secondary);
  margin-bottom: 0.75rem;
}

.no-data {
  text-align: center;
  color: var(--text-muted);
  padding: 2rem;
  background: var(--bg-card);
  border: 1px dashed var(--border);
  border-radius: var(--radius);
}

/* Stats */
.network-summary {
  display: flex;
  gap: 1rem;
  margin-bottom: 1.5rem;
}
.stat {
  display: flex;
  flex-direction: column;
  align-items: center;
  padding: 0.6rem 1.2rem;
  background: var(--bg-card);
  border: 1px solid var(--border);
  border-radius: var(--radius);
  min-width: 70px;
}
.stat-value {
  font-family: var(--font-mono);
  font-size: 1.25rem;
  font-weight: 700;
  color: var(--accent);
}
.stat-label {
  font-size: 0.75rem;
  color: var(--text-muted);
  margin-top: 0.15rem;
}

/* Edge list */
.relationship-list {
  margin-bottom: 2rem;
}
.edge-item {
  display: flex;
  align-items: center;
  gap: 0.75rem;
  padding: 0.6rem 0.75rem;
  border: 1px solid var(--border);
  border-radius: var(--radius-sm);
  margin-bottom: 0.35rem;
  background: var(--bg-card);
  transition: border-color 0.2s;
}
.edge-item:hover {
  border-color: var(--border-active);
}
.edge-source,
.edge-target {
  font-weight: 500;
  color: var(--text-primary);
}
.edge-arrow {
  font-size: 0.9rem;
}

/* Relationship type badges */
.edge-type-badge {
  font-size: 0.7rem;
  font-weight: 600;
  text-transform: uppercase;
  letter-spacing: 0.04em;
  padding: 0.15rem 0.45rem;
  border-radius: var(--radius-sm);
}
.badge-success {
  background: rgba(34, 197, 94, 0.15);
  color: var(--success);
}
.badge-danger {
  background: rgba(239, 68, 68, 0.15);
  color: var(--danger);
}
.badge-muted {
  background: rgba(255, 255, 255, 0.06);
  color: var(--text-muted);
}
.badge-accent {
  background: var(--accent-subtle);
  color: var(--accent);
}

.edge-meta {
  margin-left: auto;
  display: flex;
  gap: 0.75rem;
}
.edge-strength,
.edge-trust {
  font-family: var(--font-mono);
  font-size: 0.78rem;
  color: var(--text-muted);
}

/* Coalitions */
.coalitions-section {
  margin-top: 1rem;
}
.coalition-card {
  padding: 0.75rem 1rem;
  margin-bottom: 0.5rem;
  background: var(--bg-card);
  border: 1px solid var(--border);
  border-radius: var(--radius);
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
  padding: 0.2rem 0.55rem;
  background: var(--bg-surface);
  border: 1px solid var(--border);
  border-radius: var(--radius-sm);
  font-size: 0.85rem;
  color: var(--text-primary);
}
</style>
