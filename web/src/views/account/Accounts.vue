<script setup lang="ts">
// 账户管理（P2）：列表 / 新建 / 删除。后端 /api/users 仅管理员可访问（require_admin）。
import { onMounted, reactive, ref } from 'vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import { createUser, deleteUser, listUsers, type CreateUserBody } from '../../api/users'
import type { UserInfo } from '../../api/auth'
import { useAuthStore } from '../../stores/auth'
import { theme } from '../../styles/theme'

// 与后端 app/models/user.py 的 ROLES 一致
const ROLE_OPTIONS = ['管理员', '中医药从业者', '知识用户']

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
    <div class="page-head">
      <h2>账户管理</h2>
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
            <el-tag size="small" type="success" effect="plain">{{ row.role }}</el-tag>
          </template>
        </el-table-column>
        <el-table-column label="操作" width="100" fixed="right">
          <template #default="{ row }: { row: UserInfo }">
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
        <el-form-item label="姓名">
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
  </div>
</template>

<style scoped>
.accounts-page { display: flex; flex-direction: column; gap: 14px; }
.page-head { display: flex; align-items: center; justify-content: space-between; }
.page-head h2 { margin: 0; font-size: 18px; font-weight: 600; color: v-bind(theme.textColorPrimary); }
</style>
