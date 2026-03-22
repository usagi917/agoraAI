<script setup lang="ts">
import { ref, computed, watch, onMounted } from 'vue'
import { useSocietyStore } from '../stores/societyStore'
import { useForceGraph } from '../composables/useForceGraph'
import AgentDetailPanel from './AgentDetailPanel.vue'
import ConversationPanel from './ConversationPanel.vue'

const props = defineProps<{
  simulationId: string
}>()

const societyStore = useSocietyStore()
const graphContainer = ref<HTMLElement | null>(null)
const activeTab = ref<'graph' | 'conversation'>('graph')

const {
  graphError,
  setFullGraph,
  onNodeClick,
} = useForceGraph(graphContainer)

// Load data on mount
onMounted(async () => {
  if (societyStore.agentList.length === 0) {
    await societyStore.loadSocialGraph(props.simulationId)
    await societyStore.loadConversations(props.simulationId)
  }
  updateGraph()
})

// Update graph when filtered data changes
watch(
  () => [societyStore.graphNodes, societyStore.graphEdges],
  () => updateGraph(),
  { deep: true },
)

function updateGraph() {
  const nodes = societyStore.graphNodes
  const edges = societyStore.graphEdges
  if (nodes.length > 0) {
    setFullGraph(nodes, edges)
  }
}

// Node click handler
onNodeClick((nodeId: string) => {
  societyStore.loadAgentDetail(props.simulationId, nodeId)
})

function handleAgentSelect(agentId: string) {
  societyStore.loadAgentDetail(props.simulationId, agentId)
}

function handleClosePanel() {
  societyStore.clearSelection()
}

// Filter helpers
const stanceOptions = computed(() => [
  { value: null, label: 'All' },
  ...societyStore.uniqueStances.map((s) => ({ value: s, label: s })),
])

const regionOptions = computed(() => [
  { value: null, label: 'All' },
  ...societyStore.uniqueRegions.map((r) => ({ value: r, label: r })),
])

// Stats
const totalAgents = computed(() => societyStore.agentList.length)
const filteredCount = computed(() => societyStore.filteredAgents.length)
const edgeCount = computed(() => societyStore.socialEdges.length)
</script>

