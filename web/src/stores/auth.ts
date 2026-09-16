// 登录态：token / 当前用户，localStorage 持久化（刷新后不丢登录）。
import { defineStore } from 'pinia'
import { login as apiLogin, type UserInfo } from '../api/auth'

const TOKEN_KEY = 'medirag_token'
const USER_KEY = 'medirag_user'

export const useAuthStore = defineStore('auth', {
  state: () => ({
    token: localStorage.getItem(TOKEN_KEY) ?? '',
    user: JSON.parse(localStorage.getItem(USER_KEY) ?? 'null') as UserInfo | null,
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
  },
})
