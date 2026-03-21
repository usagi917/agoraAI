<script setup lang="ts">
import { ref, onMounted } from 'vue'
import { listSimulations, type SimulationListItem } from '../api/client'

const props = defineProps<{
  currentSimId: string
  populationId?: string
}>()

const relatedSims = ref<SimulationListItem[]>([])

onMounted(async () => {
  try {
    const all = await listSimulations()
    // society モードのシミュレーションを時系列で表示
    relatedSims.value = all
      .filter(s => s.mode === 'society')
      .slice(0, 10)
  } catch {
    // ignore
  }
})
</script>

<template>
  <div class="society-timeline">
    <div v-if="!relatedSims.length" class="timeline-empty">他の Society シミュレーションはありません</div>
    <div v-else class="timeline-list">
      <router-link
        v-for="sim in relatedSims"
        :key="sim.id"
        :to="sim.status === 'completed' ? `/sim/${sim.id}/results` : `/sim/${sim.id}`"
        class="timeline-item"
        :class="{ current: sim.id === currentSimId }"
      >
        <div class="timeline-dot" :class="sim.status" />
        <div class="timeline-info">
          <span class="timeline-id">{{ sim.id.slice(0, 8) }}</span>
          <span class="timeline-status" :class="sim.status">{{ sim.status }}</span>
        </div>
        <div class="timeline-date">{{ new Date(sim.created_at).toLocaleString('ja-JP') }}</div>
      </router-link>
    </div>
  </div>
</template>

<style scoped>
.society-timeline { display: flex; flex-direction: column; gap: 0.5rem; }
.timeline-empty { font-size: 0.82rem; color: var(--text-muted); }
.timeline-list { display: flex; flex-direction: column; gap: 0.35rem; }
.timeline-item { display: flex; align-items: center; gap: 0.75rem; padding: 0.5rem 0.75rem; border: 1px solid var(--border); border-radius: var(--radius-sm); text-decoration: none; color: var(--text-primary); transition: border-color 0.2s; }
.timeline-item:hover { border-color: rgba(255,255,255,0.12); }
.timeline-item.current { border-color: var(--accent); background: var(--accent-subtle); }
.timeline-dot { width: 8px; height: 8px; border-radius: 50%; flex-shrink: 0; }
.timeline-dot.completed { background: var(--success); }
.timeline-dot.running { background: var(--accent); animation: pulse-dot 2s infinite; }
.timeline-dot.failed { background: var(--danger); }
.timeline-dot.queued { background: var(--text-muted); }
.timeline-info { display: flex; align-items: center; gap: 0.5rem; flex: 1; }
.timeline-id { font-family: var(--font-mono); font-size: 0.78rem; font-weight: 600; }
.timeline-status { font-family: var(--font-mono); font-size: 0.65rem; padding: 0.1rem 0.3rem; border-radius: 3px; }
.timeline-status.completed { background: rgba(34,197,94,0.15); color: var(--success); }
.timeline-status.running { background: var(--accent-subtle); color: var(--accent); }
.timeline-status.failed { background: rgba(239,68,68,0.15); color: var(--danger); }
.timeline-date { font-family: var(--font-mono); font-size: 0.68rem; color: var(--text-muted); white-space: nowrap; }
</style>
