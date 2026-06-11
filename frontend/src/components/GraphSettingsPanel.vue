<script setup lang="ts">
import { DEFAULT_PHYSICS, type GraphPhysics } from './forceGraphHelpers'

const props = defineProps<{
  physics: GraphPhysics
}>()

const emit = defineEmits<{
  (e: 'update:physics', physics: GraphPhysics): void
}>()

function update(key: keyof GraphPhysics, raw: string) {
  const value = Number(raw)
  if (Number.isNaN(value)) return
  emit('update:physics', { ...props.physics, [key]: value })
}

function reset() {
  emit('update:physics', { ...DEFAULT_PHYSICS })
}
</script>

<template>
  <div class="graph-settings" data-testid="graph-settings-panel">
    <div class="settings-header">
      <span class="settings-title">グラフ物理</span>
      <button class="settings-reset" data-testid="physics-reset" @click="reset">リセット</button>
    </div>

    <label class="setting-row">
      <span class="setting-label">反発力</span>
      <input
        type="range"
        data-testid="physics-charge"
        :value="physics.chargeStrength"
        min="-600"
        max="-40"
        step="10"
        @input="update('chargeStrength', ($event.target as HTMLInputElement).value)"
      />
    </label>

    <label class="setting-row">
      <span class="setting-label">リンク距離</span>
      <input
        type="range"
        data-testid="physics-link-distance"
        :value="physics.linkDistance"
        min="20"
        max="160"
        step="5"
        @input="update('linkDistance', ($event.target as HTMLInputElement).value)"
      />
    </label>

    <label class="setting-row">
      <span class="setting-label">中心力</span>
      <input
        type="range"
        data-testid="physics-center"
        :value="physics.centerStrength"
        min="0"
        max="0.2"
        step="0.01"
        @input="update('centerStrength', ($event.target as HTMLInputElement).value)"
      />
    </label>

    <label class="setting-row">
      <span class="setting-label">ノード間隔</span>
      <input
        type="range"
        data-testid="physics-collide"
        :value="physics.collidePadding"
        min="0"
        max="16"
        step="1"
        @input="update('collidePadding', ($event.target as HTMLInputElement).value)"
      />
    </label>
  </div>
</template>

<style scoped>
.graph-settings {
  display: flex;
  flex-direction: column;
  gap: 0.45rem;
  width: 13rem;
  padding: 0.7rem 0.8rem;
  background: rgba(12, 13, 26, 0.92);
  backdrop-filter: blur(10px);
  border: 1px solid rgba(255, 255, 255, 0.1);
  border-radius: 10px;
}

.settings-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  margin-bottom: 0.15rem;
}

.settings-title {
  font-size: 0.68rem;
  font-weight: 600;
  text-transform: uppercase;
  letter-spacing: 0.06em;
  color: rgba(200, 200, 220, 0.75);
}

.settings-reset {
  font-size: 0.62rem;
  padding: 0.1rem 0.4rem;
  background: transparent;
  border: 1px solid rgba(255, 255, 255, 0.14);
  border-radius: 4px;
  color: rgba(180, 180, 200, 0.7);
  cursor: pointer;
  transition: all 0.15s;
}
.settings-reset:hover {
  border-color: rgba(255, 255, 255, 0.3);
  color: rgba(230, 230, 245, 0.9);
}

.setting-row {
  display: flex;
  align-items: center;
  gap: 0.5rem;
}

.setting-label {
  flex: 0 0 4.2rem;
  font-size: 0.66rem;
  color: rgba(200, 200, 220, 0.65);
}

.setting-row input[type='range'] {
  flex: 1;
  height: 3px;
  accent-color: #8b7cf6;
  cursor: pointer;
}
</style>
