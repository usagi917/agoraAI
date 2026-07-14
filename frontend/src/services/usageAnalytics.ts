export type UsageEventName =
  | 'session_started'
  | 'page_view'
  | 'result_viewed'

export type UsageInputMethod =
  | 'manual'
  | 'wizard'
  | 'document'
  | 'document_with_prompt'
  | 'system'
  | 'unknown'

export interface UsageContext {
  visitorId: string
  sessionId: string
}

export interface UsageEventOptions {
  simulationId?: string
  path?: string
  properties?: Record<string, string | number | boolean | null>
}

interface AnalyticsRouter {
  afterEach: (
    hook: (to: { path: string; name?: unknown }) => void,
  ) => unknown
}

const VISITOR_ID_KEY = 'agentai.analytics.visitor_id'
const SESSION_ID_KEY = 'agentai.analytics.session_id'
const SESSION_STARTED_KEY = 'agentai.analytics.session_started'

function randomId(): string {
  if (globalThis.crypto?.randomUUID) {
    return globalThis.crypto.randomUUID()
  }
  return `anon_${Date.now().toString(36)}_${Math.random().toString(36).slice(2, 14)}`
}

function readOrCreate(storage: Storage, key: string): string {
  try {
    const existing = storage.getItem(key)
    if (existing) return existing

    const created = randomId()
    storage.setItem(key, created)
    return created
  } catch {
    return randomId()
  }
}

function normalizedPath(path?: string): string {
  const raw = path || window.location.pathname
  return raw.split('?', 1)[0].split('#', 1)[0].slice(0, 255)
}

export function getUsageContext(): UsageContext {
  return {
    visitorId: readOrCreate(window.localStorage, VISITOR_ID_KEY),
    sessionId: readOrCreate(window.sessionStorage, SESSION_ID_KEY),
  }
}

export async function trackUsageEvent(
  eventName: UsageEventName,
  options: UsageEventOptions = {},
): Promise<void> {
  const identity = getUsageContext()
  const payload = {
    event_name: eventName,
    visitor_id: identity.visitorId,
    session_id: identity.sessionId,
    simulation_id: options.simulationId,
    path: normalizedPath(options.path),
    properties: options.properties || {},
  }

  try {
    await fetch('/api/analytics/events', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(payload),
      credentials: 'same-origin',
      keepalive: true,
    })
  } catch {
    // Analytics must never block or break the user flow.
  }
}

export function installUsageAnalytics(router: AnalyticsRouter): void {
  let shouldRecordSessionStart = false
  try {
    shouldRecordSessionStart = window.sessionStorage.getItem(SESSION_STARTED_KEY) !== '1'
    if (shouldRecordSessionStart) {
      window.sessionStorage.setItem(SESSION_STARTED_KEY, '1')
    }
  } catch {
    shouldRecordSessionStart = true
  }

  if (shouldRecordSessionStart) {
    void trackUsageEvent('session_started')
  }

  router.afterEach((to) => {
    void trackUsageEvent('page_view', {
      path: to.path,
      properties: { route_name: String(to.name || 'unknown') },
    })
  })
}
