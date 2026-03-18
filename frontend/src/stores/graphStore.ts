import { defineStore } from 'pinia'
import { ref } from 'vue'

export interface GraphNode {
  id: string
  label: string
  type: string
  importance_score: number
  stance: string
  activity_score: number
  sentiment_score: number
  status: string
  group: string
}

export interface GraphEdge {
  id: string
  source: string
  target: string
  relation_type: string
  weight: number
  direction: string
  status: string
}

export const useGraphStore = defineStore('graph', () => {
  const nodes = ref<GraphNode[]>([])
  const edges = ref<GraphEdge[]>([])
  function applyDiff(diff: any) {
    // Remove nodes
    if (diff.removed_nodes?.length) {
      const removeIds = new Set(diff.removed_nodes.map((n: any) => n.id))
      nodes.value = nodes.value.filter((n) => !removeIds.has(n.id))
      edges.value = edges.value.filter(
        (e) => !removeIds.has(e.source) && !removeIds.has(e.target),
      )
    }

    // Add nodes
    if (diff.added_nodes?.length) {
      const existingIds = new Set(nodes.value.map((n) => n.id))
      for (const node of diff.added_nodes) {
        if (!existingIds.has(node.id)) {
          nodes.value.push(node)
        }
      }
    }

    // Update nodes
    if (diff.updated_nodes?.length) {
      for (const update of diff.updated_nodes) {
        const idx = nodes.value.findIndex((n) => n.id === update.id)
        if (idx >= 0) {
          nodes.value[idx] = { ...nodes.value[idx], ...update }
        }
      }
    }

    // Remove edges
    if (diff.removed_edges?.length) {
      const removeIds = new Set(diff.removed_edges.map((e: any) => e.id))
      edges.value = edges.value.filter((e) => !removeIds.has(e.id))
    }

    // Add edges
    if (diff.added_edges?.length) {
      const existingIds = new Set(edges.value.map((e) => e.id))
      for (const edge of diff.added_edges) {
        if (!existingIds.has(edge.id)) {
          edges.value.push(edge)
        }
      }
    }

    // Update edges
    if (diff.updated_edges?.length) {
      for (const update of diff.updated_edges) {
        const idx = edges.value.findIndex((e) => e.id === update.id)
        if (idx >= 0) {
          edges.value[idx] = { ...edges.value[idx], ...update }
        }
      }
    }

  }

  function setFullState(graphNodes: GraphNode[], graphEdges: GraphEdge[]) {
    nodes.value = graphNodes
    edges.value = graphEdges
  }

  return { nodes, edges, applyDiff, setFullState }
})
