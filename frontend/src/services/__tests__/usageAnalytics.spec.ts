import { beforeEach, describe, expect, it, vi } from 'vitest'

import {
  getUsageContext,
  installUsageAnalytics,
  trackUsageEvent,
} from '../usageAnalytics'

function createMemoryStorage(): Storage {
  const values = new Map<string, string>()
  return {
    get length() { return values.size },
    clear: () => values.clear(),
    getItem: key => values.get(key) ?? null,
    key: index => [...values.keys()][index] ?? null,
    removeItem: key => values.delete(key),
    setItem: (key, value) => values.set(key, String(value)),
  }
}

describe('usageAnalytics', () => {
  beforeEach(() => {
    vi.restoreAllMocks()
    Object.defineProperty(window, 'localStorage', {
      configurable: true,
      value: createMemoryStorage(),
    })
    Object.defineProperty(window, 'sessionStorage', {
      configurable: true,
      value: createMemoryStorage(),
    })
    vi.stubGlobal('fetch', vi.fn().mockResolvedValue(new Response(null, { status: 204 })))
  })

  it('keeps a stable anonymous visitor and rotates the browser-session id', () => {
    const first = getUsageContext()
    const second = getUsageContext()

    expect(second).toEqual(first)
    expect(first.visitorId).toMatch(/^[a-zA-Z0-9_-]{8,64}$/)
    expect(first.sessionId).toMatch(/^[a-zA-Z0-9_-]{8,64}$/)

    window.sessionStorage.clear()
    const nextSession = getUsageContext()

    expect(nextSession.visitorId).toBe(first.visitorId)
    expect(nextSession.sessionId).not.toBe(first.sessionId)
  })

  it('posts only structured anonymous event data', async () => {
    await trackUsageEvent('page_view', {
      path: '/sim/example/results?ignored=true',
      properties: { route_name: 'results' },
    })

    expect(fetch).toHaveBeenCalledTimes(1)
    const [url, options] = vi.mocked(fetch).mock.calls[0]
    const payload = JSON.parse(String(options?.body))
    expect(url).toBe('/api/analytics/events')
    expect(options).toEqual(expect.objectContaining({ method: 'POST', keepalive: true }))
    expect(payload).toEqual(expect.objectContaining({
      event_name: 'page_view',
      path: '/sim/example/results',
      properties: { route_name: 'results' },
    }))
    expect(payload.visitor_id).toBeTruthy()
    expect(payload.session_id).toBeTruthy()
    expect(payload).not.toHaveProperty('prompt_text')
  })

  it('records one session start and every route view', async () => {
    let afterEachHook: ((to: { path: string; name?: string }) => void) | undefined
    const router = {
      afterEach: vi.fn((hook) => {
        afterEachHook = hook
      }),
    }

    installUsageAnalytics(router)
    afterEachHook?.({ path: '/sim/demo/results', name: 'results' })
    afterEachHook?.({ path: '/', name: 'launchpad' })
    await Promise.resolve()

    const payloads = vi.mocked(fetch).mock.calls.map(([, options]) => (
      JSON.parse(String(options?.body))
    ))
    expect(payloads.map(payload => payload.event_name)).toEqual([
      'session_started',
      'page_view',
      'page_view',
    ])
    expect(payloads[1]).toEqual(expect.objectContaining({
      path: '/sim/demo/results',
      properties: { route_name: 'results' },
    }))
  })
})
