import { test, expect } from '@playwright/test'

test('launches a simulation from the launchpad', async ({ page }) => {
  await page.addInitScript(() => {
    // Keep the post-launch route self-contained so this test stays stable
    // when the full E2E suite runs in parallel workers.
    // @ts-expect-error test-only hook
    window.__AGENT_AI_E2E_SIMULATION__ = {
      id: 'sim-e2e-1',
      project_id: null,
      mode: 'pipeline',
      prompt_text: 'EV battery market analysis',
      template_name: 'business_analysis',
      execution_profile: 'standard',
      colony_count: 1,
      deep_colony_count: 0,
      status: 'running',
      error_message: '',
      pipeline_stage: 'pending',
      stage_progress: {},
      run_id: 'run-e2e-1',
      swarm_id: null,
      metadata: {},
      created_at: '2026-04-03T00:00:00Z',
      started_at: '2026-04-03T00:00:00Z',
      completed_at: null,
    }
    // @ts-expect-error test-only hook
    window.__AGENT_AI_E2E_EVENTS__ = [
      {
        eventType: 'run_started',
        payload: { total_rounds: 3 },
        delayMs: 0,
      },
    ]
  })

  await page.route('**/api/health', async (route) => {
    await route.fulfill({
      json: {
        status: 'ok',
        version: '1.0.0',
        llm_provider: 'openai',
        live_simulation_available: true,
        live_simulation_message: '',
      },
    })
  })
  await page.route('**/api/templates', async (route) => {
    await route.fulfill({
      json: [
        {
          id: 'tmpl-1',
          name: 'business_analysis',
          display_name: 'Business Analysis',
          description: 'desc',
          category: 'strategy',
        },
      ],
    })
  })
  await page.route('**/api/society/populations', async (route) => {
    await route.fulfill({
      json: [
        { id: 'pop-e2e-1', agent_count: 1000, status: 'ready' },
      ],
    })
  })
  await page.route('**/api/simulations', async (route) => {
    if (route.request().method() === 'GET') {
      await route.fulfill({ json: [] })
      return
    }
    await route.fulfill({
      json: { id: 'sim-e2e-1', status: 'queued' },
    })
  })

  await page.goto('/')
  await page.getByLabel('分析プロンプト').fill('EV battery market analysis')
  await expect(page.getByTestId('launch-button')).toBeEnabled()
  await page.getByTestId('launch-button').click()

  await expect(page).toHaveURL(/\/sim\/sim-e2e-1$/)
})
