import type { DocList, DocItem } from '../types/knowledge'

export async function listDocuments(): Promise<DocList> {
  const resp = await fetch('/api/documents')
  if (!resp.ok) throw new Error(`列表加载失败（${resp.status}）`)
  return resp.json()
}

export async function uploadDocument(file: File, topic: string) {
  const form = new FormData()
  form.append('file', file)
  form.append('topic', topic)
  const resp = await fetch('/api/documents', { method: 'POST', body: form })
  if (!resp.ok) {
    const detail = await resp.json().catch(() => ({ detail: `HTTP ${resp.status}` }))
    throw new Error(detail.detail ?? '上传失败')
  }
  return resp.json()
}

export async function parseStatus(id: number): Promise<Pick<DocItem, 'id' | 'status' | 'chunk_count' | 'error_message'>> {
  const resp = await fetch(`/api/documents/${id}/parse-status`)
  if (!resp.ok) throw new Error(`状态查询失败（${resp.status}）`)
  return resp.json()
}

export function humanSize(bytes: number): string {
  if (bytes < 1024) return `${bytes} B`
  if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)} KB`
  return `${(bytes / 1024 / 1024).toFixed(1)} MB`
}