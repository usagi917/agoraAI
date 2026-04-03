<script setup lang="ts">
import { ref } from 'vue'

export interface OpinionShift {
  agent_name: string
  before: string
  after: string
  reasoning: string
}

defineProps<{
  shifts: OpinionShift[]
}>()

const expandedRows = ref<Set<number>>(new Set())

function toggleRow(index: number) {
  if (expandedRows.value.has(index)) {
    expandedRows.value.delete(index)
  } else {
    expandedRows.value.add(index)
  }
}
</script>

<template>
  <div class="opinion-shift-table" data-testid="opinion-shift-table">
    <h3 class="table-title">Opinion Shifts (Top 5)</h3>
    <div v-if="shifts.length === 0" class="table-empty">
      <p class="empty-text">データなし</p>
    </div>
    <table v-else class="shift-table">
      <thead>
        <tr>
          <th class="th-agent">Agent</th>
          <th class="th-before">Before</th>
          <th class="th-after">After</th>
          <th class="th-reasoning">Reasoning</th>
        </tr>
      </thead>
      <tbody>
        <tr
          v-for="(shift, i) in shifts"
          :key="i"
          class="shift-row"
          data-testid="shift-row"
        >
          <td class="td-agent">{{ shift.agent_name }}</td>
          <td class="td-before">
            <span class="stance-badge">{{ shift.before }}</span>
          </td>
          <td class="td-after">
            <span class="stance-badge stance-badge-after">{{ shift.after }}</span>
          </td>
          <td class="td-reasoning" @click="toggleRow(i)">
            <span
              class="reasoning-text"
              :class="{ 'reasoning-expanded': expandedRows.has(i) }"
            >
              {{ shift.reasoning }}
            </span>
            <button
              v-if="shift.reasoning.length > 80"
              class="expand-btn"
              data-testid="expand-btn"
              @click.stop="toggleRow(i)"
            >
              {{ expandedRows.has(i) ? 'less' : 'more' }}
            </button>
          </td>
        </tr>
      </tbody>
    </table>
  </div>
</template>

<style scoped>
.opinion-shift-table {
  display: flex;
  flex-direction: column;
  gap: var(--space-4);
}

.table-title {
  font-size: var(--text-lg);
  font-weight: 700;
  padding-bottom: var(--space-2);
  border-bottom: 1px solid var(--border);
}

.table-empty {
  display: flex;
  align-items: center;
  justify-content: center;
  min-height: 80px;
}

.empty-text {
  color: var(--text-muted);
  font-size: var(--text-sm);
}

.shift-table {
  width: 100%;
  border-collapse: collapse;
  font-size: var(--text-sm);
}

.shift-table th {
  text-align: left;
  font-size: var(--text-xs);
  font-weight: 600;
  color: var(--text-muted);
  text-transform: uppercase;
  letter-spacing: 0.05em;
  font-family: var(--font-mono);
  padding: var(--space-2) var(--space-3);
  border-bottom: 1px solid var(--border);
}

.shift-table td {
  padding: var(--space-3);
  border-bottom: 1px solid var(--border);
  vertical-align: top;
}

.shift-row:hover {
  background: rgba(255, 255, 255, 0.02);
}

.th-agent { width: 20%; }
.th-before { width: 15%; }
.th-after { width: 15%; }
.th-reasoning { width: 50%; }

.td-agent {
  font-weight: 600;
  color: var(--text-primary);
}

.stance-badge {
  display: inline-block;
  padding: var(--space-1) var(--space-2);
  border-radius: var(--radius-sm);
  font-family: var(--font-mono);
  font-size: var(--text-xs);
  font-weight: 600;
  background: rgba(255, 255, 255, 0.06);
  color: var(--text-secondary);
}

.stance-badge-after {
  background: rgba(59, 130, 246, 0.15);
  color: var(--accent);
}

.td-reasoning {
  cursor: pointer;
}

.reasoning-text {
  display: -webkit-box;
  -webkit-line-clamp: 2;
  -webkit-box-orient: vertical;
  overflow: hidden;
  color: var(--text-secondary);
  line-height: 1.6;
}

.reasoning-expanded {
  display: block;
  -webkit-line-clamp: unset;
  overflow: visible;
}

.expand-btn {
  display: inline-block;
  margin-top: var(--space-1);
  background: none;
  border: none;
  color: var(--accent);
  font-size: var(--text-xs);
  font-family: var(--font-mono);
  cursor: pointer;
  padding: 0;
}

.expand-btn:hover {
  color: var(--accent-hover);
}

@media (max-width: 640px) {
  .shift-table {
    font-size: var(--text-xs);
  }

  .shift-table th,
  .shift-table td {
    padding: var(--space-2);
  }

  .th-agent { width: auto; }
  .th-before { width: auto; }
  .th-after { width: auto; }
  .th-reasoning { width: auto; }
}
</style>
