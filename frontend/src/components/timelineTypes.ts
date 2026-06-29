export interface AuditEvent {
  id: string
  agent_id: string
  agent_name: string
  event_type: string
  reasoning: string
  timestamp: string
}

export interface OpinionShift {
  agent_name: string
  before: string
  after: string
  reasoning: string
}
