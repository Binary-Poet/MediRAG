import type { DocList, DocItem } from '../types/knowledge'
import { authHeaders } from './http'

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

export type DocDetail = DocItem & { stored_file: string }

export async function getDocument(id: number): Promise<DocDetail> {
  const resp = await fetch(`/api/documents/${id}`)
  if (!resp.ok) throw new Error(`详情加载失败（${resp.status}）`)
  return resp.json()
}

/** 下载地址（供 <a :href> / 临时 a 标签触发 attachment 下载） */
export function downloadUrl(id: number): string {
  return `/api/documents/${id}/download`
}

export async function renameDocument(id: number, name: string): Promise<DocItem> {
  const resp = await fetch(`/api/documents/${id}`, {
    method: 'PUT', headers: authHeaders({ 'Content-Type': 'application/json' }),
    body: JSON.stringify({ name }),
  })
  if (!resp.ok) {
    const detail = await resp.json().catch(() => ({ detail: `HTTP ${resp.status}` }))
    throw new Error(detail.detail ?? '重命名失败')
  }
  return resp.json()
}

/** 删除文档（鉴权写端点，需带 Bearer）。 */
export async function deleteDocument(id: number): Promise<{ deleted: number; removed_chunks: number }> {
  const resp = await fetch(`/api/documents/${id}`, { method: 'DELETE', headers: authHeaders() })
  if (!resp.ok) {
    const detail = await resp.json().catch(() => ({ detail: `HTTP ${resp.status}` }))
    throw new Error(detail.detail ?? '删除失败')
  }
  return resp.json()
}

export function humanSize(bytes: number): string {
  if (bytes < 1024) return `${bytes} B`
  if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)} KB`
  return `${(bytes / 1024 / 1024).toFixed(1)} MB`
}
