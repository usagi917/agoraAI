import axios from 'axios'

const api = axios.create({
  baseURL: import.meta.env.VITE_API_BASE_URL || '/api',
})

export interface TemplateResponse {
  id: string
  name: string
  display_name: string
  description: string
  category: string
}

export interface HealthResponse {
  status: string
  version: string
  llm_provider: string
  live_simulation_available: boolean
  live_simulation_message: string
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

export async function getHealth(): Promise<HealthResponse> {
  const { data } = await api.get('/health')
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

export type PipelineStage = 'pending' | 'single' | 'swarm' | 'pm_board' | 'completed'

export interface SimulationResponse {
  id: string
  project_id: string | null
  mode: string
  prompt_text: string
  template_name: string
  execution_profile: string
  colony_count: number
  deep_colony_count: number
  status: string
  error_message: string
  pipeline_stage: PipelineStage
  stage_progress: Record<string, string>
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
  pipeline_stage: PipelineStage
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

export interface SimulationTimelineEvent {
  id: string
  round_number: number
  event_type: string
  title: string
  description: string
  severity: number
  involved_entities: string[]
  created_at?: string | null
}

export async function createSimulation(
  options: {
    projectId?: string
    templateName?: string
    executionProfile?: string
    promptText?: string
    mode?: string
  } = {},
): Promise<SimulationResponse> {
  const { data } = await api.post('/simulations', {
    project_id: options.projectId || null,
    template_name: options.templateName || '',
    execution_profile: options.executionProfile || 'standard',
    mode: options.mode || 'pipeline',
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

export async function getSimulationTimeline(simId: string): Promise<SimulationTimelineEvent[]> {
  const { data } = await api.get(`/simulations/${simId}/timeline`)
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

// === Sample Results API (API Key不要) ===

export async function getSampleResults() {
  const { data } = await api.get('/simulations/samples')
  return data
}

export async function getSampleResult(sampleId: string) {
  const { data } = await api.get(`/simulations/samples/${sampleId}`)
  return data
}
