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
  onDone: (metrics: Record<string, number>) => void
}
