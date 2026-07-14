import { expect, test } from '@playwright/test'

test('social graph timeline, graph focus, and inspector stay synchronized', async ({ page }) => {
  await page.goto('/__dev__/graph')

  await expect(page.getByTestId('phase-label')).toContainText('completed', { timeout: 10_000 })
  await expect(page.getByTestId('activity-timeline').locator('.kind-dialogue')).toBeVisible()

  await page.getByTestId('activity-timeline').locator('.kind-stance_shift').click()
  await expect(page.getByTestId('node-inspector')).toContainText('条件付き賛成')
  await expect(page.locator('.live-state')).toContainText('Replay')

  await page.getByTestId('activity-timeline').locator('.kind-relationship_changed').click()
  await expect(page.locator('.workspace-inspector')).toContainText('friend')
  await expect(page.locator('.workspace-inspector')).toContainText('0.80')

  await page.getByTestId('return-live').click()
  await expect(page.locator('.live-state')).toContainText('Live')
})

test('10k population layer remains interactive and honors reduced motion', async ({ page }) => {
  await page.emulateMedia({ reducedMotion: 'reduce' })
  await page.goto('/__dev__/graph?pop=10000')

  await expect(page.getByTestId('phase-label')).toContainText('completed', { timeout: 15_000 })
  await expect(page.getByTestId('social-graph-surface')).toBeVisible()

  const frames = await page.evaluate(async () => {
    let count = 0
    const startedAt = performance.now()
    await new Promise<void>((resolve) => {
      const tick = (now: number) => {
        count += 1
        if (now - startedAt >= 1_000) resolve()
        else requestAnimationFrame(tick)
      }
      requestAnimationFrame(tick)
    })
    return count
  })

  expect(frames).toBeGreaterThanOrEqual(30)
})
