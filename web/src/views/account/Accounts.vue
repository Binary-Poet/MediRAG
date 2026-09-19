<script setup lang="ts">
// 账户管理（P2）：列表 / 新建 / 删除。后端 /api/users 仅管理员可访问（require_admin）。
import { onMounted, reactive, ref } from 'vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import {
  createUser, deleteUser, listUsers, resetUserPassword, type CreateUserBody,
} from '../../api/users'
import type { UserInfo } from '../../api/auth'
import { useAuthStore } from '../../stores/auth'
import { theme } from '../../styles/theme'

// 与后端 app/models/user.py 的 ROLES 一致
const ROLE_OPTIONS = ['管理员', '中医药从业者', '知识用户']

// 角色徽章按权限分级：三档角色原先同一个绿色，扫一眼分不出权限高低（与主布局侧栏同口径）
const ROLE_TAG: Record<string, 'warning' | 'primary' | 'info'> = {
  管理员: 'warning', 中医药从业者: 'primary', 知识用户: 'info',
}
function roleTag(role: string): 'warning' | 'primary' | 'info' {
  return ROLE_TAG[role] ?? 'info'
}

const auth = useAuthStore()
const users = ref<UserInfo[]>([])
const loading = ref(false)
const dialogVisible = ref(false)
const creating = ref(false)

const form = reactive<CreateUserBody>({ username: '', display_name: '', role: '知识用户', password: '' })

async function refresh() {
  loading.value = true
  try {
    users.value = await listUsers(auth.token)
  } catch (e) {
    users.value = []
    ElMessage.error((e as Error).message)
  } finally {
    loading.value = false
  }
}

onMounted(refresh)

function openDialog() {
  Object.assign(form, { username: '', display_name: '', role: '知识用户', password: '' })
  dialogVisible.value = true
}

async function submitCreate() {
  if (!form.username || !form.password) {
    ElMessage.warning('请填写用户名与密码')
    return
  }
  // 后端 display_name 允许空串，但空姓名会让侧栏/档案页显示空白，故前端强制必填
  if (!form.display_name.trim()) {
    ElMessage.warning('请输入姓名')
    return
  }
  creating.value = true
  try {
    await createUser({ ...form }, auth.token)
    ElMessage.success('已新建用户')
    dialogVisible.value = false
    await refresh()
  } catch (e) {
    ElMessage.error((e as Error).message)
  } finally {
    creating.value = false
  }
}

// 重置密码：登录页「忘记密码」的落地点（系统无邮件通道，只能管理员代为重置）
const resetVisible = ref(false)
const resetting = ref(false)
const resetTarget = ref<UserInfo | null>(null)
const resetPassword = ref('')

function openReset(row: UserInfo) {
  resetTarget.value = row
  resetPassword.value = ''
  resetVisible.value = true
}

async function submitReset() {
  const row = resetTarget.value
  if (!row) return
  if (resetPassword.value.length < 6) {
    ElMessage.warning('密码至少 6 位')
    return
  }
  resetting.value = true
  try {
    await resetUserPassword(row.id, resetPassword.value, auth.token)
    ElMessage.success(`已重置「${row.display_name || row.username}」的密码`)
    resetVisible.value = false
  } catch (e) {
    ElMessage.error((e as Error).message)
  } finally {
    resetting.value = false
  }
}

async function removeUser(row: UserInfo) {
  try {
    await ElMessageBox.confirm(`确定删除用户「${row.display_name || row.username}」？`, '删除确认', {
      type: 'warning',
      confirmButtonText: '删除',
      cancelButtonText: '取消',
    })
  } catch {
    return // 取消删除
  }
  try {
    await deleteUser(row.id, auth.token)
    ElMessage.success('已删除')
    await refresh()
  } catch (e) {
    ElMessage.error((e as Error).message)
  }
}
</script>

<template>
  <div class="accounts-page">
    <div class="toolbar">
      <el-button type="primary" @click="openDialog">
        <el-icon><Plus /></el-icon>&nbsp;新建用户
      </el-button>
    </div>

    <el-card shadow="never">
      <el-table v-loading="loading" :data="users" style="width: 100%">
        <el-table-column prop="username" label="用户名" min-width="160" />
        <el-table-column prop="display_name" label="姓名" min-width="160" />
        <el-table-column label="角色" width="150">
          <template #default="{ row }: { row: UserInfo }">
            <el-tag size="small" :type="roleTag(row.role)" effect="plain">{{ row.role }}</el-tag>
          </template>
        </el-table-column>
        <el-table-column label="操作" width="170" fixed="right">
          <template #default="{ row }: { row: UserInfo }">
            <el-button link type="primary" size="small" @click="openReset(row)">重置密码</el-button>
            <el-button
              link
              type="danger"
              size="small"
              :disabled="row.id === auth.user?.id"
              @click="removeUser(row)"
            >删除</el-button>
          </template>
        </el-table-column>
      </el-table>
    </el-card>

    <el-dialog v-model="dialogVisible" title="新建用户" width="480px">
      <el-form label-width="80px">
        <el-form-item label="用户名" required>
          <el-input v-model="form.username" placeholder="登录用户名" />
        </el-form-item>
        <el-form-item label="姓名" required>
          <el-input v-model="form.display_name" placeholder="展示姓名" />
        </el-form-item>
        <el-form-item label="角色">
          <el-select v-model="form.role" style="width: 100%">
            <el-option v-for="r in ROLE_OPTIONS" :key="r" :label="r" :value="r" />
          </el-select>
        </el-form-item>
        <el-form-item label="密码" required>
          <el-input v-model="form.password" type="password" show-password placeholder="至少 6 位" />
        </el-form-item>
      </el-form>
      <template #footer>
        <el-button @click="dialogVisible = false">取消</el-button>
        <el-button type="primary" :loading="creating" @click="submitCreate">确定</el-button>
      </template>
    </el-dialog>

    <el-dialog v-model="resetVisible" title="重置密码" width="420px">
      <p class="reset-hint">
        为「{{ resetTarget?.display_name || resetTarget?.username }}」设置新的登录密码，旧密码立即失效。
      </p>
      <el-input v-model="resetPassword" type="password" show-password
                placeholder="至少 6 位" @keyup.enter="submitReset" />
      <template #footer>
        <el-button @click="resetVisible = false">取消</el-button>
        <el-button type="primary" :loading="resetting" @click="submitReset">确定重置</el-button>
      </template>
    </el-dialog>
  </div>
</template>

<style scoped>
.accounts-page { display: flex; flex-direction: column; gap: 14px; }
/* 页面标题由顶栏面包屑承载；主操作右对齐（与典籍知识库「上传文献」同一位置惯例） */
.toolbar { display: flex; justify-content: flex-end; }
.reset-hint { margin: 0 0 12px; font-size: 13.5px; line-height: 1.7; color: v-bind(theme.textColorSecondary); }
</style>
