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

export interface EvidenceRef {
  source_type: string
  source_id: string
  label: string
  excerpt: string
  char_start: number
  char_end: number
}

export interface QualitySummary {
  status: 'verified' | 'draft' | 'unsupported'
  fallback_used: boolean
  fallback_reason: string
  calibration_status: string
  evidence_mode?: 'strict' | 'prefer' | 'off'
  trust_level: 'high_trust' | 'low_trust' | 'no_evidence'
  evidence_available: boolean
  evidence_refs_count: number
  document_refs_count?: number
  prompt_refs_count?: number
  unsupported_reason?: string
  issues: string[]
}

export interface RunConfig {
  evidence_mode: 'strict' | 'prefer' | 'off'
  trust_mode: string
}

export interface VerificationSummary {
  status: 'passed' | 'failed'
  score: number
  issues: string[]
  warnings: string[]
  metrics: Record<string, any>
  checks?: Record<string, VerificationSummary>
}

export interface SectionDetail {
  title: string
  content: string
  evidence_refs: EvidenceRef[]
  quality: QualitySummary
}

export interface ScenarioReport {
  description: string
  probability?: number
  scenario_score: number
  agreement_ratio?: number
  mean_confidence?: number
  ci?: [number, number]
  support_ratio: number
  model_confidence_mean: number
  supporting_colonies?: number
  total_colonies?: number
  claim_count?: number
  calibrated_probability?: number | null
  calibration_version?: string | null
  evidence_refs: EvidenceRef[]
  quality: QualitySummary
}

export interface SimulationReportBase {
  type: string
  content?: string
  sections?: Record<string, any>
  scenarios?: ScenarioReport[]
  diversity_score?: number
  entropy?: number
  agreement_matrix?: Record<string, any>
  colonies?: Array<Record<string, any>>
  pm_board?: PMBoardReportResponse
  evidence_refs: EvidenceRef[]
  run_config: RunConfig
  quality: QualitySummary
  verification?: VerificationSummary | null
}

export interface PMBoardSections {
  core_question?: string
  assumptions?: Array<Record<string, any>>
  uncertainties?: Array<Record<string, any>>
  risks?: Array<Record<string, any>>
  winning_hypothesis?: Record<string, any>
  customer_validation_plan?: Record<string, any>
  market_view?: Record<string, any>
  gtm_hypothesis?: Record<string, any>
  mvp_scope?: Record<string, any>
  plan_30_60_90?: Record<string, any>
  top_5_actions?: Array<Record<string, any>>
}

export interface PMBoardReportResponse extends SimulationReportBase {
  type: 'pm_board'
  sections: PMBoardSections
  contradictions?: Array<Record<string, any>>
  overall_confidence?: number
  key_decision_points?: string[]
  section_evidence?: Record<string, SectionDetail>
}

export interface SingleReportResponse extends SimulationReportBase {
  type: 'single'
  id: string
  run_id: string
  content: string
  sections: Record<string, any>
  status: string
}

export interface SwarmReportResponse extends SimulationReportBase {
  type: 'swarm'
  swarm_id: string
  scenarios: ScenarioReport[]
  diversity_score: number
  entropy: number
  agreement_matrix?: Record<string, any>
  colonies?: Array<Record<string, any>>
  metadata?: Record<string, any>
}

export interface PipelineReportResponse extends SimulationReportBase {
  type: 'pipeline'
  id?: string
  run_id?: string
  status?: string
  content: string
  sections?: Record<string, any>
  scenarios?: ScenarioReport[]
  diversity_score?: number
  entropy?: number
  agreement_matrix?: Record<string, any>
  swarm_metadata?: Record<string, any>
  colonies?: Array<Record<string, any>>
  pm_board?: PMBoardReportResponse
}

export type SimulationReportResponse = SimulationReportBase

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
    evidenceMode?: string
  } = {},
): Promise<SimulationResponse> {
  const { data } = await api.post('/simulations', {
    project_id: options.projectId || null,
    template_name: options.templateName || '',
    execution_profile: options.executionProfile || 'standard',
    mode: options.mode || 'pipeline',
    prompt_text: options.promptText || '',
    evidence_mode: options.evidenceMode || 'strict',
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

export async function getSimulationReport(simId: string): Promise<SimulationReportResponse> {
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

// === Society API ===

export interface PopulationResponse {
  id: string
  version: number
  agent_count: number
  status: string
  created_at: string
}

export interface SocietyActivationResponse {
  id: string
  simulation_id: string
  population_id: string
  phase_data: {
    aggregation: {
      total_respondents: number
      stance_distribution: Record<string, number>
      average_confidence: number
      top_concerns: string[]
      top_priorities: string[]
    }
    representative_count: number
  }
  usage: Record<string, any>
  created_at: string
}

export interface EvaluationMetric {
  id: string
  metric_name: string
  score: number
  details: Record<string, any>
  baseline_type: string | null
  baseline_score: number | null
  created_at: string
}

export async function listPopulations(): Promise<PopulationResponse[]> {
  const { data } = await api.get('/society/populations')
  return data
}

export async function generatePopulation(count: number = 1000, seed?: number) {
  const { data } = await api.post('/society/populations/generate', { count, seed })
  return data
}

export async function getSocietyActivation(simId: string): Promise<SocietyActivationResponse> {
  const { data } = await api.get(`/society/simulations/${simId}/activation`)
  return data
}

export async function getSocietyEvaluation(simId: string): Promise<EvaluationMetric[]> {
  const { data } = await api.get(`/society/simulations/${simId}/evaluation`)
  return data
}

export async function getSocietyMeeting(simId: string) {
  const { data } = await api.get(`/society/simulations/${simId}/meeting`)
  return data
}

export async function getPopulationDetail(popId: string) {
  const { data } = await api.get(`/society/populations/${popId}`)
  return data
}

export async function forkPopulation(popId: string) {
  const { data } = await api.post(`/society/populations/${popId}/fork`)
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
