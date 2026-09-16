/** 共享鉴权头：写端点需带 Bearer（token 存 localStorage，非组件上下文无法直接取 store）。 */
const TOKEN_KEY = 'medirag_token'

export function authHeaders(extra: Record<string, string> = {}): Record<string, string> {
  const token = localStorage.getItem(TOKEN_KEY)
  return token ? { ...extra, Authorization: `Bearer ${token}` } : { ...extra }
}
