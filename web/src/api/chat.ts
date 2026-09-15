/** SSE 流式问答（fetch ReadableStream 解析，EventSource 不支持 POST） */
import type { StreamHandlers } from '../types/chat'

export async function streamChat(
  question: string,
  handlers: StreamHandlers,
  sessionId?: string,
): Promise<void> {
  const resp = await fetch('/api/chat/stream', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ question, session_id: sessionId }),
  })
  if (!resp.ok || !resp.body) {
    const detail = await resp.json().catch(() => ({ detail: `HTTP ${resp.status}` }))
    throw new Error(detail.detail ?? `请求失败（${resp.status}）`)
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
    case 'done': h.onDone(data.metrics ?? {}); break
    default: break
  }
}
