<script setup lang="ts">
import { ref, watch, onUnmounted, computed } from 'vue'
import type { MeetingArgument } from '../stores/societyGraphStore'

const props = defineProps<{
  arguments: MeetingArgument[]
  round: number
}>()

const currentIndex = ref(0)
let advanceTimer: ReturnType<typeof setInterval> | null = null

const currentArg = computed(() =>
  props.arguments.length > 0 ? props.arguments[currentIndex.value] : null,
)

const isDevilAdvocate = computed(() => {
  if (!currentArg.value) return false
  return currentArg.value.is_devil_advocate || currentArg.value.role === 'devil_advocate'
})

const displayText = computed(() => {
  if (!currentArg.value) return ''
  const text = currentArg.value.argument
  return text.length > 150 ? text.slice(0, 147) + '...' : text
})

const roleLabel = computed(() => {
  if (!currentArg.value) return 'Participant'
  if (isDevilAdvocate.value) return "Devil's Advocate"
  if (currentArg.value.role === 'expert') return 'Expert'
  if (currentArg.value.role === 'citizen_representative') return 'Citizen'
  return currentArg.value.role || 'Participant'
})

function startAutoAdvance() {
  stopAutoAdvance()
  if (props.arguments.length <= 1) return
  advanceTimer = setInterval(() => {
    currentIndex.value = (currentIndex.value + 1) % props.arguments.length
  }, 4000)
}

function stopAutoAdvance() {
  if (advanceTimer) {
    clearInterval(advanceTimer)
    advanceTimer = null
  }
}

watch(
  () => props.arguments,
  () => {
    currentIndex.value = 0
    startAutoAdvance()
  },
  { immediate: true },
)

onUnmounted(() => {
  stopAutoAdvance()
})
</script>

<template>
  <Transition name="toast-slide">
    <div v-if="currentArg" class="conversation-toast" :key="`${round}-${currentIndex}`">
      <div class="toast-header">
        <span class="speaker-name">{{ currentArg.participant_name }}</span>
        <span
          class="role-badge"
          :class="{ 'role-badge-devil': isDevilAdvocate }"
        >
          {{ roleLabel }}
        </span>
        <span class="round-badge">Round {{ round }}</span>
        <span v-if="arguments.length > 1" class="toast-counter">
          {{ currentIndex + 1 }}/{{ arguments.length }}
        </span>
      </div>
      <p class="toast-text">{{ displayText }}</p>
    </div>
  </Transition>
</template>

<style scoped>
.conversation-toast {
  position: absolute;
  bottom: 1rem;
  left: 50%;
  transform: translateX(-50%);
  max-width: min(90%, 32rem);
  padding: 0.75rem 1rem;
  background: rgba(16, 16, 30, 0.92);
  backdrop-filter: blur(12px);
  border: 1px solid rgba(255, 215, 64, 0.25);
  border-radius: 12px;
  z-index: 10;
  pointer-events: auto;
}

.toast-header {
  display: flex;
  align-items: center;
  gap: 0.5rem;
  margin-bottom: 0.4rem;
  flex-wrap: wrap;
}

.speaker-name {
  font-weight: 600;
  font-size: 0.8rem;
  color: #ffd740;
}

.role-badge {
  font-size: 0.65rem;
  padding: 0.1rem 0.4rem;
  background: rgba(255, 215, 64, 0.15);
  border: 1px solid rgba(255, 215, 64, 0.3);
  border-radius: 4px;
  color: rgba(255, 215, 64, 0.8);
  text-transform: uppercase;
  letter-spacing: 0.03em;
}

.role-badge-devil {
  background: rgba(239, 68, 68, 0.18);
  border-color: rgba(239, 68, 68, 0.4);
  color: rgba(239, 100, 100, 0.9);
}

.round-badge {
  font-size: 0.65rem;
  padding: 0.1rem 0.4rem;
  background: rgba(100, 100, 255, 0.15);
  border: 1px solid rgba(100, 100, 255, 0.3);
  border-radius: 4px;
  color: rgba(150, 150, 255, 0.8);
}

.toast-counter {
  font-size: 0.65rem;
  color: rgba(255, 255, 255, 0.4);
  margin-left: auto;
}

.toast-text {
  font-size: 0.78rem;
  line-height: 1.5;
  color: rgba(230, 230, 240, 0.9);
  margin: 0;
}

.toast-slide-enter-active {
  transition: all 0.35s cubic-bezier(0.16, 1, 0.3, 1);
}
.toast-slide-leave-active {
  transition: all 0.25s ease-in;
}
.toast-slide-enter-from {
  opacity: 0;
  transform: translateX(-50%) translateY(12px);
}
.toast-slide-leave-to {
  opacity: 0;
  transform: translateX(-50%) translateY(-8px);
}
</style>
