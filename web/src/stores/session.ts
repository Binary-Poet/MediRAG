// 问答会话列表状态：侧栏与问答区共享（新建要清空问答区、点选要灌入历史、
// 提问完成后要刷新列表项的标题/时间/条数）。父子传参会形成环形依赖，故用 store。
import { defineStore } from 'pinia'
import {
  deleteSession as apiDelete, fetchSessionMessages, listSessions, setSessionFavorite,
} from '../api/chat'
import type { SessionSummary, StoredMessage } from '../types/chat'

export const useSessionStore = defineStore('session', {
  state: () => ({
    sessions: [] as SessionSummary[],
    total: 0,
    favoriteTotal: 0,
    favoriteOnly: false,
    activeId: '',
    loading: false,
  }),
  actions: {
    async refresh() {
      this.loading = true
      try {
        const r = await listSessions(this.favoriteOnly)
        this.sessions = r.sessions
        this.total = r.total
        this.favoriteTotal = r.favorite_total
      } finally {
        this.loading = false
      }
    },
    /** 收藏/取消：统计与「已收藏」筛选都在服务端，改完重新拉一次最省心 */
    async toggleFavorite(s: SessionSummary) {
      await setSessionFavorite(s.session_id, !s.favorite)
      await this.refresh()
    },
    /** 删除；不清 activeId——由调用方（Chat.vue）决定问答区是否复位 */
    async remove(id: string) {
      await apiDelete(id)
      await this.refresh()
    },
    loadMessages(id: string): Promise<StoredMessage[]> {
      return fetchSessionMessages(id)
    },
  },
})
