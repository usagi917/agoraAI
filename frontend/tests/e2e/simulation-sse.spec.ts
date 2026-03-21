import { test, expect } from '@playwright/test'

test('reacts to verification SSE events on the simulation page', async ({ page }) => {
  await page.addInitScript(() => {
    // @ts-expect-error test-only hook
    window.__AGENT_AI_E2E_EVENTS__ = [
      {
        eventType: 'pipeline_stage_started',
        payload: { stage: 'single' },
        delayMs: 10,
      },
      {
        eventType: 'verification_started',
        payload: { scope: 'pipeline', target: 'final_report' },
        delayMs: 30,
      },
    ]
    // @ts-expect-error test-only hook
    window.__AGENT_AI_E2E_SIMULATION__ = {
      id: 'sim-live',
      project_id: null,
      mode: 'pipeline',
      prompt_text: 'prompt only',
      template_name: 'business_analysis',
      execution_profile: 'standard',
      colony_count: 1,
      deep_colony_count: 0,
      status: 'running',
      error_message: '',
      pipeline_stage: 'pending',
      stage_progress: {},
      run_id: 'run-1',
      swarm_id: null,
      metadata: {},
      created_at: '2026-03-21T00:00:00Z',
      started_at: '2026-03-21T00:00:00Z',
      completed_at: null,
    }
  })

  await page.goto('/__e2e__/sse')

  await page.waitForFunction(() => {
    // @ts-expect-error test-only hook
    return window.__AGENT_AI_E2E_LAST_EVENT__ === 'verification_started'
  })
})
