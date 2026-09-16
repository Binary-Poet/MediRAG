import type { CandidateEdge, CandidateNode, GraphEntity, GraphLink, GraphNode } from '../types/graph'

async function getJson<T>(url: string): Promise<T> {
  const resp = await fetch(url)
  if (!resp.ok) throw new Error(`${url} 失败（${resp.status}）`)
  return resp.json()
}

export const searchEntities = (entity: string, type = '') =>
  getJson<{ items: GraphEntity[] }>(`/api/graph/search?entity=${encodeURIComponent(entity)}&type=${encodeURIComponent(type)}`)

export const getNeighbors = (name: string, hop = 2) =>
  getJson<{ nodes: GraphNode[]; links: GraphLink[] }>(`/api/graph/neighbors?name=${encodeURIComponent(name)}&hop=${hop}`)

export const getEntityDetail = (name: string) =>
  getJson<GraphEntity & { desc: string; source: string }>(`/api/graph/entities/${encodeURIComponent(name)}`)

export const listCandidates = () =>
  getJson<{ nodes: CandidateNode[]; edges: CandidateEdge[] }>('/api/graph/candidates')

async function post(url: string, body: unknown) {
  const resp = await fetch(url, { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(body) })
  if (!resp.ok) {
    const detail = await resp.json().catch(() => ({ detail: `HTTP ${resp.status}` }))
    throw new Error(detail.detail ?? '操作失败')
  }
  return resp.json()
}

export const approveCandidate = (body: Record<string, string>) => post('/api/graph/candidates/approve', body)
export const rejectCandidate = (body: Record<string, string>) => post('/api/graph/candidates/reject', body)

/** 重新导入基础数据（幂等 MERGE，不破坏已发布/候选状态——规格 P0-5）。 */
export const reimportGraph = (): Promise<{ imported: { nodes: number; edges: number } }> =>
  fetch('/api/graph/import', { method: 'POST' }).then(async (resp) => {
    if (!resp.ok) throw new Error(`导入失败（${resp.status}）`)
    return resp.json()
  })