<template>
  <div class="flex flex-col h-full">
    <!-- Filter Bar -->
    <div class="flex items-center gap-3 px-4 py-2 bg-gray-800/50 border-b border-gray-700 text-sm flex-wrap">
      <div class="flex items-center gap-1.5">
        <span class="text-gray-400 text-xs">Stance:</span>
        <select
          class="bg-gray-700 text-gray-200 text-xs rounded px-2 py-1 border border-gray-600 focus:outline-none focus:border-indigo-500"
          :value="societyStore.filters.stance || ''"
          @change="societyStore.setFilter('stance', ($event.target as HTMLSelectElement).value || null)"
        >
          <option v-for="opt in stanceOptions" :key="String(opt.value)" :value="opt.value || ''">
            {{ opt.label }}
          </option>
        </select>
      </div>

      <div class="flex items-center gap-1.5">
        <span class="text-gray-400 text-xs">Region:</span>
        <select
          class="bg-gray-700 text-gray-200 text-xs rounded px-2 py-1 border border-gray-600 focus:outline-none focus:border-indigo-500"
          :value="societyStore.filters.region || ''"
          @change="societyStore.setFilter('region', ($event.target as HTMLSelectElement).value || null)"
        >
          <option v-for="opt in regionOptions" :key="String(opt.value)" :value="opt.value || ''">
            {{ opt.label }}
          </option>
        </select>
      </div>

      <button
        v-if="societyStore.filters.stance || societyStore.filters.region || societyStore.filters.occupation"
        class="text-xs text-indigo-400 hover:text-indigo-300 transition-colors"
        @click="societyStore.clearFilters()"
      >
        Clear
      </button>

      <div class="ml-auto flex items-center gap-3 text-xs text-gray-500">
        <span>{{ filteredCount }}/{{ totalAgents }} agents</span>
        <span>{{ edgeCount }} edges</span>
      </div>
    </div>

    <!-- Stance Legend -->
    <div class="flex items-center gap-3 px-4 py-1.5 bg-gray-800/30 text-xs">
      <span class="text-gray-500">Stance:</span>
      <span class="flex items-center gap-1">
        <span class="w-2.5 h-2.5 rounded-full bg-green-500" />
        <span class="text-gray-400">賛成</span>
      </span>
      <span class="flex items-center gap-1">
        <span class="w-2.5 h-2.5 rounded-full bg-green-300" />
        <span class="text-gray-400">条件付き賛成</span>
      </span>
      <span class="flex items-center gap-1">
        <span class="w-2.5 h-2.5 rounded-full bg-gray-400" />
        <span class="text-gray-400">中立</span>
      </span>
      <span class="flex items-center gap-1">
        <span class="w-2.5 h-2.5 rounded-full bg-red-300" />
        <span class="text-gray-400">条件付き反対</span>
      </span>
      <span class="flex items-center gap-1">
        <span class="w-2.5 h-2.5 rounded-full bg-red-500" />
        <span class="text-gray-400">反対</span>
      </span>
    </div>

    <!-- Tab Bar -->
    <div class="flex border-b border-gray-700">
      <button
        class="px-4 py-2 text-sm transition-colors"
        :class="activeTab === 'graph' ? 'text-indigo-400 border-b-2 border-indigo-400' : 'text-gray-400 hover:text-gray-300'"
        @click="activeTab = 'graph'"
      >
        People Graph
      </button>
      <button
        class="px-4 py-2 text-sm transition-colors"
        :class="activeTab === 'conversation' ? 'text-indigo-400 border-b-2 border-indigo-400' : 'text-gray-400 hover:text-gray-300'"
        @click="activeTab = 'conversation'"
      >
        Conversations
      </button>
    </div>

    <!-- Content -->
    <div class="flex-1 relative overflow-hidden">
      <!-- 3D Graph -->
      <div
        v-show="activeTab === 'graph'"
        ref="graphContainer"
        class="w-full h-full"
      />

      <div v-if="graphError" class="absolute inset-0 flex items-center justify-center text-red-400 text-sm">
        {{ graphError }}
      </div>

      <!-- Conversation View -->
      <div
        v-show="activeTab === 'conversation'"
        class="w-full h-full overflow-y-auto p-4"
      >
        <ConversationPanel
          :rounds="societyStore.meetingRounds"
          :participants="societyStore.meetingParticipants"
          :synthesis="societyStore.meetingSynthesis"
          @select-agent="handleAgentSelect"
        />
      </div>

      <!-- Loading -->
      <div
        v-if="societyStore.loading"
        class="absolute inset-0 flex items-center justify-center bg-gray-900/60 backdrop-blur-sm"
      >
        <div class="flex items-center gap-3 text-gray-300">
          <svg class="animate-spin h-5 w-5" viewBox="0 0 24 24">
            <circle class="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" stroke-width="4" fill="none" />
            <path class="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4zm2 5.291A7.962 7.962 0 014 12H0c0 3.042 1.135 5.824 3 7.938l3-2.647z" />
          </svg>
          <span class="text-sm">Loading social graph...</span>
        </div>
      </div>

      <!-- Empty state -->
      <div
        v-if="!societyStore.loading && totalAgents === 0 && activeTab === 'graph'"
        class="absolute inset-0 flex items-center justify-center text-gray-500 text-sm"
      >
        Society mode simulation data not available
      </div>
    </div>

    <!-- Agent Detail Panel -->
    <AgentDetailPanel
      :agent="societyStore.selectedAgentDetail"
      @close="handleClosePanel"
      @select-agent="handleAgentSelect"
    />
  </div>
</template>
