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

export interface Trace {
  understand: { raw: string; rewritten: string; entities: string[] }
  retrieve: { vector_n: number; keyword_n: number; graph_n: number; entity_n: number }
  fuse: { candidate_n: number; method: string }
  rerank: { evidence_n: number; confidence: number; status: string }
}