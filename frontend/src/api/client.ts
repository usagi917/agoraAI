import axios from 'axios'

const api = axios.create({
  baseURL: '/api',
})

export interface TemplateResponse {
  id: string
  name: string
  display_name: string
  description: string
  category: string
}

export async function createProject(name: string) {
  const { data } = await api.post(`/projects?name=${encodeURIComponent(name)}`)
  return data
}

export async function uploadDocument(projectId: string, file: File) {
  const formData = new FormData()
  formData.append('file', file)
  const { data } = await api.post(`/projects/${projectId}/documents`, formData)
  return data
}

export async function getTemplates(): Promise<TemplateResponse[]> {
  const { data } = await api.get('/templates')
  return data
}

// === Simulation Types ===

export interface ColonyResponse {
  id: string
  colony_index: number
  perspective_id: string
  perspective_label: string
  temperature: number
  adversarial: boolean
  status: string
  current_round: number
  total_rounds: number
  error_message: string
}

// === Simulation API (統一) ===

export interface SimulationResponse {
  id: string
  project_id: string | null
  mode: 'single' | 'swarm' | 'hybrid'
  prompt_text: string
  template_name: string
  execution_profile: string
  colony_count: number
  deep_colony_count: number
  status: string
  error_message: string
  run_id: string | null
  swarm_id: string | null
  metadata: Record<string, any>
  created_at: string
  started_at: string | null
  completed_at: string | null
}

export interface SimulationListItem {
  id: string
  project_id: string | null
  mode: string
  status: string
  template_name: string
  execution_profile: string
  colony_count: number
  run_id: string | null
  swarm_id: string | null
  created_at: string
  completed_at: string | null
}

export interface GraphSnapshot {
  round: number
  nodes: any[]
  edges: any[]
  focus_entities?: string[]
}

export async function createSimulation(
  mode: 'single' | 'swarm' | 'hybrid',
  options: {
    projectId?: string
    templateName?: string
    executionProfile?: string
    promptText?: string
  } = {},
): Promise<SimulationResponse> {
  const { data } = await api.post('/simulations', {
    project_id: options.projectId || null,
    template_name: options.templateName || '',
    execution_profile: options.executionProfile || 'standard',
    mode,
    prompt_text: options.promptText || '',
  })
  return data
}

export async function listSimulations(): Promise<SimulationListItem[]> {
  const { data } = await api.get('/simulations')
  return data
}

export async function getSimulation(simId: string): Promise<SimulationResponse> {
  const { data } = await api.get(`/simulations/${simId}`)
  return data
}

export async function getSimulationGraph(simId: string) {
  const { data } = await api.get(`/simulations/${simId}/graph`)
  return data
}

export async function getSimulationGraphHistory(simId: string): Promise<GraphSnapshot[]> {
  const { data } = await api.get(`/simulations/${simId}/graph/history`)
  return data
}

export async function getSimulationReport(simId: string) {
  const { data } = await api.get(`/simulations/${simId}/report`)
  return data
}

export async function getSimulationColonies(simId: string): Promise<ColonyResponse[]> {
  const { data } = await api.get(`/simulations/${simId}/colonies`)
  return data
}

export async function submitSimulationFollowup(simId: string, question: string) {
  const { data } = await api.post(`/simulations/${simId}/followups?question=${encodeURIComponent(question)}`)
  return data
}

export async function rerunSimulation(simId: string) {
  const { data } = await api.post(`/simulations/${simId}/rerun`)
  return data
}
