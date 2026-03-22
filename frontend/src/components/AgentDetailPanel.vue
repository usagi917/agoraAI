<script setup lang="ts">
import { computed } from 'vue'
import type { AgentDetailResponse } from '../api/client'

const props = defineProps<{
  agent: AgentDetailResponse | null
  loading?: boolean
}>()

const emit = defineEmits<{
  close: []
  selectAgent: [agentId: string]
}>()

const bigFiveLabels: Record<string, string> = {
  O: '開放性',
  C: '誠実性',
  E: '外向性',
  A: '協調性',
  N: '神経症傾向',
}

const stanceColorClass = computed(() => {
  const stance = props.agent?.activation_response?.stance
  if (!stance) return 'bg-gray-600'
  const map: Record<string, string> = {
    '賛成': 'bg-green-500',
    '条件付き賛成': 'bg-green-300',
    '中立': 'bg-gray-400',
    '条件付き反対': 'bg-red-300',
    '反対': 'bg-red-500',
  }
  return map[stance] || 'bg-gray-600'
})

const bigFiveEntries = computed(() => {
  if (!props.agent?.big_five) return []
  return Object.entries(props.agent.big_five).map(([key, value]) => ({
    key,
    label: bigFiveLabels[key] || key,
    value: (value as number) || 0,
    percent: Math.round(((value as number) || 0) * 100),
  }))
})
</script>

