export interface InferenceConfig {
  semantic_k: number; keyword_k: number; fuse_candidate: number
  final_evidence: number; rrf_k: number
  model: string; answer_temp: number; query_temp: number
}

export async function getConfig(): Promise<InferenceConfig> {
  const resp = await fetch('/api/config')
  if (!resp.ok) throw new Error(`配置加载失败（${resp.status}）`)
  return (await resp.json()).items
}

export async function saveConfig(body: InferenceConfig): Promise<InferenceConfig> {
  const resp = await fetch('/api/config', {
    method: 'PUT',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(body),
  })
  if (!resp.ok) {
    const detail = await resp.json().catch(() => ({ detail: `HTTP ${resp.status}` }))
    throw new Error(detail.detail ?? '保存失败')
  }
  return resp.json()
}
