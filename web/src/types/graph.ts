export interface GraphEntity {
  name: string
  type: string
  alias: string
  status: string
}

export interface GraphNode { id: string; name: string; category: string; status: string }
export interface GraphLink { source: string; target: string; relation: string; status: string }

export interface CandidateNode { name: string; type: string; source_doc: string }
export interface CandidateEdge {
  source: string; relation: string; target: string
  source_type: string; target_type: string; source_doc: string
}

/* 节点类型 → theme token 名（颜色在组件内从 theme.ts 取） */
export const NODE_TYPES = ['方剂', '中药', '证候', '症状', '功效', '禁忌'] as const