<template>
  <div
    v-if="agent"
    class="fixed right-0 top-0 h-full w-96 bg-gray-900/95 border-l border-gray-700 z-50 overflow-y-auto backdrop-blur-sm"
  >
    <!-- Header -->
    <div class="sticky top-0 bg-gray-900/90 backdrop-blur-sm border-b border-gray-700 p-4 flex items-center justify-between">
      <h3 class="text-lg font-semibold text-white">
        {{ agent.demographics?.occupation || '不明' }}
      </h3>
      <button
        class="text-gray-400 hover:text-white transition-colors"
        @click="emit('close')"
      >
        <span class="text-xl">&times;</span>
      </button>
    </div>

    <div class="p-4 space-y-5">
      <!-- Demographics -->
      <section>
        <h4 class="text-xs font-semibold text-gray-400 uppercase tracking-wider mb-2">Profile</h4>
        <div class="grid grid-cols-2 gap-2 text-sm">
          <div class="bg-gray-800 rounded px-3 py-2">
            <span class="text-gray-400 text-xs">年齢</span>
            <p class="text-white">{{ agent.demographics?.age || '?' }}歳</p>
          </div>
          <div class="bg-gray-800 rounded px-3 py-2">
            <span class="text-gray-400 text-xs">性別</span>
            <p class="text-white">{{ agent.demographics?.gender || '?' }}</p>
          </div>
          <div class="bg-gray-800 rounded px-3 py-2">
            <span class="text-gray-400 text-xs">職業</span>
            <p class="text-white">{{ agent.demographics?.occupation || '?' }}</p>
          </div>
          <div class="bg-gray-800 rounded px-3 py-2">
            <span class="text-gray-400 text-xs">地域</span>
            <p class="text-white">{{ agent.demographics?.region || '?' }}</p>
          </div>
          <div class="bg-gray-800 rounded px-3 py-2">
            <span class="text-gray-400 text-xs">学歴</span>
            <p class="text-white">{{ agent.demographics?.education || '?' }}</p>
          </div>
          <div class="bg-gray-800 rounded px-3 py-2">
            <span class="text-gray-400 text-xs">収入</span>
            <p class="text-white">{{ agent.demographics?.income_bracket || '?' }}</p>
          </div>
        </div>
      </section>

      <!-- Big Five -->
      <section v-if="bigFiveEntries.length > 0">
        <h4 class="text-xs font-semibold text-gray-400 uppercase tracking-wider mb-2">Big Five</h4>
        <div class="space-y-2">
          <div v-for="trait in bigFiveEntries" :key="trait.key" class="flex items-center gap-2 text-sm">
            <span class="text-gray-300 w-20 text-xs">{{ trait.label }}</span>
            <div class="flex-1 bg-gray-800 rounded-full h-2">
              <div
                class="h-2 rounded-full bg-indigo-500 transition-all"
                :style="{ width: `${trait.percent}%` }"
              />
            </div>
            <span class="text-gray-400 text-xs w-8 text-right">{{ trait.percent }}%</span>
          </div>
        </div>
      </section>

      <!-- Values -->
      <section v-if="agent.values && Object.keys(agent.values).length > 0">
        <h4 class="text-xs font-semibold text-gray-400 uppercase tracking-wider mb-2">Values</h4>
        <div class="flex flex-wrap gap-1">
          <span
            v-for="(_, value) in agent.values"
            :key="String(value)"
            class="px-2 py-0.5 bg-indigo-900/50 text-indigo-300 text-xs rounded-full border border-indigo-700/50"
          >
            {{ value }}
          </span>
        </div>
      </section>

      <!-- Activation Response -->
      <section v-if="agent.activation_response">
        <h4 class="text-xs font-semibold text-gray-400 uppercase tracking-wider mb-2">Activation</h4>
        <div class="bg-gray-800 rounded-lg p-3 space-y-2">
          <div class="flex items-center gap-2">
            <span :class="[stanceColorClass, 'px-2 py-0.5 rounded text-xs text-white font-medium']">
              {{ agent.activation_response.stance }}
            </span>
            <span class="text-gray-400 text-xs">
              信頼度: {{ Math.round((agent.activation_response.confidence || 0) * 100) }}%
            </span>
          </div>
          <p v-if="agent.activation_response.reason" class="text-gray-300 text-sm leading-relaxed">
            {{ agent.activation_response.reason }}
          </p>
          <p v-if="agent.activation_response.concern" class="text-yellow-400/80 text-xs mt-1">
            懸念: {{ agent.activation_response.concern }}
          </p>
          <p v-if="agent.activation_response.priority" class="text-blue-400/80 text-xs">
            優先: {{ agent.activation_response.priority }}
          </p>
        </div>
      </section>

      <!-- Meeting Contributions -->
      <section v-if="agent.meeting_contributions?.length > 0">
        <h4 class="text-xs font-semibold text-gray-400 uppercase tracking-wider mb-2">
          Meeting ({{ agent.meeting_contributions.length }}発言)
        </h4>
        <div class="space-y-2">
          <div
            v-for="(contrib, idx) in agent.meeting_contributions"
            :key="idx"
            class="bg-gray-800 rounded-lg p-3 border-l-2 border-indigo-500"
          >
            <div class="flex items-center gap-2 mb-1">
              <span class="text-indigo-400 text-xs font-medium">R{{ contrib.round }}</span>
              <span class="text-gray-400 text-xs">{{ contrib.position }}</span>
            </div>
            <p class="text-gray-300 text-sm">{{ contrib.argument }}</p>
            <p v-if="contrib.evidence" class="text-gray-500 text-xs mt-1">
              根拠: {{ contrib.evidence }}
            </p>
          </div>
        </div>
      </section>

      <!-- Connections -->
      <section v-if="agent.connections?.length > 0">
        <h4 class="text-xs font-semibold text-gray-400 uppercase tracking-wider mb-2">
          Connections ({{ agent.connections.length }})
        </h4>
        <div class="space-y-1 max-h-48 overflow-y-auto">
          <button
            v-for="conn in agent.connections"
            :key="conn.id"
            class="w-full flex items-center gap-2 px-3 py-2 bg-gray-800 rounded hover:bg-gray-700 transition-colors text-left"
            @click="emit('selectAgent', conn.connected_to)"
          >
            <span class="text-xs text-gray-400">{{ conn.relation_type }}</span>
            <div class="flex-1 bg-gray-700 rounded-full h-1.5">
              <div
                class="h-1.5 rounded-full bg-cyan-500"
                :style="{ width: `${Math.round(conn.strength * 100)}%` }"
              />
            </div>
            <span class="text-xs text-gray-500">{{ Math.round(conn.strength * 100) }}%</span>
          </button>
        </div>
      </section>

      <!-- Extra Info -->
      <section v-if="agent.speech_style || agent.life_event">
        <h4 class="text-xs font-semibold text-gray-400 uppercase tracking-wider mb-2">Background</h4>
        <div class="space-y-1 text-xs text-gray-400">
          <p v-if="agent.speech_style">
            <span class="text-gray-500">発話: </span>{{ agent.speech_style }}
          </p>
          <p v-if="agent.life_event">
            <span class="text-gray-500">経験: </span>{{ agent.life_event }}
          </p>
          <p v-if="agent.information_source">
            <span class="text-gray-500">情報源: </span>{{ agent.information_source }}
          </p>
        </div>
      </section>
    </div>
  </div>
</template>
