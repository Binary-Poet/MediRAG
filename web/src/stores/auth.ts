// 登录态：token / 当前用户，localStorage 持久化（刷新后不丢登录）。
import { defineStore } from 'pinia'
import { login as apiLogin, type UserInfo } from '../api/auth'

const TOKEN_KEY = 'medirag_token'
const USER_KEY = 'medirag_user'

export const useAuthStore = defineStore('auth', {
  state: () => ({
    token: localStorage.getItem(TOKEN_KEY) ?? '',
    // localStorage 可能被写入非法 JSON：直接 JSON.parse 会抛错，
    // 而守卫每次导航都会实例化 store —— 一旦抛错则导航永不 resolve（含 /login 自身），
    // 整个应用白屏且无法恢复。故解析失败即清掉脏数据并回落到未登录。
    user: (() => {
      try {
        return JSON.parse(localStorage.getItem(USER_KEY) ?? 'null') as UserInfo | null
      } catch {
        localStorage.removeItem(USER_KEY)
        return null
      }
    })(),
  }),
  actions: {
    async login(username: string, password: string) {
      const { token, user } = await apiLogin(username, password)
      this.token = token; this.user = user
      localStorage.setItem(TOKEN_KEY, token)
      localStorage.setItem(USER_KEY, JSON.stringify(user))
    },
    logout() {
      this.token = ''; this.user = null
      localStorage.removeItem(TOKEN_KEY); localStorage.removeItem(USER_KEY)
    },
    setUser(user: UserInfo) {
      this.user = user
      localStorage.setItem(USER_KEY, JSON.stringify(user))
    },
  },
})
