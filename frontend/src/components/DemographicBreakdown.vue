<script setup lang="ts">
import { computed } from 'vue'
import type { SocialGraphNode } from '../api/client'

const props = defineProps<{
  agents: SocialGraphNode[]
}>()

const stanceColors: Record<string, string> = {
  '賛成': '#22c55e',
  '条件付き賛成': '#86efac',
  '中立': '#a3a3a3',
  '条件付き反対': '#fca5a5',
  '反対': '#ef4444',
}

function computeBreakdown(groupFn: (a: SocialGraphNode) => string) {
  const groups: Record<string, Record<string, number>> = {}
  const allStances = new Set<string>()

  for (const a of props.agents) {
    const group = groupFn(a)
    const stance = a.stance || '不明'
    allStances.add(stance)
    if (!groups[group]) groups[group] = {}
    groups[group][stance] = (groups[group][stance] || 0) + 1
  }

  const stanceList = Array.from(allStances)
  const groupEntries = Object.entries(groups)
    .map(([group, stances]) => {
      const total = Object.values(stances).reduce((s, v) => s + v, 0)
      return {
        group,
        total,
        stances: stanceList.map((s) => ({
          stance: s,
          count: stances[s] || 0,
          percent: total > 0 ? Math.round(((stances[s] || 0) / total) * 100) : 0,
          color: stanceColors[s] || '#6b7280',
        })),
      }
    })
    .sort((a, b) => b.total - a.total)

  return { groups: groupEntries, stances: stanceList }
}

const ageGroups = computed(() => {
  return computeBreakdown((a) => {
    const age = a.demographics?.age || 0
    if (age < 30) return '18-29'
    if (age < 40) return '30-39'
    if (age < 50) return '40-49'
    if (age < 60) return '50-59'
    return '60+'
  })
})

const regionGroups = computed(() => {
  return computeBreakdown((a) => a.demographics?.region || '不明')
})

const occupationGroups = computed(() => {
  return computeBreakdown((a) => a.demographics?.occupation || '不明')
})
</script>

<template>
  <div class="space-y-6">
    <!-- Age breakdown -->
    <section>
      <h4 class="text-xs font-semibold text-gray-400 uppercase tracking-wider mb-3">Age x Stance</h4>
      <div class="space-y-2">
        <div v-for="entry in ageGroups.groups" :key="entry.group" class="flex items-center gap-2">
          <span class="w-14 text-xs text-gray-400 text-right shrink-0">{{ entry.group }}</span>
          <div class="flex-1 flex h-5 rounded overflow-hidden bg-gray-800">
            <div
              v-for="s in entry.stances"
              :key="s.stance"
              :style="{ width: `${s.percent}%`, backgroundColor: s.color }"
              class="transition-all"
              :title="`${s.stance}: ${s.count} (${s.percent}%)`"
            />
          </div>
          <span class="w-8 text-xs text-gray-500 text-right shrink-0">{{ entry.total }}</span>
        </div>
      </div>
    </section>

    <!-- Region breakdown -->
    <section>
      <h4 class="text-xs font-semibold text-gray-400 uppercase tracking-wider mb-3">Region x Stance</h4>
      <div class="space-y-2">
        <div v-for="entry in regionGroups.groups.slice(0, 10)" :key="entry.group" class="flex items-center gap-2">
          <span class="w-28 text-xs text-gray-400 text-right shrink-0 truncate" :title="entry.group">{{ entry.group }}</span>
          <div class="flex-1 flex h-5 rounded overflow-hidden bg-gray-800">
            <div
              v-for="s in entry.stances"
              :key="s.stance"
              :style="{ width: `${s.percent}%`, backgroundColor: s.color }"
              class="transition-all"
              :title="`${s.stance}: ${s.count} (${s.percent}%)`"
            />
          </div>
          <span class="w-8 text-xs text-gray-500 text-right shrink-0">{{ entry.total }}</span>
        </div>
      </div>
    </section>

    <!-- Occupation breakdown (top 10) -->
    <section>
      <h4 class="text-xs font-semibold text-gray-400 uppercase tracking-wider mb-3">Occupation x Stance (top 10)</h4>
      <div class="space-y-2">
        <div v-for="entry in occupationGroups.groups.slice(0, 10)" :key="entry.group" class="flex items-center gap-2">
          <span class="w-28 text-xs text-gray-400 text-right shrink-0 truncate" :title="entry.group">{{ entry.group }}</span>
          <div class="flex-1 flex h-5 rounded overflow-hidden bg-gray-800">
            <div
              v-for="s in entry.stances"
              :key="s.stance"
              :style="{ width: `${s.percent}%`, backgroundColor: s.color }"
              class="transition-all"
              :title="`${s.stance}: ${s.count} (${s.percent}%)`"
            />
          </div>
          <span class="w-8 text-xs text-gray-500 text-right shrink-0">{{ entry.total }}</span>
        </div>
      </div>
    </section>

    <!-- Legend -->
    <div class="flex items-center gap-4 text-xs text-gray-500 pt-2 border-t border-gray-800">
      <span v-for="(color, stance) in stanceColors" :key="stance" class="flex items-center gap-1">
        <span class="w-2.5 h-2.5 rounded-sm" :style="{ backgroundColor: color }" />
        {{ stance }}
      </span>
    </div>
  </div>
</template>
