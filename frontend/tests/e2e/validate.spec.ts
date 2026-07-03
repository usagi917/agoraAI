import { expect, test } from '@playwright/test'

const distribution = {
  賛成: 0.15,
  条件付き賛成: 0.20,
  中立: 0.35,
  条件付き反対: 0.18,
  反対: 0.12,
}

test('runs validation flow and renders report overlays', async ({ page }) => {
  await page.route('**/api/validation/topics**', async (route) => {
    await route.fulfill({
      json: {
        preset: 'economy',
        topics: [
          {
            survey_id: 'boj_living_2024_economy_金利政策',
            theme: '金利政策',
            question: '現在の金融緩和政策を支持しますか',
            source: 'BOJ',
            survey_date: '2024-03',
            sample_size: 2182,
            source_origin: 'same_source_as_train',
            actual_distribution: distribution,
          },
        ],
      },
    })
  })

  await page.route('**/api/simulations', async (route) => {
    await route.fulfill({
      json: {
        id: 'sim-validate-e2e',
        mode: 'standard',
        status: 'queued',
        prompt_text: '金利政策',
        template_name: '',
        execution_profile: 'standard',
        evidence_mode: 'prefer',
        seed: 42,
        created_at: '2026-07-02T00:00:00Z',
      },
    })
  })

  await page.route('**/api/simulations/sim-validate-e2e/validation-report**', async (route) => {
    await route.fulfill({
      json: {
        simulation_id: 'sim-validate-e2e',
        preset: 'economy',
        predicted: distribution,
        actual: distribution,
        jsd: 0,
        emd: 0,
        brier: 0,
        ece: 0,
        verdict: 'hit',
        sample_reasons: [{ stance: '賛成', reason: '生活実感として支持できる。' }],
        evaluations: [
          {
            survey_id: 'boj_living_2024_economy_金利政策',
            theme: '金利政策',
            question: '',
            source: 'BOJ',
            predicted: distribution,
            actual: distribution,
            jsd: 0,
            emd: 0,
            brier: 0,
            ece: 0,
            verdict: 'hit',
          },
        ],
      },
    })
  })

  await page.addInitScript(() => {
    // @ts-expect-error test-only hook
    window.__AGENT_AI_E2E_EVENTS__ = [
      {
        eventType: 'society_selection_completed',
        payload: {
          selected_count: 1,
          total_population: 1,
          selected_agents: [
            { id: 'agent-1', agent_index: 1, name: 'Agent-1', occupation: '会社員', age: 40, region: '関東' },
          ],
        },
        delayMs: 10,
      },
      {
        eventType: 'society_activation_completed',
        payload: {
          aggregation: { stance_distribution: distribution },
          representative_count: 1,
          selected_agent_ids: ['agent-1'],
          usage: {},
        },
        delayMs: 20,
      },
      {
        eventType: 'simulation_completed',
        payload: { simulation_id: 'sim-validate-e2e', mode: 'unified' },
        delayMs: 30,
      },
    ]
  })

  await page.goto('/validate')
  await expect(page.getByLabel('検証トピック')).toContainText('金利政策')
  await page.getByRole('button', { name: '検証を実行' }).click()

  await expect(page).toHaveURL(/\/validate\/sim-validate-e2e$/)
  await expect(page.getByText('的中')).toBeVisible()
  await expect(page.getByText('分布比較')).toBeVisible()
  await expect(page.getByText('生活実感として支持できる。')).toBeVisible()
})
