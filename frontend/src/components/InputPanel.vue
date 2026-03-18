<script setup lang="ts">
import { ref } from 'vue'

const props = defineProps<{
  modelValue: string
  files: File[]
}>()

const emit = defineEmits<{
  'update:modelValue': [value: string]
  'update:files': [files: File[]]
}>()

const isDragOver = ref(false)

function handleDrop(event: DragEvent) {
  isDragOver.value = false
  if (event.dataTransfer?.files) {
    emit('update:files', Array.from(event.dataTransfer.files))
  }
}

function handleFileSelect(event: Event) {
  const input = event.target as HTMLInputElement
  if (input.files) {
    emit('update:files', Array.from(input.files))
  }
}
</script>

<template>
  <div class="input-panel">
    <!-- Prompt textarea -->
    <div class="prompt-section">
      <label class="input-label">分析プロンプト</label>
      <textarea
        class="prompt-textarea"
        :value="modelValue"
        @input="emit('update:modelValue', ($event.target as HTMLTextAreaElement).value)"
        placeholder="もし〜なら？ — 分析したい仮説やシナリオを入力してください。ファイルなしでも起動可能です。"
        rows="4"
      ></textarea>
    </div>

    <!-- File drop zone -->
    <div class="file-section">
      <label class="input-label">
        データ入力
        <span v-if="files.length > 0" class="file-count">{{ files.length }} ファイル</span>
      </label>
      <div
        class="upload-area"
        :class="{ 'drag-over': isDragOver, 'has-files': files.length > 0 }"
        @dragover.prevent="isDragOver = true"
        @dragleave="isDragOver = false"
        @drop.prevent="handleDrop"
      >
        <input
          type="file"
          multiple
          accept=".txt,.md,.pdf"
          @change="handleFileSelect"
          class="file-input"
          id="sim-file-upload"
        />
        <label for="sim-file-upload" class="upload-label">
          <div class="upload-icon">
            <svg width="24" height="24" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5">
              <path d="M21 15v4a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2v-4" />
              <polyline points="17 8 12 3 7 8" />
              <line x1="12" y1="3" x2="12" y2="15" />
            </svg>
          </div>
          <span class="upload-text">ファイルをドラッグ&ドロップ または クリック</span>
          <span class="upload-hint">txt / md / pdf · オプション</span>
        </label>
        <div v-if="files.length > 0" class="file-list">
          <div v-for="file in files" :key="file.name" class="file-item">
            <span class="file-name">{{ file.name }}</span>
            <span class="file-size">{{ Math.round(file.size / 1024) }}KB</span>
          </div>
        </div>
      </div>
    </div>
  </div>
</template>

<style scoped>
.input-panel {
  display: flex;
  flex-direction: column;
  gap: 1.25rem;
}

.input-label {
  display: flex;
  align-items: center;
  gap: 0.5rem;
  flex-wrap: wrap;
  font-size: 0.8rem;
  font-weight: 600;
  color: var(--text-secondary);
  margin-bottom: 0.5rem;
}

.file-count {
  font-family: var(--font-mono);
  font-size: 0.68rem;
  color: var(--text-muted);
  background: rgba(255, 255, 255, 0.04);
  padding: 0.1rem 0.4rem;
  border-radius: 999px;
  border: 1px solid var(--border);
}

.prompt-textarea {
  width: 100%;
  padding: 0.85rem 1rem;
  background: var(--bg-card);
  border: 1px solid var(--border);
  border-radius: var(--radius);
  color: var(--text-primary);
  font-family: var(--font-sans);
  font-size: 0.88rem;
  line-height: 1.6;
  resize: vertical;
  outline: none;
  transition: border-color 0.2s;
}

.prompt-textarea:focus {
  border-color: var(--accent);
  box-shadow: 0 0 0 2px var(--accent-glow);
}

.prompt-textarea::placeholder {
  color: var(--text-muted);
}

.upload-area {
  border: 2px dashed rgba(255, 255, 255, 0.08);
  border-radius: var(--radius);
  background: var(--bg-card);
  transition: all 0.3s;
  overflow: hidden;
}

.upload-area.drag-over {
  border-color: var(--accent);
  background: var(--accent-subtle);
}

.upload-area.has-files {
  border-style: solid;
  border-color: var(--border-active);
}

.file-input { display: none; }

.upload-label {
  display: flex;
  flex-direction: column;
  align-items: center;
  gap: 0.35rem;
  padding: 1.25rem;
  cursor: pointer;
  text-align: center;
}

.upload-icon { color: var(--text-muted); }
.upload-label:hover .upload-icon { color: var(--accent); }

.upload-text {
  font-size: 0.82rem;
  color: var(--text-secondary);
}

.upload-hint {
  font-size: 0.7rem;
  color: var(--text-muted);
}

.file-list { padding: 0 1rem 1rem; }

.file-item {
  display: flex;
  align-items: center;
  justify-content: space-between;
  flex-wrap: wrap;
  gap: 0.5rem;
  padding: 0.4rem 0.6rem;
  font-size: 0.78rem;
  border-radius: var(--radius-sm);
  background: rgba(255, 255, 255, 0.02);
  margin-top: 0.25rem;
}

.file-name {
  flex: 1 1 12rem;
  min-width: 0;
  color: var(--text-primary);
  overflow-wrap: anywhere;
}

.file-size {
  font-family: var(--font-mono);
  font-size: 0.68rem;
  color: var(--text-muted);
}

@media (max-width: 640px) {
  .input-panel {
    gap: 1rem;
  }

  .prompt-textarea {
    min-height: 9rem;
  }

  .upload-label {
    padding: 1rem;
  }

  .upload-text {
    line-height: 1.5;
  }

  .file-list {
    padding-inline: 0.75rem;
  }

  .file-item {
    align-items: flex-start;
  }
}
</style>
