export interface UserInfo { id: number; username: string; display_name: string; role: string }

export async function login(username: string, password: string): Promise<{ token: string; user: UserInfo }> {
  const resp = await fetch('/api/auth/login', {
    method: 'POST', headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ username, password }),
  })
  if (!resp.ok) {
    const detail = await resp.json().catch(() => ({ detail: `HTTP ${resp.status}` }))
    throw new Error(detail.detail ?? '登录失败')
  }
  return resp.json()
}

/** 自助注册：成功即返回 token（后端固定发放最低权限角色），前端无需再走一次登录 */
export async function register(
  username: string,
  password: string,
  display_name = '',
): Promise<{ token: string; user: UserInfo }> {
  const resp = await fetch('/api/auth/register', {
    method: 'POST', headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ username, password, display_name }),
  })
  if (!resp.ok) {
    const detail = await resp.json().catch(() => ({ detail: `HTTP ${resp.status}` }))
    throw new Error(detail.detail ?? '注册失败')
  }
  return resp.json()
}

export async function fetchMe(token: string): Promise<UserInfo> {
  const resp = await fetch('/api/auth/me', { headers: { Authorization: `Bearer ${token}` } })
  if (!resp.ok) throw new Error(`登录已失效（${resp.status}）`)
  return resp.json()
}

export async function changePassword(old_password: string, new_password: string, token: string): Promise<void> {
  const resp = await fetch('/api/auth/password', {
    method: 'PUT', headers: { 'Content-Type': 'application/json', Authorization: `Bearer ${token}` },
    body: JSON.stringify({ old_password, new_password }),
  })
  if (!resp.ok) {
    const detail = await resp.json().catch(() => ({ detail: `HTTP ${resp.status}` }))
    throw new Error(detail.detail ?? '修改失败')
  }
}

export async function updateProfile(display_name: string, token: string): Promise<UserInfo> {
  const resp = await fetch('/api/auth/profile', {
    method: 'PUT', headers: { 'Content-Type': 'application/json', Authorization: `Bearer ${token}` },
    body: JSON.stringify({ display_name }),
  })
  if (!resp.ok) {
    const detail = await resp.json().catch(() => ({ detail: `HTTP ${resp.status}` }))
    throw new Error(detail.detail ?? '修改失败')
  }
  return resp.json()
}
