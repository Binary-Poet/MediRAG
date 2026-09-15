export const TOPICS = ['内科', '外科', '儿科', '妇科', '情志脑病', '筋骨伤科', '皮肤病证', '五官病证'] as const
export type Topic = typeof TOPICS[number]

export interface DocItem {
  id: number
  name: string
  file_type: string
  size: number
  topic: string
  status: '上传中' | '处理中' | '就绪' | '失败'
  chunk_count: number
  error_message: string
  uploaded_at: string
}

export interface DocList {
  total: number
  total_chunks: number
  items: DocItem[]
}