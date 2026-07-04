<script setup lang="ts">
import { computed, onMounted, onUnmounted, ref } from 'vue'
import { getStanceColor } from '../constants/stances'

interface OpinionBubble {
  agent_id?: string
  stance?: string
  reason: string
}

const props = defineProps<{
  opinions: OpinionBubble[]
}>()

const offset = ref(0)
const pinnedIndex = ref<number | null>(null)
let timer: ReturnType<typeof window.setInterval> | null = null

const capped = computed(() => props.opinions.slice(0, 5))
const visible = computed(() => {
  if (pinnedIndex.value !== null) {
    return capped.value[pinnedIndex.value] ? [capped.value[pinnedIndex.value]] : []
  }
  if (capped.value.length <= 3) return capped.value
  return [0, 1, 2].map((i) => capped.value[(offset.value + i) % capped.value.length])
})

function togglePin(opinion: OpinionBubble) {
  const index = capped.value.indexOf(opinion)
  pinnedIndex.value = pinnedIndex.value === index ? null : index
}

onMounted(() => {
  timer = window.setInterval(() => {
    if (pinnedIndex.value === null && capped.value.length > 3) {
      offset.value = (offset.value + 1) % capped.value.length
    }
  }, 3000)
})

onUnmounted(() => {
  if (timer) window.clearInterval(timer)
})
</script>

<template>
  <div v-if="visible.length > 0" class="opinion-bubbles">
    <button
      v-for="opinion in visible"
      :key="`${opinion.agent_id || opinion.reason}`"
      class="opinion-bubble"
      type="button"
      :style="{ borderColor: getStanceColor(opinion.stance, 'var(--accent)') }"
      @click="togglePin(opinion)"
    >
      <span class="bubble-stance">{{ opinion.stance || '意見' }}</span>
      <span class="bubble-text">{{ opinion.reason }}</span>
    </button>
  </div>
</template>

<style scoped>
.opinion-bubbles {
  position: absolute;
  left: 1rem;
  top: 5.25rem;
  display: grid;
  gap: 0.6rem;
  width: min(22rem, calc(100% - 2rem));
  z-index: 8;
  pointer-events: none;
}

.opinion-bubble {
  pointer-events: auto;
  display: grid;
  gap: 0.25rem;
  text-align: left;
  color: var(--text-primary);
  background: rgba(10, 10, 15, 0.78);
  border: 1px solid var(--border-active);
  border-radius: var(--radius);
  padding: 0.7rem 0.8rem;
  box-shadow: var(--shadow);
  backdrop-filter: blur(12px);
  cursor: pointer;
}

.bubble-stance {
  font-size: 0.7rem;
  color: var(--text-secondary);
}

.bubble-text {
  font-size: 0.78rem;
  line-height: 1.45;
}
</style>
