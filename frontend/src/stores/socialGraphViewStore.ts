import { ref } from 'vue'
import { defineStore } from 'pinia'

export const useSocialGraphViewStore = defineStore('socialGraphView', () => {
  const selectedNodeId = ref<string | null>(null)
  const selectedEdgeId = ref<string | null>(null)
  const searchQuery = ref('')

  function selectNode(nodeId: string | null) {
    selectedNodeId.value = nodeId
    if (nodeId) selectedEdgeId.value = null
  }

  function selectEdge(edgeId: string | null) {
    selectedEdgeId.value = edgeId
    if (edgeId) selectedNodeId.value = null
  }

  function focusEvent(sourceId?: string | null, edgeId?: string | null) {
    if (edgeId) selectEdge(edgeId)
    else if (sourceId) selectNode(sourceId)
  }

  function reset() {
    selectedNodeId.value = null
    selectedEdgeId.value = null
    searchQuery.value = ''
  }

  return {
    selectedNodeId,
    selectedEdgeId,
    searchQuery,
    selectNode,
    selectEdge,
    focusEvent,
    reset,
  }
})
