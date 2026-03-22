<script setup lang="ts">
import type { ConversationRound, MeetingParticipant, MeetingSynthesis } from '../api/client'

const props = defineProps<{
  rounds: ConversationRound[]
  participants: MeetingParticipant[]
  synthesis: MeetingSynthesis | null
}>()

const emit = defineEmits<{
  selectAgent: [agentId: string]
}>()

const roundNames = ['初期主張', '相互質疑・反論', '最終立場表明']

function getParticipantColor(role: string): string {
  return role === 'expert' ? 'border-purple-500' : 'border-cyan-500'
}

function getRoleBadge(role: string): string {
  return role === 'expert' ? '専門家' : '市民代表'
}
</script>

<template>
  <div class="space-y-6">
    <!-- Participants -->
    <section v-if="participants.length > 0">
      <h4 class="text-xs font-semibold text-gray-400 uppercase tracking-wider mb-3">
        Participants ({{ participants.length }})
      </h4>
      <div class="flex flex-wrap gap-2">
        <button
          v-for="(p, idx) in participants"
          :key="idx"
          class="flex items-center gap-1.5 px-2.5 py-1.5 bg-gray-800 rounded-lg hover:bg-gray-700 transition-colors"
          @click="p.agent_id && emit('selectAgent', p.agent_id)"
        >
          <span
            class="w-2 h-2 rounded-full"
            :class="p.role === 'expert' ? 'bg-purple-400' : 'bg-cyan-400'"
          />
          <span class="text-sm text-gray-300">{{ p.display_name || `参加者${idx + 1}` }}</span>
          <span v-if="p.stance" class="text-xs text-gray-500">{{ p.stance }}</span>
        </button>
      </div>
    </section>

    <!-- Rounds -->
    <section v-for="round in rounds" :key="round.round">
      <div class="flex items-center gap-2 mb-3">
        <span class="text-indigo-400 font-mono text-sm font-semibold">R{{ round.round }}</span>
        <span class="text-gray-300 text-sm">{{ roundNames[round.round - 1] || `Round ${round.round}` }}</span>
        <span class="text-gray-600 text-xs">({{ round.arguments.length }}発言)</span>
      </div>

      <div class="space-y-3 ml-4 border-l border-gray-700 pl-4">
        <div
          v-for="(arg, idx) in round.arguments"
          :key="idx"
          class="bg-gray-800/60 rounded-lg p-3 border-l-2"
          :class="getParticipantColor(arg.role)"
        >
          <div class="flex items-center gap-2 mb-1.5">
            <span class="text-white text-sm font-medium">{{ arg.participant_name }}</span>
            <span
              class="text-xs px-1.5 py-0.5 rounded"
              :class="arg.role === 'expert' ? 'bg-purple-900/50 text-purple-300' : 'bg-cyan-900/50 text-cyan-300'"
            >
              {{ getRoleBadge(arg.role) }}
            </span>
          </div>

          <div v-if="arg.position" class="text-xs text-gray-400 mb-1">
            立場: {{ arg.position }}
          </div>

          <p class="text-gray-300 text-sm leading-relaxed">{{ arg.argument }}</p>

          <p v-if="arg.evidence" class="text-gray-500 text-xs mt-2">
            根拠: {{ arg.evidence }}
          </p>

          <div v-if="arg.concerns?.length > 0" class="mt-2 flex flex-wrap gap-1">
            <span
              v-for="(concern, ci) in arg.concerns"
              :key="ci"
              class="text-xs px-1.5 py-0.5 bg-yellow-900/30 text-yellow-400/80 rounded"
            >
              {{ concern }}
            </span>
          </div>
        </div>
      </div>
    </section>

    <!-- Synthesis -->
    <section v-if="synthesis" class="border-t border-gray-700 pt-4">
      <h4 class="text-xs font-semibold text-gray-400 uppercase tracking-wider mb-3">Synthesis</h4>

      <div v-if="synthesis.overall_assessment" class="bg-gray-800 rounded-lg p-4 mb-4">
        <p class="text-gray-300 text-sm leading-relaxed">{{ synthesis.overall_assessment }}</p>
      </div>

      <div v-if="synthesis.consensus_points?.length" class="mb-3">
        <h5 class="text-xs text-green-400 font-semibold mb-1">合意点</h5>
        <ul class="space-y-1">
          <li
            v-for="(point, idx) in synthesis.consensus_points"
            :key="idx"
            class="text-sm text-gray-300 flex items-start gap-1.5"
          >
            <span class="text-green-500 mt-0.5 shrink-0">+</span>
            {{ point }}
          </li>
        </ul>
      </div>

      <div v-if="synthesis.recommendations?.length" class="mb-3">
        <h5 class="text-xs text-blue-400 font-semibold mb-1">提言</h5>
        <ul class="space-y-1">
          <li
            v-for="(rec, idx) in synthesis.recommendations"
            :key="idx"
            class="text-sm text-gray-300 flex items-start gap-1.5"
          >
            <span class="text-blue-500 mt-0.5 shrink-0">></span>
            {{ rec }}
          </li>
        </ul>
      </div>

      <div v-if="synthesis.stance_shifts?.length" class="mb-3">
        <h5 class="text-xs text-yellow-400 font-semibold mb-1">Stance Shifts</h5>
        <div class="space-y-1">
          <div
            v-for="(shift, idx) in synthesis.stance_shifts"
            :key="idx"
            class="text-sm text-gray-300 flex items-center gap-2"
          >
            <span class="text-gray-400">{{ shift.participant }}</span>
            <span class="text-red-400 text-xs">{{ shift.from }}</span>
            <span class="text-gray-600">&rarr;</span>
            <span class="text-green-400 text-xs">{{ shift.to }}</span>
          </div>
        </div>
      </div>
    </section>

    <!-- Empty state -->
    <div v-if="rounds.length === 0" class="text-center py-8 text-gray-500">
      <p>Meeting データがありません</p>
    </div>
  </div>
</template>
