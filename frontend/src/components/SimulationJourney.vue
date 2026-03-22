<script setup lang="ts">
import { ref, computed } from 'vue'
import { useSocietyStore } from '../stores/societyStore'
import DemographicBreakdown from './DemographicBreakdown.vue'

const props = defineProps<{
  simulationId: string
  societyResult: Record<string, any> | null
}>()

const emit = defineEmits<{
  selectAgent: [agentId: string]
}>()

const societyStore = useSocietyStore()
const activePhase = ref<'population' | 'selection' | 'activation' | 'meeting' | 'insights'>('activation')

const phases = [
  { id: 'population' as const, label: 'Population', icon: '1' },
  { id: 'selection' as const, label: 'Selection', icon: '2' },
  { id: 'activation' as const, label: 'Activation', icon: '3' },
  { id: 'meeting' as const, label: 'Meeting', icon: '4' },
  { id: 'insights' as const, label: 'Insights', icon: '5' },
]

const populationCount = computed(() => props.societyResult?.population_count || 0)
const selectedCount = computed(() => props.societyResult?.selected_count || 0)
const stanceDist = computed(() => props.societyResult?.aggregation?.stance_distribution || {})
const avgConfidence = computed(() => props.societyResult?.aggregation?.average_confidence || 0)
const topConcerns = computed(() => props.societyResult?.aggregation?.top_concerns || [])
const topPriorities = computed(() => props.societyResult?.aggregation?.top_priorities || [])
const evaluation = computed(() => props.societyResult?.evaluation || {})

const stanceColors: Record<string, string> = {
  '賛成': 'bg-green-500',
  '条件付き賛成': 'bg-green-300',
  '中立': 'bg-gray-400',
  '条件付き反対': 'bg-red-300',
  '反対': 'bg-red-500',
}

// Meeting synthesis
const synthesis = computed(() => societyStore.meetingSynthesis)
</script>

