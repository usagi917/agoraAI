<script setup lang="ts">
import { computed } from 'vue'

export interface CoalitionGroup {
  label: string
  support: number
  oppose: number
}

const props = defineProps<{
  coalitionMap: Record<string, unknown>
}>()

const groups = computed<CoalitionGroup[]>(() => {
  const result: CoalitionGroup[] = []
  const map = props.coalitionMap
  if (!map || typeof map !== 'object') return result

  for (const [category, segments] of Object.entries(map)) {
    if (!segments || typeof segments !== 'object') continue
    for (const [label, data] of Object.entries(segments as Record<string, unknown>)) {
      if (data && typeof data === 'object') {
        const d = data as Record<string, unknown>
        result.push({
          label: `${category}: ${label}`,
          support: typeof d.support === 'number' ? d.support : 0,
          oppose: typeof d.oppose === 'number' ? d.oppose : 0,
        })
      }
    }
  }
  return result
})

function pct(value: number): string {
  return (value * 100).toFixed(0)
}
</script>

<template>
  <div class="coalition-map" data-testid="coalition-map">
    <h3 class="coalition-title">Coalition Map</h3>
    <div v-if="groups.length === 0" class="coalition-empty">
      <p class="empty-text">データなし</p>
    </div>
    <div v-else class="coalition-groups">
      <div
        v-for="(group, i) in groups"
        :key="i"
        class="coalition-row"
        data-testid="coalition-row"
      >
        <span class="coalition-label">{{ group.label }}</span>
        <div class="coalition-bars">
          <div class="bar-track">
            <div
              class="bar-fill bar-support"
              :style="{ width: pct(group.support) + '%' }"
              :title="`Support: ${pct(group.support)}%`"
            />
            <div
              class="bar-fill bar-oppose"
              :style="{ width: pct(group.oppose) + '%' }"
              :title="`Oppose: ${pct(group.oppose)}%`"
            />
          </div>
          <div class="bar-labels">
            <span class="bar-pct bar-pct-support">{{ pct(group.support) }}%</span>
            <span class="bar-pct bar-pct-oppose">{{ pct(group.oppose) }}%</span>
          </div>
        </div>
      </div>
    </div>
    <div class="coalition-legend">
      <span class="legend-item">
        <span class="legend-dot legend-dot-support" />
        Support
      </span>
      <span class="legend-item">
        <span class="legend-dot legend-dot-oppose" />
        Oppose
      </span>
    </div>
  </div>
</template>

<style scoped>
.coalition-map {
  display: flex;
  flex-direction: column;
  gap: var(--space-4);
}

.coalition-title {
  font-size: var(--text-lg);
  font-weight: 700;
  padding-bottom: var(--space-2);
  border-bottom: 1px solid var(--border);
}

.coalition-empty {
  display: flex;
  align-items: center;
  justify-content: center;
  min-height: 80px;
}

.empty-text {
  color: var(--text-muted);
  font-size: var(--text-sm);
}

.coalition-groups {
  display: flex;
  flex-direction: column;
  gap: var(--space-3);
}

.coalition-row {
  display: flex;
  align-items: center;
  gap: var(--space-4);
}

.coalition-label {
  width: 160px;
  flex-shrink: 0;
  font-size: var(--text-sm);
  font-weight: 500;
  color: var(--text-primary);
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.coalition-bars {
  flex: 1;
  display: flex;
  flex-direction: column;
  gap: var(--space-1);
}

.bar-track {
  display: flex;
  height: 20px;
  background: rgba(255, 255, 255, 0.04);
  border-radius: var(--radius-sm);
  overflow: hidden;
}

.bar-fill {
  height: 100%;
  transition: width 0.6s ease;
}

.bar-support {
  background: var(--accent);
}

.bar-oppose {
  background: var(--highlight);
}

.bar-labels {
  display: flex;
  justify-content: space-between;
}

.bar-pct {
  font-family: var(--font-mono);
  font-size: var(--text-xs);
  font-weight: 600;
}

.bar-pct-support {
  color: var(--accent);
}

.bar-pct-oppose {
  color: var(--highlight);
}

.coalition-legend {
  display: flex;
  gap: var(--space-6);
  padding-top: var(--space-2);
}

.legend-item {
  display: inline-flex;
  align-items: center;
  gap: var(--space-2);
  font-size: var(--text-xs);
  color: var(--text-secondary);
}

.legend-dot {
  width: 10px;
  height: 10px;
  border-radius: 2px;
}

.legend-dot-support {
  background: var(--accent);
}

.legend-dot-oppose {
  background: var(--highlight);
}

@media (max-width: 640px) {
  .coalition-row {
    flex-direction: column;
    align-items: flex-start;
    gap: var(--space-2);
  }

  .coalition-label {
    width: auto;
  }

  .coalition-bars {
    width: 100%;
  }
}
</style>
