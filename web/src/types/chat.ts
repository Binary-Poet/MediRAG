export interface Reference {
  chunk_id: string
  title: string
  doc_name: string
  chapter: string
  page_no: number
  score: number
}

export interface GraphFact {
  source: string
  relation: string
  target: string
  source_type: string
  target_type: string
}

export interface StepEvent {
  step: string            // understand | retrieve | reflect | fuse | rerank（前端另用 generate 标记生成中）
  raw?: string
  rewritten?: string
  entities?: string[]
  intent?: string
  sub_query_n?: number    // 查询分解出的子查询数（复合意图 > 1）
  sub_queries?: string[]  // 子查询词摘要，悬浮展示分解结果
  path_template?: string | null   // 图谱走的定向路径模板，为空即无向邻居
  graph_dropped_n?: number        // 锚定过滤剔除的旁支事实数
  matched_queries?: number[]
  vector_n?: number
  keyword_n?: number
  graph_n?: number
  entity_n?: number
  candidate_n?: number
  method?: string
  evidence_n?: number
  confidence?: number
  status?: string
  round?: number
  reason?: string
}

export interface StreamHandlers {
  onStep: (ev: StepEvent) => void
  onToken: (text: string) => void
  onReferences: (refs: Reference[], graphFacts: GraphFact[]) => void
  onSafety: (type: string, message: string) => void
  onError?: (detail: string) => void
  onDone: (data: DonePayload) => void
}

export interface SessionSummary {
  session_id: string
  title: string
  favorite: boolean
  message_count: number
  updated_at: string   // ISO，末尾带 Z（UTC）
}

export interface StoredMessage {
  seq: number
  role: 'user' | 'assistant'
  content: string
  payload: {
    trace?: StepEvent[]
    references?: Reference[]
    graph_facts?: GraphFact[]
    safety?: { type: string; message: string } | null
  } | null
  created_at: string
}

export interface SessionListResponse {
  sessions: SessionSummary[]
  total: number
  favorite_total: number
}

/** done 事件载荷：message_id 即会话 id，前端据此认领本轮新建的会话；
    user_seq 为本轮提问的 seq，撤回时用它精确删掉指定轮 */
export interface DonePayload {
  message_id?: string
  metrics?: Record<string, number>
  user_seq?: number
  assistant_seq?: number
}
