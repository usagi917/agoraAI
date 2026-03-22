<script setup lang="ts">
import { computed } from 'vue'
import type { NarrativeResponse } from '../api/client'

const props = defineProps<{
  narrative: NarrativeResponse | null
}>()

const emit = defineEmits<{
  selectAgent: [agentId: string]
}>()

const stanceBadgeClass: Record<string, string> = {
  '賛成': 'bg-green-600 text-white',
  '条件付き賛成': 'bg-green-400 text-gray-900',
  '中立': 'bg-gray-500 text-white',
  '条件付き反対': 'bg-red-400 text-gray-900',
  '反対': 'bg-red-600 text-white',
}

function getStanceClass(stance: string): string {
  return stanceBadgeClass[stance] || 'bg-gray-600 text-white'
}

const hasContent = computed(() => {
  if (!props.narrative) return false
  return (
    props.narrative.key_findings.length > 0 ||
    props.narrative.consensus_areas.length > 0 ||
    props.narrative.controversy_areas.length > 0 ||
    props.narrative.recommendations.length > 0
  )
})
</script>

<template>
  <div v-if="narrative && hasContent" class="space-y-6">
    <!-- Executive Summary -->
    <div v-if="narrative.executive_summary" class="bg-gradient-to-r from-indigo-900/30 to-purple-900/30 rounded-xl p-5 border border-indigo-700/30">
      <h3 class="text-sm font-semibold text-indigo-300 uppercase tracking-wider mb-2">Executive Summary</h3>
      <p class="text-gray-200 text-sm leading-relaxed">{{ narrative.executive_summary }}</p>
    </div>

    <!-- Key Findings -->
    <section v-if="narrative.key_findings.length > 0">
      <h3 class="text-xs font-semibold text-gray-400 uppercase tracking-wider mb-3">
        Key Findings ({{ narrative.key_findings.length }})
      </h3>
      <div class="space-y-3">
        <div
          v-for="(finding, idx) in narrative.key_findings"
          :key="idx"
          class="bg-gray-800/60 rounded-lg p-4 border-l-3 border-indigo-500"
        >
          <div class="flex items-start justify-between gap-3 mb-2">
            <p class="text-gray-200 text-sm leading-relaxed flex-1">{{ finding.finding }}</p>
            <div class="flex items-center gap-2 shrink-0">
              <span
                class="text-xs px-2 py-0.5 rounded-full"
                :class="finding.type === 'scenario' ? 'bg-purple-900/50 text-purple-300' : 'bg-blue-900/50 text-blue-300'"
              >
                {{ finding.type === 'scenario' ? 'Scenario' : 'Insight' }}
              </span>
              <span class="text-xs text-gray-500">
                {{ Math.round(finding.confidence * 100) }}%
              </span>
            </div>
          </div>

          <div v-if="finding.key_factors?.length" class="flex flex-wrap gap-1 mb-2">
            <span
              v-for="(factor, fi) in finding.key_factors"
              :key="fi"
              class="text-xs px-1.5 py-0.5 bg-gray-700 text-gray-400 rounded"
            >
              {{ factor }}
            </span>
          </div>

          <!-- Supporting Agent Quotes -->
          <div v-if="finding.supporting_evidence?.length" class="mt-3 space-y-2">
            <div
              v-for="(quote, qi) in finding.supporting_evidence"
              :key="qi"
              class="flex items-start gap-2 pl-3 border-l border-gray-600"
            >
              <button
                class="shrink-0 flex items-center gap-1 hover:bg-gray-700 rounded px-1.5 py-0.5 transition-colors"
                @click="emit('selectAgent', quote.agent_id)"
              >
                <span class="text-xs text-gray-300">{{ quote.occupation }}</span>
                <span class="text-xs text-gray-500">{{ quote.age }}歳</span>
                <span :class="[getStanceClass(quote.stance), 'text-[10px] px-1 py-px rounded']">
                  {{ quote.stance }}
                </span>
              </button>
              <p class="text-xs text-gray-400 italic leading-relaxed">&ldquo;{{ quote.quote }}&rdquo;</p>
            </div>
          </div>
        </div>
      </div>
    </section>

    <!-- Consensus Areas -->
    <section v-if="narrative.consensus_areas.length > 0">
      <h3 class="text-xs font-semibold text-green-400 uppercase tracking-wider mb-3">
        Consensus ({{ narrative.consensus_areas.length }})
      </h3>
      <div class="space-y-3">
        <div
          v-for="(consensus, idx) in narrative.consensus_areas"
          :key="idx"
          class="bg-gray-800/60 rounded-lg p-4 border-l-3 border-green-500"
        >
          <p class="text-gray-200 text-sm leading-relaxed flex items-start gap-2">
            <span class="text-green-400 shrink-0 mt-0.5">+</span>
            {{ consensus.point }}
          </p>

          <div v-if="consensus.supporting_agents?.length" class="mt-2 flex flex-wrap gap-2">
            <button
              v-for="(agent, ai) in consensus.supporting_agents"
              :key="ai"
              class="flex items-center gap-1 px-2 py-1 bg-gray-700/50 rounded hover:bg-gray-600/50 transition-colors"
              @click="emit('selectAgent', agent.agent_id)"
            >
              <span class="text-xs text-gray-300">{{ agent.occupation }}, {{ agent.age }}歳</span>
              <span :class="[getStanceClass(agent.stance), 'text-[10px] px-1 py-px rounded']">
                {{ agent.stance }}
              </span>
            </button>
          </div>
        </div>
      </div>
    </section>

    <!-- Controversy Areas -->
    <section v-if="narrative.controversy_areas.length > 0">
      <h3 class="text-xs font-semibold text-red-400 uppercase tracking-wider mb-3">
        Controversies ({{ narrative.controversy_areas.length }})
      </h3>
      <div class="space-y-3">
        <div
          v-for="(controversy, idx) in narrative.controversy_areas"
          :key="idx"
          class="bg-gray-800/60 rounded-lg p-4 border-l-3 border-red-500"
        >
          <p class="text-gray-200 text-sm leading-relaxed mb-2">{{ controversy.point }}</p>

          <!-- Positions -->
          <div v-if="controversy.positions?.length" class="space-y-1 mb-2">
            <div
              v-for="(pos, pi) in controversy.positions"
              :key="pi"
              class="text-xs text-gray-400"
            >
              <span class="text-gray-300 font-medium">{{ pos.participant }}:</span> {{ pos.position }}
            </div>
          </div>

          <!-- Pro vs Con quotes -->
          <div class="grid grid-cols-2 gap-3 mt-3">
            <div v-if="controversy.supporting_quotes?.length">
              <span class="text-[10px] text-green-400 uppercase tracking-wider">Supporting</span>
              <div v-for="(q, qi) in controversy.supporting_quotes" :key="qi" class="mt-1">
                <button
                  class="text-left hover:bg-gray-700 rounded px-1.5 py-0.5 transition-colors w-full"
                  @click="emit('selectAgent', q.agent_id)"
                >
                  <span class="text-xs text-gray-300">{{ q.occupation }}, {{ q.age }}歳</span>
                  <p class="text-xs text-gray-500 italic">&ldquo;{{ q.quote.slice(0, 80) }}...&rdquo;</p>
                </button>
              </div>
            </div>
            <div v-if="controversy.opposing_quotes?.length">
              <span class="text-[10px] text-red-400 uppercase tracking-wider">Opposing</span>
              <div v-for="(q, qi) in controversy.opposing_quotes" :key="qi" class="mt-1">
                <button
                  class="text-left hover:bg-gray-700 rounded px-1.5 py-0.5 transition-colors w-full"
                  @click="emit('selectAgent', q.agent_id)"
                >
                  <span class="text-xs text-gray-300">{{ q.occupation }}, {{ q.age }}歳</span>
                  <p class="text-xs text-gray-500 italic">&ldquo;{{ q.quote.slice(0, 80) }}...&rdquo;</p>
                </button>
              </div>
            </div>
          </div>
        </div>
      </div>
    </section>

    <!-- Recommendations -->
    <section v-if="narrative.recommendations.length > 0">
      <h3 class="text-xs font-semibold text-blue-400 uppercase tracking-wider mb-3">
        Recommendations ({{ narrative.recommendations.length }})
      </h3>
      <div class="space-y-3">
        <div
          v-for="(rec, idx) in narrative.recommendations"
          :key="idx"
          class="bg-gray-800/60 rounded-lg p-4 border-l-3 border-blue-500"
        >
          <p class="text-gray-200 text-sm leading-relaxed flex items-start gap-2">
            <span class="text-blue-400 shrink-0 mt-0.5">&gt;</span>
            {{ rec.recommendation }}
          </p>

          <!-- Evidence Chain -->
          <div v-if="rec.evidence_chain?.length" class="mt-2 space-y-1">
            <div
              v-for="(ev, ei) in rec.evidence_chain"
              :key="ei"
              class="text-xs pl-3 border-l border-gray-600"
            >
              <span class="text-gray-400">{{ ev.participant_name }} (R{{ ev.round }}):</span>
              <span class="text-gray-500 ml-1">{{ ev.evidence }}</span>
            </div>
          </div>

          <!-- Supporting Agents -->
          <div v-if="rec.supporting_agents?.length" class="mt-2 flex flex-wrap gap-2">
            <button
              v-for="(agent, ai) in rec.supporting_agents"
              :key="ai"
              class="flex items-center gap-1 px-2 py-1 bg-gray-700/50 rounded hover:bg-gray-600/50 transition-colors"
              @click="emit('selectAgent', agent.agent_id)"
            >
              <span class="text-xs text-gray-300">{{ agent.occupation }}, {{ agent.age }}歳</span>
              <span class="text-xs text-gray-500">{{ agent.region }}</span>
            </button>
          </div>
        </div>
      </div>
    </section>

    <!-- Stance Shifts -->
    <section v-if="narrative.stance_shifts?.length > 0">
      <h3 class="text-xs font-semibold text-yellow-400 uppercase tracking-wider mb-3">Stance Shifts</h3>
      <div class="space-y-2">
        <div
          v-for="(shift, idx) in narrative.stance_shifts"
          :key="idx"
          class="flex items-center gap-3 bg-gray-800/40 rounded-lg px-4 py-2.5"
        >
          <span class="text-sm text-gray-300">{{ shift.participant }}</span>
          <span :class="[getStanceClass(shift.from || shift.initial_position || ''), 'text-xs px-1.5 py-0.5 rounded']">
            {{ shift.from || shift.initial_position }}
          </span>
          <span class="text-gray-600">&rarr;</span>
          <span :class="[getStanceClass(shift.to || shift.final_position || ''), 'text-xs px-1.5 py-0.5 rounded']">
            {{ shift.to || shift.final_position }}
          </span>
          <span v-if="shift.reason" class="text-xs text-gray-500 ml-auto">{{ shift.reason }}</span>
        </div>
      </div>
    </section>
  </div>

  <!-- Empty state -->
  <div v-else class="text-center py-12 text-gray-500">
    <p class="text-sm">Narrative data is not yet available.</p>
    <p class="text-xs mt-1">Run a Society simulation to generate findings.</p>
  </div>
</template>
