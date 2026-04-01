<script setup lang="ts">
import { computed } from 'vue'

const props = defineProps<{
  mode?: string // ThinkingVisualMode: 'idle' | 'graphrag' | 'simulation' | 'swarm' | 'report' | 'society'
}>()

const CHARS = '01アイウエオカキクケコ'
const COLUMN_COUNT = 20
const MIN_CHARS = 15
const MAX_CHARS = 20

interface RainChar {
  char: string
  top: number
  opacity: number
}

interface RainColumn {
  left: number
  duration: number
  delay: number
  chars: RainChar[]
}

/**
 * Generate deterministic rain columns using a simple seeded PRNG.
 * The seed is fixed so the output is stable across renders.
 */
function seededRandom(seed: number): () => number {
  let s = seed
  return () => {
    s = (s * 16807 + 0) % 2147483647
    return (s - 1) / 2147483646
  }
}

const rainColumns = computed<RainColumn[]>(() => {
  const rng = seededRandom(42)
  const columns: RainColumn[] = []

  for (let i = 0; i < COLUMN_COUNT; i++) {
    const charCount = MIN_CHARS + Math.floor(rng() * (MAX_CHARS - MIN_CHARS + 1))
    const chars: RainChar[] = []

    for (let j = 0; j < charCount; j++) {
      chars.push({
        char: CHARS[Math.floor(rng() * CHARS.length)],
        top: (j / charCount) * 100,
        opacity: 0.08 + rng() * 0.07,
      })
    }

    columns.push({
      left: rng() * 100,
      duration: 8 + rng() * 7,
      delay: rng() * 10,
      chars,
    })
  }

  return columns
})

const containerClass = computed(() => props.mode ? `mode-${props.mode}` : 'mode-idle')
</script>

<template>
  <div class="digital-workspace-bg" :class="containerClass" data-testid="digital-workspace-bg">
    <!-- Layer 1: Data Rain -->
    <div class="data-rain" data-testid="data-rain">
      <div
        v-for="(col, ci) in rainColumns"
        :key="ci"
        class="rain-column"
        :style="{
          left: `${col.left}%`,
          animationDuration: `${col.duration}s`,
          animationDelay: `${col.delay}s`,
        }"
      >
        <span
          v-for="(ch, chi) in col.chars"
          :key="chi"
          class="rain-char"
          :style="{ top: `${ch.top}%`, opacity: ch.opacity }"
        >{{ ch.char }}</span>
      </div>
    </div>

    <!-- Layer 2: Scan Line -->
    <div class="scan-line-layer" data-testid="scan-line" />

    <!-- Layer 3: Pulse Grid -->
    <div class="grid-pulse" data-testid="grid-pulse" />
  </div>
</template>

<style scoped>
.digital-workspace-bg {
  position: absolute;
  inset: 0;
  overflow: hidden;
  pointer-events: none;
  border-radius: inherit;
}

/* --- Layer 1: Data Rain --- */
.data-rain {
  position: absolute;
  inset: 0;
}

.rain-column {
  position: absolute;
  top: 0;
  width: 1ch;
  height: 100%;
  animation: rain-fall 10s linear infinite;
  font-family: monospace;
  font-size: 0.7rem;
  color: var(--accent, #3b82f6);
}

.rain-char {
  position: absolute;
  left: 0;
  user-select: none;
}

@keyframes rain-fall {
  from {
    transform: translateY(-100%);
  }
  to {
    transform: translateY(100%);
  }
}

/* --- Layer 2: Scan Line --- */
.scan-line-layer {
  position: absolute;
  inset: 0;
}

.scan-line-layer::after {
  content: '';
  position: absolute;
  left: 0;
  width: 100%;
  height: 2px;
  background: linear-gradient(90deg, transparent, rgba(59, 130, 246, 0.3), transparent);
  animation: scan-sweep 6s linear infinite;
}

@keyframes scan-sweep {
  from {
    top: -2px;
  }
  to {
    top: 100%;
  }
}

/* --- Layer 3: Pulse Grid --- */
.grid-pulse {
  position: absolute;
  inset: 0;
  background-image:
    repeating-linear-gradient(0deg, rgba(59, 130, 246, 0.04) 0px, transparent 1px),
    repeating-linear-gradient(90deg, rgba(59, 130, 246, 0.04) 0px, transparent 1px);
  background-size: 40px 40px;
  animation: grid-pulse 4s ease-in-out infinite;
}

@keyframes grid-pulse {
  0%,
  100% {
    opacity: 0.3;
  }
  50% {
    opacity: 0.8;
  }
}

/* --- Mode variants --- */
.mode-society {
  --accent: #6366f1;
}
.mode-simulation {
  --accent: #3b82f6;
}
.mode-graphrag {
  --accent: #06b6d4;
}
.mode-swarm {
  --accent: #10b981;
}
.mode-report {
  --accent: #8b5cf6;
}
</style>
