/** API 封装：阶段 1 问答接口（阶段 3 换 SSE 流式） */
import type { Reference } from '../types/chat'

export interface AskResponse {
  answer: string
  references: Reference[]
}

export async function askQuestion(question: string): Promise<AskResponse> {
  const resp = await fetch('/api/chat/ask', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ question }),
  })
  if (!resp.ok) {
    const detail = await resp.json().catch(() => ({ detail: `HTTP ${resp.status}` }))
    throw new Error(detail.detail ?? `请求失败（${resp.status}）`)
  }
  return resp.json()
}
