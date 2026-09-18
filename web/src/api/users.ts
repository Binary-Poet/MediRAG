// 账户管理接口：/api/users 全部要求管理员 Bearer token（后端 require_admin）。
import type { UserInfo } from './auth'

export interface CreateUserBody {
  username: string
  display_name: string
  role: string
  password: string
}

function authHeaders(token: string, json = false): Record<string, string> {
  const h: Record<string, string> = { Authorization: `Bearer ${token}` }
  if (json) h['Content-Type'] = 'application/json'
  return h
}

// 后端 422 的 detail 可能是数组（逐字段校验错误），直接 String(detail) 会得到 "[object Object]"。
async function fail(resp: Response, fallback: string): Promise<never> {
  const body = (await resp.json().catch(() => ({ detail: `HTTP ${resp.status}` }))) as { detail?: unknown }
  const d = body.detail
  const msg = Array.isArray(d)
    ? (d as Array<{ loc?: unknown[]; msg?: unknown }>)
        .map((x) => {
          const loc = x?.loc
          const field = loc && loc.length ? loc[loc.length - 1] : '字段'
          return `${field}: ${x?.msg ?? '非法值'}`
        })
        .join('；')
    : d
  throw new Error(typeof msg === 'string' && msg ? msg : fallback)
}

export async function listUsers(token: string): Promise<UserInfo[]> {
  const resp = await fetch('/api/users', { headers: authHeaders(token) })
  if (!resp.ok) return fail(resp, '账户列表加载失败')
  return (await resp.json()).items
}

export async function createUser(body: CreateUserBody, token: string): Promise<UserInfo> {
  const resp = await fetch('/api/users', {
    method: 'POST', headers: authHeaders(token, true), body: JSON.stringify(body),
  })
  if (!resp.ok) return fail(resp, '新建用户失败')
  return resp.json()
}

/** 管理员重置指定用户密码（登录页「忘记密码」的唯一落地点）。 */
export async function resetUserPassword(id: number, newPassword: string, token: string): Promise<void> {
  const resp = await fetch(`/api/users/${id}/password`, {
    method: 'PUT', headers: authHeaders(token, true),
    body: JSON.stringify({ new_password: newPassword }),
  })
  if (!resp.ok) return fail(resp, '重置密码失败')
}

export async function deleteUser(id: number, token: string): Promise<void> {
  const resp = await fetch(`/api/users/${id}`, { method: 'DELETE', headers: authHeaders(token) })
  if (!resp.ok) return fail(resp, '删除用户失败')
}
