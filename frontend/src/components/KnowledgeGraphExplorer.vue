<script setup lang="ts">
import { ref, computed } from 'vue'

interface KGEntity {
  id: string
  label: string
  type: string
  description: string
  community?: string
  aliases?: string[]
}

interface KGRelation {
  source: string
  target: string
  type: string
  confidence: number
}

interface KGCommunity {
  community: number
  summary: string
  members: string[]
}

const props = defineProps<{
  entities: KGEntity[]
  relations: KGRelation[]
  communities: KGCommunity[]
}>()

const searchQuery = ref('')
const selectedEntity = ref<KGEntity | null>(null)
const selectedCommunity = ref<KGCommunity | null>(null)

const filteredEntities = computed(() => {
  if (!searchQuery.value) return props.entities
  const q = searchQuery.value.toLowerCase()
  return props.entities.filter(
    e =>
      e.label.toLowerCase().includes(q) ||
      e.type.toLowerCase().includes(q) ||
      e.description.toLowerCase().includes(q),
  )
})

const entityRelations = computed(() => {
  if (!selectedEntity.value) return []
  const id = selectedEntity.value.id
  return props.relations.filter(r => r.source === id || r.target === id)
})

function selectEntity(entity: KGEntity) {
  selectedEntity.value = entity
  selectedCommunity.value = null
}

function selectCommunity(community: KGCommunity) {
  selectedCommunity.value = community
  selectedEntity.value = null
}

function typeColor(type: string): string {
  const colors: Record<string, string> = {
    person: '#3498db',
    organization: '#e74c3c',
    technology: '#27ae60',
    policy: '#f39c12',
    market: '#9b59b6',
    concept: '#1abc9c',
    location: '#e67e22',
    event: '#2ecc71',
    resource: '#34495e',
  }
  return colors[type] || '#95a5a6'
}
</script>

<template>
  <div class="kg-explorer">
    <div class="kg-sidebar">
      <input
        v-model="searchQuery"
        class="search-input"
        placeholder="エンティティを検索..."
      />

      <!-- コミュニティ一覧 -->
      <div v-if="communities.length > 0" class="communities-section">
        <h4>コミュニティ</h4>
        <div
          v-for="comm in communities"
          :key="comm.community"
          class="community-item"
          :class="{ selected: selectedCommunity?.community === comm.community }"
          @click="selectCommunity(comm)"
        >
          <div class="community-name">C{{ comm.community }} ({{ comm.members.length }})</div>
          <div class="community-summary">{{ comm.summary?.slice(0, 60) }}...</div>
        </div>
      </div>

      <!-- エンティティ一覧 -->
      <h4>エンティティ ({{ filteredEntities.length }})</h4>
      <div class="entity-list">
        <div
          v-for="entity in filteredEntities.slice(0, 50)"
          :key="entity.id"
          class="entity-item"
          :class="{ selected: selectedEntity?.id === entity.id }"
          @click="selectEntity(entity)"
        >
          <span class="entity-type-dot" :style="{ background: typeColor(entity.type) }"></span>
          <span class="entity-label">{{ entity.label }}</span>
          <span class="entity-type-text">{{ entity.type }}</span>
        </div>
      </div>
    </div>

    <div class="kg-detail">
      <!-- エンティティ詳細 -->
      <div v-if="selectedEntity" class="detail-panel">
        <h3>
          <span class="entity-type-dot large" :style="{ background: typeColor(selectedEntity.type) }"></span>
          {{ selectedEntity.label }}
        </h3>
        <div class="detail-type">{{ selectedEntity.type }}</div>
        <div class="detail-description">{{ selectedEntity.description }}</div>

        <div v-if="selectedEntity.aliases && selectedEntity.aliases.length > 0" class="aliases">
          <span class="detail-label">別名:</span>
          <span v-for="alias in selectedEntity.aliases" :key="alias" class="alias-badge">{{ alias }}</span>
        </div>

        <div v-if="entityRelations.length > 0" class="relations-section">
          <h4>関係 ({{ entityRelations.length }})</h4>
          <div v-for="rel in entityRelations" :key="`${rel.source}-${rel.target}`" class="relation-item">
            <span>{{ rel.source }}</span>
            <span class="rel-type">&mdash; {{ rel.type }} &rarr;</span>
            <span>{{ rel.target }}</span>
            <span class="rel-confidence">{{ (rel.confidence * 100).toFixed(0) }}%</span>
          </div>
        </div>
      </div>

      <!-- コミュニティ詳細 -->
      <div v-else-if="selectedCommunity" class="detail-panel">
        <h3>コミュニティ {{ selectedCommunity.community }}</h3>
        <div class="detail-description">{{ selectedCommunity.summary }}</div>
        <div class="members-section">
          <h4>メンバー ({{ selectedCommunity.members.length }})</h4>
          <div class="member-list">
            <span v-for="member in selectedCommunity.members" :key="member" class="member-badge">
              {{ member }}
            </span>
          </div>
        </div>
      </div>

      <div v-else class="no-selection">
        エンティティまたはコミュニティを選択してください
      </div>
    </div>
  </div>