<template>
  <div>
    <!-- Phase Stepper -->
    <div class="flex items-center gap-1 mb-6 px-2">
      <template v-for="(phase, idx) in phases" :key="phase.id">
        <button
          class="flex items-center gap-1.5 px-3 py-1.5 rounded-lg text-xs font-medium transition-all"
          :class="
            activePhase === phase.id
              ? 'bg-indigo-600 text-white'
              : 'bg-gray-800 text-gray-400 hover:bg-gray-700 hover:text-gray-300'
          "
          @click="activePhase = phase.id"
        >
          <span class="w-4 h-4 rounded-full text-[10px] flex items-center justify-center" :class="activePhase === phase.id ? 'bg-indigo-400' : 'bg-gray-700'">
            {{ phase.icon }}
          </span>
          {{ phase.label }}
        </button>
        <span v-if="idx < phases.length - 1" class="text-gray-700">&rarr;</span>
      </template>
    </div>

    <!-- Population Phase -->
    <div v-if="activePhase === 'population'" class="space-y-4">
      <h3 class="text-base font-semibold text-white">Population Overview</h3>
      <div class="grid grid-cols-3 gap-3">
        <div class="bg-gray-800 rounded-lg p-4 text-center">
          <div class="text-2xl font-bold text-white">{{ populationCount.toLocaleString() }}</div>
          <div class="text-xs text-gray-400 mt-1">Total Population</div>
        </div>
        <div class="bg-gray-800 rounded-lg p-4 text-center">
          <div class="text-2xl font-bold text-indigo-400">{{ selectedCount }}</div>
          <div class="text-xs text-gray-400 mt-1">Selected</div>
        </div>
        <div class="bg-gray-800 rounded-lg p-4 text-center">
          <div class="text-2xl font-bold text-cyan-400">{{ societyStore.meetingParticipants.length }}</div>
          <div class="text-xs text-gray-400 mt-1">Meeting Participants</div>
        </div>
      </div>

      <DemographicBreakdown
        v-if="societyStore.agentList.length > 0"
        :agents="societyStore.agentList"
      />
    </div>

    <!-- Selection Phase -->
    <div v-if="activePhase === 'selection'" class="space-y-4">
      <h3 class="text-base font-semibold text-white">Agent Selection</h3>
      <p class="text-sm text-gray-400">
        {{ populationCount.toLocaleString() }} people &rarr; {{ selectedCount }} selected based on theme relevance
      </p>
      <div v-if="societyStore.agentList.length > 0" class="grid grid-cols-2 sm:grid-cols-3 md:grid-cols-4 gap-2 max-h-96 overflow-y-auto">
        <button
          v-for="agent in societyStore.agentList.slice(0, 40)"
          :key="agent.id"
          class="bg-gray-800 rounded-lg p-2.5 text-left hover:bg-gray-700 transition-colors"
          @click="emit('selectAgent', agent.id)"
        >
          <div class="text-xs text-white font-medium truncate">{{ agent.demographics?.occupation || '?' }}</div>
          <div class="text-xs text-gray-500">{{ agent.demographics?.age || '?' }}歳 / {{ agent.demographics?.region || '?' }}</div>
          <span
            v-if="agent.stance"
            class="inline-block mt-1 px-1.5 py-0.5 rounded text-[10px] text-white"
            :class="stanceColors[agent.stance] || 'bg-gray-600'"
          >
            {{ agent.stance }}
          </span>
        </button>
      </div>
    </div>

    <!-- Activation Phase -->
    <div v-if="activePhase === 'activation'" class="space-y-4">
      <h3 class="text-base font-semibold text-white">Activation Results</h3>

      <!-- Stance Distribution -->
      <div class="bg-gray-800 rounded-lg p-4">
        <h4 class="text-xs text-gray-400 uppercase tracking-wider mb-3">Stance Distribution</h4>
        <div class="space-y-2">
          <div v-for="(ratio, stance) in stanceDist" :key="String(stance)" class="flex items-center gap-2">
            <span class="w-24 text-xs text-gray-300 text-right">{{ stance }}</span>
            <div class="flex-1 bg-gray-700 rounded-full h-4 overflow-hidden">
              <div
                class="h-full rounded-full transition-all"
                :class="stanceColors[String(stance)] || 'bg-gray-500'"
                :style="{ width: `${(Number(ratio) * 100)}%` }"
              />
            </div>
            <span class="w-12 text-xs text-gray-400 text-right">{{ (Number(ratio) * 100).toFixed(1) }}%</span>
          </div>
        </div>
        <div class="mt-3 text-xs text-gray-500">
          Avg Confidence: {{ (avgConfidence * 100).toFixed(1) }}%
        </div>
      </div>

      <!-- Concerns & Priorities -->
      <div class="grid grid-cols-2 gap-3">
        <div v-if="topConcerns.length" class="bg-gray-800 rounded-lg p-3">
          <h4 class="text-xs text-yellow-400 font-semibold mb-2">Top Concerns</h4>
          <ul class="space-y-1">
            <li v-for="c in topConcerns" :key="c" class="text-xs text-gray-300">{{ c }}</li>
          </ul>
        </div>
        <div v-if="topPriorities.length" class="bg-gray-800 rounded-lg p-3">
          <h4 class="text-xs text-blue-400 font-semibold mb-2">Top Priorities</h4>
          <ul class="space-y-1">
            <li v-for="p in topPriorities" :key="p" class="text-xs text-gray-300">{{ p }}</li>
          </ul>
        </div>
      </div>

      <!-- Demographic Breakdown -->
      <DemographicBreakdown
        v-if="societyStore.agentList.length > 0"
        :agents="societyStore.agentList"
      />
    </div>

    <!-- Meeting Phase -->
    <div v-if="activePhase === 'meeting'" class="space-y-4">
      <h3 class="text-base font-semibold text-white">Meeting Discussions</h3>

      <!-- Participants -->
      <div class="flex flex-wrap gap-2 mb-3">
        <button
          v-for="(p, idx) in societyStore.meetingParticipants"
          :key="idx"
          class="flex items-center gap-1.5 px-2.5 py-1.5 bg-gray-800 rounded-lg hover:bg-gray-700 transition-colors"
          @click="p.agent_id && emit('selectAgent', p.agent_id)"
        >
          <span
            class="w-2 h-2 rounded-full"
            :class="p.role === 'expert' ? 'bg-purple-400' : 'bg-cyan-400'"
          />
          <span class="text-xs text-gray-300">{{ p.display_name || `#${idx + 1}` }}</span>
        </button>
      </div>

      <!-- Round summaries -->
      <div v-for="round in societyStore.meetingRounds" :key="round.round" class="bg-gray-800 rounded-lg p-4">
        <div class="flex items-center gap-2 mb-2">
          <span class="text-indigo-400 font-mono text-sm font-semibold">R{{ round.round }}</span>
          <span class="text-gray-400 text-xs">{{ round.arguments.length }} arguments</span>
        </div>
        <div class="space-y-2">
          <div
            v-for="(arg, idx) in round.arguments.slice(0, 5)"
            :key="idx"
            class="text-sm pl-3 border-l-2"
            :class="arg.role === 'expert' ? 'border-purple-500' : 'border-cyan-500'"
          >
            <span class="text-gray-300 font-medium">{{ arg.participant_name }}:</span>
            <span class="text-gray-400 ml-1">{{ arg.position }}</span>
          </div>
          <p v-if="round.arguments.length > 5" class="text-xs text-gray-600 pl-3">
            +{{ round.arguments.length - 5 }} more...
          </p>
        </div>
      </div>
    </div>

    <!-- Insights Phase -->
    <div v-if="activePhase === 'insights'" class="space-y-4">
      <h3 class="text-base font-semibold text-white">Key Insights</h3>

      <!-- Synthesis -->
      <div v-if="synthesis" class="space-y-3">
        <div v-if="synthesis.overall_assessment" class="bg-gray-800 rounded-lg p-4">
          <h4 class="text-xs text-gray-400 uppercase tracking-wider mb-2">Overall Assessment</h4>
          <p class="text-sm text-gray-300 leading-relaxed">{{ synthesis.overall_assessment }}</p>
        </div>

        <div v-if="synthesis.consensus_points?.length" class="bg-gray-800 rounded-lg p-4">
          <h4 class="text-xs text-green-400 font-semibold mb-2">Consensus ({{ synthesis.consensus_points.length }})</h4>
          <ul class="space-y-1.5">
            <li v-for="(pt, idx) in synthesis.consensus_points" :key="idx" class="text-sm text-gray-300 flex items-start gap-2">
              <span class="text-green-500 shrink-0">+</span>
              {{ pt }}
            </li>
          </ul>
        </div>

        <div v-if="synthesis.recommendations?.length" class="bg-gray-800 rounded-lg p-4">
          <h4 class="text-xs text-blue-400 font-semibold mb-2">Recommendations</h4>
          <ul class="space-y-1.5">
            <li v-for="(rec, idx) in synthesis.recommendations" :key="idx" class="text-sm text-gray-300 flex items-start gap-2">
              <span class="text-blue-500 shrink-0">&gt;</span>
              {{ rec }}
            </li>
          </ul>
        </div>

        <div v-if="synthesis.key_insights?.length" class="bg-gray-800 rounded-lg p-4">
          <h4 class="text-xs text-indigo-400 font-semibold mb-2">Key Insights</h4>
          <ul class="space-y-1.5">
            <li v-for="(insight, idx) in synthesis.key_insights" :key="idx" class="text-sm text-gray-300 flex items-start gap-2">
              <span class="text-indigo-400 shrink-0">*</span>
              {{ insight }}
            </li>
          </ul>
        </div>
      </div>

      <!-- Evaluation Metrics -->
      <div v-if="Object.keys(evaluation).length" class="bg-gray-800 rounded-lg p-4">
        <h4 class="text-xs text-gray-400 uppercase tracking-wider mb-3">Evaluation Metrics</h4>
        <div class="grid grid-cols-3 gap-3">
          <div v-for="(score, metric) in evaluation" :key="String(metric)" class="text-center">
            <div class="text-lg font-bold text-white">{{ (Number(score) * 100).toFixed(0) }}%</div>
            <div class="text-xs text-gray-500">{{ metric }}</div>
          </div>
        </div>
      </div>
    </div>
  </div>
</template>
