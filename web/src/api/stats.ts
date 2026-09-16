import type { OverviewData } from '../types/stats'

export async function getOverview(): Promise<OverviewData> {
  const resp = await fetch('/api/stats/overview')
  if (!resp.ok) throw new Error(`统计加载失败（${resp.status}）`)
  return resp.json()
}
