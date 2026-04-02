import { test, expect } from '@playwright/test'

test('launches a simulation from the launchpad', async ({ page }) => {
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
