// 运行概览接口类型：字段与后端 GET /api/stats/overview 六键一一对应
export interface TrendPoint { date: string; count: number }
export interface NamedValue { name: string; value: number }
export interface QualityStats {
  total: number; fallback_n: number; normal_n: number
  useful: number; useless: number
  satisfaction: number; success_rate: number
}
export interface OverviewData {
  trend: TrendPoint[]
  role_dist: NamedValue[]
  topic_dist: NamedValue[]
  status_dist: NamedValue[]
  quality: QualityStats
  config: Record<string, number | string>
}
