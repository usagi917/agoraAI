export type ResultsPrimaryView = 'report' | 'scenarios' | 'decision_brief'
export type ResultsSecondaryTab = 'pm' | 'society' | 'evidence' | 'transcript'
export type LivePrimaryView = 'graph' | 'society'
export type LiveSecondaryTab = 'progress' | 'debate' | 'activity' | 'society' | 'colonies' | 'thinking' | 'dialogue'

export interface ResultsLayoutContext {
  mode?: string | null
  hasScenarios: boolean
  hasDecisionBrief: boolean
  hasPmBoard: boolean
  hasSociety: boolean
  hasEvidence: boolean
  hasTranscript?: boolean
}

export interface LiveLayoutContext {
  mode?: string | null
  hasColonies: boolean
  hasActivity: boolean
  hasCognitiveData?: boolean
}

const SCENARIO_FIRST_MODES = new Set([
  'pipeline',
  'swarm',
  'hybrid',
  'society_first',
  'meta_simulation',
  'unified',
])

const SOCIETY_MODES = new Set([
  'society',
  'society_first',
  'meta_simulation',
  'unified',
])

export function getResultsPrimaryView(context: ResultsLayoutContext): ResultsPrimaryView {
  const mode = context.mode || ''

  if (mode === 'pm_board' && context.hasDecisionBrief) {
    return 'decision_brief'
  }

  if (mode === 'pm_board') {
    return 'report'
  }

  if (mode === 'single') {
    return 'report'
  }

  if (SCENARIO_FIRST_MODES.has(mode) && context.hasScenarios) {
    return 'scenarios'
  }

  if (context.hasDecisionBrief) {
    return 'decision_brief'
  }

  if (context.hasScenarios) {
    return 'scenarios'
  }

  return 'report'
}

export function getResultsSecondaryTabs(context: ResultsLayoutContext): ResultsSecondaryTab[] {
  const mode = context.mode || ''
  const tabs: ResultsSecondaryTab[] = []

  if (context.hasSociety && SOCIETY_MODES.has(mode)) {
    tabs.push('society')
  }

  if ((context.hasTranscript ?? false) && SOCIETY_MODES.has(mode)) {
    tabs.push('transcript')
  }

  if (context.hasPmBoard && mode !== 'pm_board') {
    tabs.push('pm')
  }

  if (context.hasEvidence) {
    tabs.push('evidence')
  }

  return tabs
}

export function getDefaultResultsSecondaryTab(context: ResultsLayoutContext): ResultsSecondaryTab {
  const tabs = getResultsSecondaryTabs(context)
  if (tabs.includes('society') && SOCIETY_MODES.has(context.mode || '')) {
    return 'society'
  }
  return tabs[0] || 'society'
}

export function getLivePrimaryView(context: LiveLayoutContext): LivePrimaryView {
  return SOCIETY_MODES.has(context.mode || '') ? 'society' : 'graph'
}

export function getLiveSecondaryTabs(context: LiveLayoutContext): LiveSecondaryTab[] {
  const tabs: LiveSecondaryTab[] = ['progress']

  // Debate cards always available (theater events)
  tabs.push('debate')

  if (SOCIETY_MODES.has(context.mode || '')) {
    tabs.push('society')
  }

  if (context.hasActivity) {
    tabs.push('activity')
  }

  if (context.hasColonies) {
    tabs.push('colonies')
  }

  if (context.hasCognitiveData) {
    tabs.push('thinking')
  }

  if (SOCIETY_MODES.has(context.mode || '') || context.hasCognitiveData) {
    tabs.push('dialogue')
  }

  return tabs
}

export function getDefaultLiveSecondaryTab(context: LiveLayoutContext): LiveSecondaryTab {
  const tabs = getLiveSecondaryTabs(context)
  if (tabs.includes('society')) {
    return 'society'
  }
  return tabs[0] || 'progress'
}
