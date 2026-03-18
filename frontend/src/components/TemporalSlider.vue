<script setup lang="ts">
import { computed } from 'vue'

const props = defineProps<{
  totalRounds: number
  modelValue: number
  displayValue?: number
  playing?: boolean
}>()

const emit = defineEmits<{
  'update:modelValue': [value: number]
  'update:playing': [value: boolean]
}>()

const isPlaying = computed(() => props.playing ?? false)
const sliderValue = computed(() => props.displayValue ?? props.modelValue)
const currentLabelRound = computed(() => Math.min(props.totalRounds, Math.round(sliderValue.value)))

function togglePlay() {
  emit('update:playing', !isPlaying.value)
}
</script>

<template>
  <div class="temporal-slider" v-if="totalRounds > 0">
    <button class="play-btn" @click="togglePlay">
      {{ isPlaying ? '⏸' : '▶' }}
    </button>
    <div class="slider-track">
      <input
        type="range"
        min="0"
        :max="totalRounds"
        step="0.001"
        :value="sliderValue"
        @input="emit('update:modelValue', Math.round(Number(($event.target as HTMLInputElement).value)))"
        class="slider-input"
      />
      <div class="slider-labels">
        <span class="slider-label">R0</span>
        <span class="slider-label current">R{{ currentLabelRound }}</span>
        <span class="slider-label">R{{ totalRounds }}</span>
      </div>
    </div>
  </div>
</template>

<style scoped>
.temporal-slider {
  display: flex;
  align-items: center;
  gap: 0.75rem;
  padding: 0.6rem 1rem;
  background: rgba(10, 10, 30, 0.75);
  backdrop-filter: blur(8px);
  border: 1px solid rgba(100, 100, 255, 0.15);
  border-radius: 8px;
}

.play-btn {
  width: 32px;
  height: 32px;
  border-radius: 50%;
  border: 1px solid rgba(100, 100, 255, 0.3);
  background: rgba(20, 20, 60, 0.8);
  color: rgba(200, 200, 255, 0.8);
  font-size: 0.8rem;
  cursor: pointer;
  display: flex;
  align-items: center;
  justify-content: center;
  flex-shrink: 0;
  transition: all 0.2s;
}

.play-btn:hover {
  background: rgba(40, 40, 100, 0.9);
  border-color: var(--accent);
  color: #fff;
}

.slider-track {
  flex: 1;
  display: flex;
  flex-direction: column;
  gap: 0.2rem;
}

.slider-input {
  width: 100%;
  appearance: none;
  height: 4px;
  background: rgba(100, 100, 255, 0.15);
  border-radius: 2px;
  outline: none;
  cursor: pointer;
}

.slider-input::-webkit-slider-thumb {
  appearance: none;
  width: 14px;
  height: 14px;
  border-radius: 50%;
  background: var(--accent);
  border: 2px solid rgba(255, 255, 255, 0.3);
  box-shadow: 0 0 8px var(--accent-glow);
  cursor: pointer;
}

.slider-labels {
  display: flex;
  justify-content: space-between;
}

.slider-label {
  font-family: var(--font-mono);
  font-size: 0.6rem;
  color: rgba(200, 200, 255, 0.4);
}

.slider-label.current {
  color: var(--accent);
  font-weight: 600;
}
</style>
