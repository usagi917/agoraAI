<script setup lang="ts">
import { ref, computed, watch, nextTick } from 'vue'
import { useSocietyGraphStore, type MeetingArgument } from '../stores/societyGraphStore'
import { useAgentVisualizationStore, type CommunicationFlow } from '../stores/agentVisualizationStore'

interface DialogueItem {
  id: string
  speaker: string
  role: 'expert' | 'citizen' | null
  roleLabel: string
  content: string
  align: 'left' | 'right'
  stanceClass: 'agree' | 'disagree' | 'neutral'
  confidence: number | null
  timestamp: number
}

interface StanceShiftDisplay {
  id: string
  agent: string
  from: string
  to: string
}

const societyGraphStore = useSocietyGraphStore()
const vizStore = useAgentVisualizationStore()
const messagesRef = ref<HTMLElement | null>(null)

function deriveRole(role: string): 'expert' | 'citizen' | null {
  if (!role) return null
  const lower = role.toLowerCase()
  if (lower.includes('expert') || lower.includes('専門')) return 'expert'
  if (lower.includes('citizen') || lower.includes('市民')) return 'citizen'
  return null
}

function deriveRoleLabel(role: 'expert' | 'citizen' | null): string {
  if (role === 'expert') return '専門家'
  if (role === 'citizen') return '市民代表'
  return ''
}

function deriveStanceClass(position?: string): 'agree' | 'disagree' | 'neutral' {
  if (!position) return 'neutral'
  const lower = position.toLowerCase()
  if (lower.includes('賛成') || lower.includes('agree') || lower.includes('support')) return 'agree'
  if (lower.includes('反対') || lower.includes('disagree') || lower.includes('oppose')) return 'disagree'
  return 'neutral'
}

const dialogueItems = computed<DialogueItem[]>(() => {
  const items: DialogueItem[] = []

  // Merge meeting arguments
  societyGraphStore.currentArguments.forEach((arg: MeetingArgument, idx: number) => {
    const role = deriveRole(arg.role)
    items.push({
      id: `arg-${idx}-${arg.participant_index}`,
      speaker: arg.participant_name,
      role,
      roleLabel: deriveRoleLabel(role),
      content: arg.argument,
      align: idx % 2 === 0 ? 'left' : 'right',
      stanceClass: deriveStanceClass(arg.position),
      confidence: null,
      timestamp: idx,
    })
  })

  // Merge conversation-type communication flows
  const conversationFlows = vizStore.communicationFlows.filter(
    (f: CommunicationFlow) => f.messageType === 'conversation',
  )
  conversationFlows.forEach((flow: CommunicationFlow, idx: number) => {
    const globalIdx = items.length
    items.push({
      id: `flow-${idx}-${flow.sourceId}-${flow.timestamp}`,
      speaker: flow.sourceId,
      role: null,
      roleLabel: '',
      content: flow.content,
      align: globalIdx % 2 === 0 ? 'left' : 'right',
      stanceClass: 'neutral',
      confidence: null,
      timestamp: flow.timestamp,
    })
  })

  return items
})

const stanceShifts = computed<StanceShiftDisplay[]>(() => {
  return societyGraphStore.pendingStanceShifts.map((shift, idx) => ({
    id: `shift-${idx}-${shift.agentId}`,
    agent: shift.agentId,
    from: shift.fromStance,
    to: shift.toStance,
  }))
})

watch(
  () => dialogueItems.value.length,
  async () => {
    await nextTick()
    messagesRef.value?.scrollTo({
      top: messagesRef.value.scrollHeight,
      behavior: 'smooth',
    })
  },
)
</script>

<template>
  <div class="dialogue-stream">
    <div class="dialogue-messages" ref="messagesRef">
      <!-- Meeting arguments as chat bubbles -->
      <TransitionGroup name="chat-msg">
        <div
          v-for="item in dialogueItems"
          :key="item.id"
          :class="['dialogue-bubble', item.align, `stance-${item.stanceClass}`]"
        >
          <div class="bubble-header">
            <span class="bubble-speaker">{{ item.speaker }}</span>
            <span v-if="item.role" class="bubble-role">{{ item.roleLabel }}</span>
          </div>
          <div class="bubble-content">{{ item.content }}</div>
          <div v-if="item.confidence != null" class="bubble-confidence">
            <div class="confidence-bar" :style="{ width: `${item.confidence * 100}%` }" />
          </div>
        </div>
      </TransitionGroup>

      <!-- Stance shifts as system messages -->
      <div v-for="shift in stanceShifts" :key="shift.id" class="system-message">
        <span class="shift-arrow">{{ shift.agent }} : {{ shift.from }} → {{ shift.to }}</span>
      </div>
    </div>

    <!-- Empty state -->
    <div v-if="dialogueItems.length === 0" class="dialogue-empty">
      対話データを待機中...
    </div>
  </div>
</template>

<style scoped>
.dialogue-stream {
  display: flex;
  flex-direction: column;
  height: 100%;
  overflow: hidden;
}

.dialogue-messages {
  flex: 1;
  overflow-y: auto;
  display: flex;
  flex-direction: column;
  gap: 0.5rem;
  padding: 0.5rem;
}

.dialogue-bubble {
  max-width: 85%;
  padding: 0.5rem 0.75rem;
  background: var(--bg-elevated);
  border-radius: 8px 8px 8px 2px;
  border-left: 3px solid var(--accent);
  font-size: 0.75rem;
}

.dialogue-bubble.right {
  align-self: flex-end;
  border-radius: 8px 8px 2px 8px;
  border-left: none;
  border-right: 3px solid var(--accent);
}

.dialogue-bubble.stance-agree {
  border-left-color: #22c55e;
}
.dialogue-bubble.stance-agree.right {
  border-left-color: transparent;
  border-right-color: #22c55e;
}

.dialogue-bubble.stance-disagree {
  border-left-color: #ef4444;
}
.dialogue-bubble.stance-disagree.right {
  border-left-color: transparent;
  border-right-color: #ef4444;
}

.dialogue-bubble.stance-neutral {
  border-left-color: #a3a3a3;
}
.dialogue-bubble.stance-neutral.right {
  border-left-color: transparent;
  border-right-color: #a3a3a3;
}

.bubble-header {
  display: flex;
  align-items: center;
  gap: 0.4rem;
  margin-bottom: 0.25rem;
}

.bubble-speaker {
  font-weight: 600;
  font-size: 0.72rem;
  color: var(--text-primary);
}

.bubble-role {
  font-size: 0.6rem;
  padding: 0.1rem 0.3rem;
  border-radius: 3px;
  background: rgba(59, 130, 246, 0.15);
  color: var(--accent);
}

.bubble-content {
  color: var(--text-secondary);
  line-height: 1.5;
}

.confidence-bar {
  height: 2px;
  background: var(--accent);
  border-radius: 1px;
  margin-top: 0.4rem;
  transition: width 0.3s ease;
}

.system-message {
  text-align: center;
  font-size: 0.65rem;
  color: var(--text-muted);
  padding: 0.25rem;
  border-top: 1px solid var(--border);
  border-bottom: 1px solid var(--border);
}

.dialogue-empty {
  display: flex;
  align-items: center;
  justify-content: center;
  min-height: 8rem;
  color: var(--text-muted);
  font-size: 0.75rem;
}

/* Transition */
.chat-msg-enter-active { transition: all 0.3s ease-out; }
.chat-msg-enter-from { opacity: 0; transform: translateY(10px); }
.chat-msg-leave-active { transition: all 0.2s ease-in; }
.chat-msg-leave-to { opacity: 0; }
</style>
