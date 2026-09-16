/** SSE 流式问答（fetch ReadableStream 解析，EventSource 不支持 POST） */
import { authHeaders } from './http'
import type {
  SessionListResponse, StoredMessage, StreamHandlers,
} from '../types/chat'

export async function streamChat(
  question: string,
  handlers: StreamHandlers,
  sessionId?: string,
): Promise<void> {
  const resp = await fetch('/api/chat/stream', {
    method: 'POST',
    headers: authHeaders({ 'Content-Type': 'application/json' }),
    body: JSON.stringify({ question, session_id: sessionId }),
  })
  if (!resp.ok || !resp.body) {
    throw new Error(await detail(resp))
  }
  const reader = resp.body.getReader()
  const decoder = new TextDecoder('utf-8')
  let buf = ''
  while (true) {
    const { done, value } = await reader.read()
    if (done) break
    buf += decoder.decode(value, { stream: true })
    const frames = buf.split('\n\n')
    buf = frames.pop() ?? ''
    for (const frame of frames) {
      const evt = parseSseFrame(frame)
      if (!evt) continue
      dispatch(evt, handlers)
    }
  }
}

function parseSseFrame(frame: string): { event: string; data: string } | null {
  let event = 'message'
  const dataLines: string[] = []
  for (const line of frame.split('\n')) {
    if (line.startsWith('event:')) event = line.slice(6).trim()
    else if (line.startsWith('data:')) dataLines.push(line.slice(5).trim())
  }
  if (!dataLines.length) return null
  return { event, data: dataLines.join('\n') }
}

function dispatch(evt: { event: string; data: string }, h: StreamHandlers) {
  let data: any // SSE data 为非定形 JSON，各 case 自行取字段
  try {
    data = JSON.parse(evt.data || 'null')
  } catch {
    return // 坏帧跳过，不中断整个流
  }
  switch (evt.event) {
    case 'step': h.onStep(data); break
    case 'token': h.onToken(data.text ?? ''); break
    case 'references': h.onReferences(data.docs ?? [], data.graph_facts ?? []); break
    case 'safety': h.onSafety(data.type, data.message ?? ''); break
    case 'error': h.onError?.(String(data.detail ?? '未知错误')); break
    case 'done': h.onDone(data); break
    default: break
  }
}

async function detail(resp: Response): Promise<string> {
  const body = await resp.json().catch(() => ({ detail: `HTTP ${resp.status}` }))
  return body.detail ?? `请求失败（${resp.status}）`
}

export async function listSessions(favoriteOnly = false): Promise<SessionListResponse> {
  const resp = await fetch(`/api/chat/sessions?favorite=${favoriteOnly}`, { headers: authHeaders() })
  if (!resp.ok) throw new Error(await detail(resp))
  return resp.json()
}

export async function setSessionFavorite(sessionId: string, favorite: boolean): Promise<void> {
  const resp = await fetch(`/api/chat/sessions/${sessionId}`, {
    method: 'PATCH',
    headers: authHeaders({ 'Content-Type': 'application/json' }),
    body: JSON.stringify({ favorite }),
  })
  if (!resp.ok) throw new Error(await detail(resp))
}

export async function deleteSession(sessionId: string): Promise<void> {
  const resp = await fetch(`/api/chat/sessions/${sessionId}`, {
    method: 'DELETE', headers: authHeaders(),
  })
  if (!resp.ok) throw new Error(await detail(resp))
}

export async function fetchSessionMessages(sessionId: string): Promise<StoredMessage[]> {
  const resp = await fetch(`/api/chat/sessions/${sessionId}/messages`, { headers: authHeaders() })
  if (!resp.ok) throw new Error(await detail(resp))
  return (await resp.json()).messages
}
