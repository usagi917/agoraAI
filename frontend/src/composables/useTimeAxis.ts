import { ref } from 'vue'
import { getTimeAxis, type TimeAxisReport } from '../api/client'

/**
 * useTimeAxis — Composable wrapping the time-axis (t0..t5) report endpoint.
 *
 * Single concern: data fetching + state management for the time-axis view.
 * Gracefully handles 404 (no time-axis result available yet) by leaving
 * `report` as `null` and not setting `error`.
 */
export function useTimeAxis() {
  const report = ref<TimeAxisReport | null>(null)
  const loading = ref(false)
  const error = ref<string | null>(null)

  async function fetch(simId: string): Promise<void> {
    if (!simId) return
    loading.value = true
    error.value = null
    try {
      report.value = await getTimeAxis(simId)
    } catch (e: any) {
      // 404 → time-axis not available yet; treat as a soft absence, not an error.
      const status = e?.response?.status
      if (status === 404) {
        report.value = null
      } else {
        error.value = e?.message ?? 'time-axis レポートの取得に失敗しました'
      }
    } finally {
      loading.value = false
    }
  }

  return { report, loading, error, fetch }
}