</template>

<style scoped>
.kg-explorer {
  display: flex;
  height: 100%;
  gap: 1rem;
}
.kg-sidebar {
  width: 300px;
  overflow-y: auto;
  border-right: 1px solid #e0e0e0;
  padding-right: 1rem;
}
.search-input {
  width: 100%;
  padding: 0.5rem;
  border: 1px solid #e0e0e0;
  border-radius: 6px;
  margin-bottom: 1rem;
}
.communities-section {
  margin-bottom: 1.5rem;
}
.community-item {
  padding: 0.5rem;
  border-radius: 6px;
  cursor: pointer;
  margin-bottom: 0.25rem;
}
.community-item:hover {
  background: #f0f7ff;
}
.community-item.selected {
  background: #e3f2fd;
}
.community-name {
  font-weight: 600;
  font-size: 0.85rem;
}
.community-summary {
  font-size: 0.8rem;
  color: #666;
}
.entity-list {
  max-height: 400px;
  overflow-y: auto;
}
.entity-item {
  display: flex;
  align-items: center;
  gap: 0.5rem;
  padding: 0.4rem;
  cursor: pointer;
  border-radius: 4px;
}
.entity-item:hover {
  background: #f0f7ff;
}
.entity-item.selected {
  background: #e3f2fd;
}
.entity-type-dot {
  width: 8px;
  height: 8px;
  border-radius: 50%;
  flex-shrink: 0;
}
.entity-type-dot.large {
  width: 12px;
  height: 12px;
}
.entity-label {
  flex: 1;
  font-size: 0.85rem;
}
.entity-type-text {
  font-size: 0.75rem;
  color: #999;
}
.kg-detail {
  flex: 1;
  overflow-y: auto;
  padding: 0 1rem;
}
.detail-panel h3 {
  display: flex;
  align-items: center;
  gap: 0.5rem;
}
.detail-type {
  color: #666;
  margin-bottom: 0.5rem;
}
.detail-description {
  line-height: 1.6;
  margin-bottom: 1rem;
}
.detail-label {
  font-size: 0.85rem;
  color: #888;
}
.aliases {
  margin-bottom: 1rem;
}
.alias-badge, .member-badge {
  display: inline-block;
  padding: 0.15rem 0.5rem;
  background: #f0f0f0;
  border-radius: 4px;
  font-size: 0.8rem;
  margin: 0.2rem;
}
.relations-section {
  margin-top: 1.5rem;
}
.relation-item {
  display: flex;
  gap: 0.5rem;
  padding: 0.4rem 0;
  border-bottom: 1px solid #f0f0f0;
  font-size: 0.85rem;
}
.rel-type {
  color: #888;
}
.rel-confidence {
  color: #999;
  font-size: 0.8rem;
}
.no-selection {
  display: flex;
  align-items: center;
  justify-content: center;
  height: 100%;
  color: #999;
}
</style>
