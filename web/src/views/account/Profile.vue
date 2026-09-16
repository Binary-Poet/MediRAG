<script setup lang="ts">
// 我的档案：展示当前登录用户信息 + 修改密码（PUT /api/auth/password）。
import { computed, reactive, ref } from 'vue'
import { ElMessage } from 'element-plus'
import { changePassword } from '../../api/auth'
import { useAuthStore } from '../../stores/auth'
import { theme } from '../../styles/theme'

const auth = useAuthStore()
const form = reactive({ old_password: '', new_password: '' })
const saving = ref(false)

const infoRows = computed(() => [
  { label: '用户名', value: auth.user?.username ?? '-' },
  { label: '姓名', value: auth.user?.display_name ?? '-' },
  { label: '角色', value: auth.user?.role ?? '-' },
])

async function submit() {
  if (!form.old_password || !form.new_password) {
    ElMessage.warning('请填写原密码与新密码')
    return
  }
  if (form.new_password.length < 6) {
    ElMessage.warning('新密码至少 6 位')
    return
  }
  saving.value = true
  try {
    await changePassword(form.old_password, form.new_password, auth.token)
    ElMessage.success('密码已修改')
    form.old_password = ''
    form.new_password = ''
  } catch (e) {
    ElMessage.error((e as Error).message)
  } finally {
    saving.value = false
  }
}
</script>

<template>
  <div class="profile-page">
    <div class="page-head"><h2>我的档案</h2></div>

    <el-card shadow="never" class="card">
      <div class="card-title">账号信息</div>
      <div class="info-rows">
        <div v-for="row in infoRows" :key="row.label" class="info-row">
          <span class="info-label">{{ row.label }}</span>
          <span class="info-value">{{ row.value }}</span>
        </div>
      </div>
    </el-card>

    <el-card shadow="never" class="card">
      <div class="card-title">修改密码</div>
      <el-form label-width="90px" class="pwd-form">
        <el-form-item label="原密码" required>
          <el-input v-model="form.old_password" type="password" show-password placeholder="请输入原密码" />
        </el-form-item>
        <el-form-item label="新密码" required>
          <el-input v-model="form.new_password" type="password" show-password placeholder="至少 6 位" />
        </el-form-item>
      </el-form>
      <el-button type="primary" :loading="saving" @click="submit">保存修改</el-button>
    </el-card>
  </div>
</template>

<style scoped>
.profile-page { display: flex; flex-direction: column; gap: 14px; }
.page-head h2 { margin: 0; font-size: 18px; font-weight: 600; color: v-bind(theme.textColorPrimary); }
.card { background: v-bind(theme.cardBg); border-radius: v-bind(theme.borderRadius); }
.card-title { font-size: 14px; font-weight: 600; color: v-bind(theme.textColorPrimary); margin-bottom: 12px; }
.info-rows { display: flex; flex-direction: column; gap: 10px; }
.info-row { display: flex; align-items: center; gap: 12px; }
.info-label { flex: none; width: 90px; font-size: 13px; color: v-bind(theme.textColorSecondary); }
.info-value { font-size: 13px; color: v-bind(theme.textColorPrimary); }
.pwd-form { max-width: 420px; }
</style>
