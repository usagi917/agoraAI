import { test, expect } from '@playwright/test'

test('shows unsupported strict-evidence state in results', async ({ page }) => {
  await page.route('**/api/simulations/sim-strict', async (route) => {
    await route.fulfill({
      json: {
        id: 'sim-strict',
        project_id: null,
        mode: 'single',
        prompt_text: 'prompt only',
        template_name: 'business_analysis',
        execution_profile: 'standard',
        colony_count: 1,
        deep_colony_count: 0,
        status: 'completed',
        error_message: '',
        pipeline_stage: 'completed',
        stage_progress: {},
        run_id: 'run-1',
        swarm_id: null,
        metadata: {},
        created_at: '2026-03-21T00:00:00Z',
        started_at: null,
        completed_at: '2026-03-21T00:01:00Z',
      },
    })
  })
  await page.route('**/api/simulations/sim-strict/report', async (route) => {
    await route.fulfill({
      json: {
        type: 'single',
        id: 'report-1',
        run_id: 'run-1',
        content: 'short report',
        sections: {},
        status: 'completed',
        evidence_refs: [],
        run_config: { evidence_mode: 'strict', trust_mode: 'strict' },
        verification: {
          status: 'failed',
          score: 0.4,
          issues: ['unsupported_quality'],
          warnings: [],
          metrics: {},
        },
        quality: {
          status: 'unsupported',
          fallback_used: false,
          fallback_reason: '',
          calibration_status: 'uncalibrated',
          evidence_mode: 'strict',
          trust_level: 'low_trust',
          evidence_available: true,
          evidence_refs_count: 1,
          document_refs_count: 0,
          prompt_refs_count: 1,
          unsupported_reason: 'strict_document_evidence_required',
          issues: ['strict_document_evidence_required'],
        },
      },
    })
  })
  await page.route('**/api/simulations/sim-strict/graph/history', async (route) => {
    await route.fulfill({ json: [] })
  })
  await page.route('**/api/simulations/sim-strict/graph', async (route) => {
    await route.fulfill({ json: { nodes: [], edges: [] } })
  })

  await page.goto('/sim/sim-strict/results')

  await expect(page.getByTestId('quality-banner')).toContainText('Unsupported')
  await expect(page.getByTestId('quality-banner')).toContainText('strict_document_evidence_required')
})
