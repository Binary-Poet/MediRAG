import { authHeaders } from './http'

export interface InferenceConfig {
  semantic_k: number; keyword_k: number; fuse_candidate: number
  final_evidence: number; rrf_k: number
  model: string; answer_temp: number; query_temp: number
}

export interface ConfigResponse {
  items: InferenceConfig
  /** 按后端 Key 就绪情况计算的可选模型（未就绪的下拉选项置灰）。 */
  available_models: string[]
}

export async function getConfig(): Promise<ConfigResponse> {
  const resp = await fetch('/api/config')
  if (!resp.ok) throw new Error(`配置加载失败（${resp.status}）`)
  return resp.json()
}

export async function saveConfig(body: InferenceConfig): Promise<InferenceConfig> {
  const resp = await fetch('/api/config', {
    method: 'PUT',
    headers: authHeaders({ 'Content-Type': 'application/json' }),
    body: JSON.stringify(body),
  })
  if (!resp.ok) {
    // 后端 422 的 detail 可能是数组（逐字段校验错误），需拼成可读文案，
    // 否则直接 String(detail) 会得到 "[object Object]"。
    const body = await resp.json().catch(() => ({ detail: `HTTP ${resp.status}` }))
    const d = (body as { detail?: unknown }).detail
    const msg = Array.isArray(d)
      ? (d as Array<{ loc?: unknown[]; msg?: unknown }>)
          .map((x) => {
            const loc = x?.loc
            const field = loc && loc.length ? loc[loc.length - 1] : '字段'
            return `${field}: ${x?.msg ?? '非法值'}`
          })
          .join('；')
      : (d ?? '保存失败')
    throw new Error(String(msg))
  }
  return resp.json()
}
