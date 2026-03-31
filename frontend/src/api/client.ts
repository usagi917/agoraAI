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

export interface DecisionKeyReason {
  reason: string
  evidence?: string
  confidence?: number
  decision_impact?: string
}

export interface DecisionGuardrail {
  condition: string
  status?: string
  why_it_matters?: string
}

export interface DecisionDealBreaker {
  trigger: string
  impact: string
  recommended_response?: string
}

export interface DecisionUnknown {
  question: string
  importance?: string
  how_to_validate?: string
  decision_blocking?: boolean
}

export interface DecisionNextDecision {
  decision: string
  owner?: string
  deadline?: string
  input_needed?: string
}

export interface DecisionAction {
  action: string
  owner?: string
  deadline?: string
  expected_learning?: string
  priority?: 'high' | 'medium' | 'low' | string
}

export interface DecisionOptionComparison {
  label: string
  upside?: string
  downside?: string
  fit?: string
  when_to_choose?: string
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
  decision_brief?: DecisionBrief
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

export interface SocietyFirstIssueCandidate {
  issue_id: string
  label: string
  description: string
  population_share: number
  controversy_score: number
  market_impact_score: number
  network_spread_score: number
  selection_score: number
  supporting_stances?: Array<{ stance: string; share: number }>
  sample_reasons?: string[]
}

export interface SocietyFirstIssueColony {
  issue_id: string
  label: string
  description: string
  swarm_id: string
  integrated_report: string
  top_scenarios?: ScenarioReport[]
  diversity_score?: number
  entropy?: number
  colony_count?: number
}

export interface SocietyFirstIntervention {
  intervention_id: string
  label: string
  change_summary: string
  affected_issues: string[]
  comparison_mode?: 'heuristic' | 'observed'
  expected_effect: string
  observed_uplift?: number | null
  observed_downside?: number | null
  uncertainty?: number | null
  observed_case_count?: number
  supporting_signals?: string[]
  supporting_evidence?: SocietyFirstInterventionEvidence[]
}

export interface SocietyFirstInterventionEvidence {
  case_id: string
  title: string
  metric: string
  metric_label: string
  baseline: number
  outcome: number
  signed_delta: number
  summary: string
  evidence?: string[]
}

export interface SocietyFirstBacktestMatch {
  issue_id: string
  issue_label: string
  scenario_description: string
  predicted_score: number
  actual_summary: string
  actual_scenario: string
  match_score: number
  label_match: number
  text_overlap: number
  tag_overlap: number
  verdict: 'hit' | 'partial_hit' | 'miss'
  reasons: string[]
}

export interface SocietyFirstHistoricalOutcome {
  issue_label?: string
  summary: string
  actual_scenario: string
  metrics: Record<string, number>
  tags: string[]
}

export interface SocietyFirstHistoricalCase {
  case_id: string
  title: string
  observed_at?: string
  linked_simulation_id?: string
  linked_report_id?: string
  baseline_metrics: Record<string, number>
  outcome: SocietyFirstHistoricalOutcome
  interventions: Array<{
    intervention_id: string
    label?: string
    baseline_metrics: Record<string, number>
    outcome_metrics: Record<string, number>
    evidence: string[]
  }>
}

export interface SocietyFirstBacktestCase extends SocietyFirstHistoricalCase {
  best_match?: SocietyFirstBacktestMatch | null
  scenario_matches?: SocietyFirstBacktestMatch[]
  issue_results?: Array<{
    issue_label: string
    verdict: 'hit' | 'partial_hit' | 'miss'
    match_score: number
    scenario_description: string
  }>
  summary?: {
    hit_count: number
    partial_hit_count: number
    miss_count: number
  }
}

export interface SocietyFirstBacktestSummary {
  case_count: number
  compared_case_count: number
  hit_count: number
  partial_hit_count: number
  miss_count: number
  hit_rate: number
  issue_hit_count: number
  issue_hit_rate: number
}

export interface SocietyFirstBacktestResponse {
  id?: string
  schema_version: number
  input_format: Record<string, any>
  matching_rules: Record<string, any>
  historical_cases: SocietyFirstHistoricalCase[]
  cases: SocietyFirstBacktestCase[]
  summary: SocietyFirstBacktestSummary
  status: 'no_data' | 'ready'
}

export interface SocietyFirstReportResponse extends SimulationReportBase {
  type: 'society_first'
  content: string
  sections?: Record<string, any>
  society_summary?: Record<string, any>
  issue_candidates?: SocietyFirstIssueCandidate[]
  selected_issues?: SocietyFirstIssueCandidate[]
  issue_colonies?: SocietyFirstIssueColony[]
  intervention_comparison?: SocietyFirstIntervention[]
  backtest?: SocietyFirstBacktestResponse
  scenarios?: ScenarioReport[]
}

export interface MetaInterventionPlan {
  intervention_id: string
  label: string
  change_type: string
  hypothesis: string
  target_issues: string[]
  expected_effect: string
  expected_delta: number
  confidence: number
  implementation_cost: string
  selection_score?: number
}

export interface MetaSimulationCycle {
  cycle_index: number
  population_id: string
  population_count: number
  selected_count: number
  aggregation: Record<string, any>
  evaluation: Record<string, number>
  meeting: Record<string, any>
  issue_candidates: SocietyFirstIssueCandidate[]
  selected_issues: SocietyFirstIssueCandidate[]
  issue_colonies: SocietyFirstIssueColony[]
  scenarios: ScenarioReport[]
  pm_board: PMBoardReportResponse
  interventions: MetaInterventionPlan[]
  selected_intervention?: MetaInterventionPlan | null
  score_breakdown?: {
    society_score: number
    swarm_score: number
    pm_score: number
    objective_score: number
  }
  objective_score: number
  stop_evaluation?: Record<string, any>
}

export interface MetaSimulationReportResponse extends SimulationReportBase {
  type: 'meta_simulation'
  content: string
  summary_markdown: string
  baseline: Record<string, any>
  cycles: MetaSimulationCycle[]
  final_state: Record<string, any>
  intervention_history: MetaInterventionPlan[]
  pm_board?: PMBoardReportResponse
  society_summary?: Record<string, any>
  scenarios?: ScenarioReport[]
}

export interface DecisionBrief {
  recommendation: 'Go' | 'No-Go' | '条件付きGo'
  agreement_score?: number
  agreement_breakdown?: { society: number; council: number; synthesis: number }
  decision_summary?: string
  why_now?: string
  key_reasons?: DecisionKeyReason[]
  guardrails?: DecisionGuardrail[]
  deal_breakers?: DecisionDealBreaker[]
  critical_unknowns?: DecisionUnknown[]
  next_decisions?: DecisionNextDecision[]
  recommended_actions?: DecisionAction[]
  option_comparison?: DecisionOptionComparison[]
  confidence_explainer?: string
  evidence_gaps?: string[]
  options?: Array<{ label: string; expected_effect: string; risk: string }>
  strongest_counterargument?: string
  risk_factors?: Array<{ condition: string; impact: string }>
  next_steps?: string[]
  time_horizon?: {
    short_term: { period: string; prediction: string }
    mid_term: { period: string; prediction: string }
    long_term: { period: string; prediction: string }
  }
  stakeholder_reactions?: Array<{ group: string; reaction: string; percentage: number }>
}

export interface UnifiedReportResponse extends SimulationReportBase {
  type: 'unified'
  decision_brief: DecisionBrief
  agreement_score: number
  society_summary: Record<string, any>
  council: {
    participants: Array<{ display_name: string; role: string; stance: string }>
    rounds: any[][]
    synthesis: Record<string, any>
    devil_advocate_summary: string
  }
}

export type SimulationReportResponse =
  | SingleReportResponse
  | SwarmReportResponse
  | PipelineReportResponse
  | PMBoardReportResponse
  | SocietyFirstReportResponse
  | MetaSimulationReportResponse
  | UnifiedReportResponse
  | SimulationReportBase

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
    mode: options.mode || 'unified',
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

export async function listPopulations(): Promise<PopulationResponse[]> {
  const { data } = await api.get('/society/populations')
  return data
}

export async function generatePopulation(count: number = 1000, seed?: number) {
  const { data } = await api.post('/society/populations/generate', { count, seed })
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

// === Society ソーシャルグラフ & エージェント API ===

export interface AgentDemographics {
  age: number
  gender: string
  occupation: string
  region: string
  income_bracket: string
  education: string
}

export interface SocialGraphNode {
  id: string
  agent_index: number
  demographics: AgentDemographics
  big_five: Record<string, number>
  values: Record<string, any>
  speech_style: string
  stance: string
  confidence: number
  reason: string
  concern: string
  priority: string
}

export interface SocialGraphEdge {
  id: string
  source: string
  target: string
  relation_type: string
  strength: number
}

export interface SocialGraphResponse {
  nodes: SocialGraphNode[]
  edges: SocialGraphEdge[]
  population_id: string
}

export interface AgentConnection {
  id: string
  agent_id: string
  target_id: string
  relation_type: string
  strength: number
  connected_to: string
}

export interface MeetingArgument {
  participant_index: number
  participant_name: string
  role: string
  expertise: string
  round: number
  position: string
  argument: string
  evidence: string
  concerns: string[]
  questions_to_others: string[]
  addressed_to?: string
  addressed_to_participant_index?: number | null
  belief_update?: string
  round_name?: string
  sub_round?: string
  tension_topic?: string
  is_devil_advocate?: boolean
}

export interface MeetingParticipant {
  role: string
  expertise: string
  display_name: string
  agent_id?: string
  agent_index?: number
  occupation?: string
  region?: string
  age?: number
  stance?: string
}

export interface AgentDetailResponse {
  id: string
  agent_index: number
  population_id: string
  demographics: AgentDemographics
  big_five: Record<string, number>
  values: Record<string, any>
  life_event: string
  contradiction: string
  information_source: string
  local_context: string
  hidden_motivation: string
  speech_style: string
  shock_sensitivity: Record<string, number>
  memory_summary: string
  activation_response: Record<string, any> | null
  meeting_participant: MeetingParticipant | null
  meeting_contributions: MeetingArgument[]
  connections: AgentConnection[]
}

export interface ConversationRound {
  round: number
  arguments: MeetingArgument[]
}

export interface MeetingSynthesis {
  consensus_points?: string[]
  disagreement_points?: Array<Record<string, any>>
  key_insights?: string[]
  scenarios?: Array<Record<string, any>>
  stance_shifts?: Array<Record<string, any>>
  recommendations?: string[]
  overall_assessment?: string
}

interface ConversationsResponse {
  rounds: ConversationRound[]
  participants: MeetingParticipant[]
  synthesis: MeetingSynthesis
  total_rounds: number
}

export async function getSocialGraph(simId: string): Promise<SocialGraphResponse> {
  const { data } = await api.get(`/society/simulations/${simId}/social-graph`)
  return data
}

export async function getAgentDetail(simId: string, agentId: string): Promise<AgentDetailResponse> {
  const { data } = await api.get(`/society/simulations/${simId}/agents/${agentId}`)
  return data
}

export async function getConversations(
  simId: string,
  filters?: { round?: number; participant_index?: number },
): Promise<ConversationsResponse> {
  const { data } = await api.get(`/society/simulations/${simId}/conversations`, { params: filters })
  return data
}

// === Narrative API ===

export interface AgentQuote {
  agent_id: string
  agent_index: number
  occupation: string
  age: number
  region: string
  stance: string
  confidence: number
  quote: string
}

export interface NarrativeFinding {
  finding: string
  type: string
  supporting_evidence?: AgentQuote[]
  confidence: number
  probability?: number
  key_factors?: string[]
}

export interface NarrativeConsensus {
  point: string
  supporting_agents: AgentQuote[]
}

export interface NarrativeControversy {
  point: string
  positions: Array<Record<string, any>>
  supporting_quotes: AgentQuote[]
  opposing_quotes: AgentQuote[]
  demographic_split: Record<string, any>
}

export interface NarrativeRecommendation {
  recommendation: string
  evidence_chain: Array<Record<string, any>>
  supporting_agents: AgentQuote[]
}

export interface NarrativeResponse {
  executive_summary: string
  key_findings: NarrativeFinding[]
  consensus_areas: NarrativeConsensus[]
  controversy_areas: NarrativeControversy[]
  recommendations: NarrativeRecommendation[]
  stance_shifts: Array<Record<string, any>>
}

export async function getNarrative(simId: string): Promise<{ phase_data: NarrativeResponse }> {
  const { data } = await api.get(`/society/simulations/${simId}/narrative`)
  return data
}

export interface PropagationData {
  converged: boolean
  total_timesteps: number
  cluster_count: number
  clusters: Array<{ label: number; size: number; centroid: number[] }>
  echo_chamber: { homophily_index: number; polarization_index: number }
  stigmergy_topics: Array<{ topic: string; intensity: number }>
  prediction_market: Record<string, number>
  phase_transitions: Array<{ timestep: number; type: string }>
  tipping_points: Array<{ timestep: number; cascade_ratio: number }>
  aggregation_pre_independence?: Record<string, any> | null
  aggregation_post_independence?: Record<string, any>
  independence_re_aggregation?: {
    applied: boolean
    effective_sample_size_pre?: number | null
    effective_sample_size_post?: number | null
    stance_distribution_pre?: Record<string, number> | null
    stance_distribution_post?: Record<string, number> | null
  }
}

export async function getPropagation(simId: string): Promise<{ phase_data: PropagationData | null }> {
  const { data } = await api.get(`/society/simulations/${simId}/propagation`)
  return data
}

// === Transcript API ===

export interface TranscriptEntry {
  id: string
  phase: string
  round_number: number
  participant_name: string
  participant_role: string
  content_text: string
  stance: string
  stance_changed: boolean
  addressed_to: string
  created_at: string
}

export interface TranscriptResponse {
  simulation_id: string
  total_entries: number
  entries: TranscriptEntry[]
}

export async function getTranscript(
  simId: string,
  phase?: string,
  round?: number,
): Promise<TranscriptResponse> {
  const params: Record<string, string> = {}
  if (phase) params.phase = phase
  if (round != null) params.round = String(round)
  const { data } = await api.get(`/society/simulations/${simId}/transcript`, { params })
  return data
}

// === Sample Results API (API Key不要) ===

export async function getSampleResult(sampleId: string) {
  const { data } = await api.get(`/simulations/samples/${sampleId}`)
  return data
}
