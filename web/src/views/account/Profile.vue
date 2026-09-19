<script setup lang="ts">
import { computed, reactive, ref } from 'vue'
import { ElMessage } from 'element-plus'
import { changePassword, updateProfile } from '../../api/auth'
import { useAuthStore } from '../../stores/auth'
import { theme } from '../../styles/theme'

const auth = useAuthStore()
const pwdForm = reactive({ old_password: '', new_password: '' })
const pwdSaving = ref(false)

const editName = ref(false)
const nameInput = ref('')
const nameSaving = ref(false)

const infoRows = computed(() => [
  { label: '用户名', value: auth.user?.username || '-', editable: false },
  { label: '姓名', value: auth.user?.display_name || '-', editable: true },
  { label: '角色', value: auth.user?.role || '-', editable: false },
])

function startEditName() {
  nameInput.value = auth.user?.display_name || ''
  editName.value = true
}

function cancelEditName() {
  editName.value = false
}

async function saveName() {
  const name = nameInput.value.trim()
  if (!name) {
    ElMessage.warning('姓名不能为空')
    return
  }
  if (name.length > 50) {
    ElMessage.warning('姓名不超过 50 字')
    return
  }
  nameSaving.value = true
  try {
    const user = await updateProfile(name, auth.token)
    auth.setUser(user)
    ElMessage.success('姓名已修改')
    editName.value = false
  } catch (e) {
    ElMessage.error((e as Error).message)
  } finally {
    nameSaving.value = false
  }
}

async function submitPwd() {
  if (!pwdForm.old_password || !pwdForm.new_password) {
    ElMessage.warning('请填写原密码与新密码')
    return
  }
  if (pwdForm.new_password.length < 6) {
    ElMessage.warning('新密码至少 6 位')
    return
  }
  pwdSaving.value = true
  try {
    await changePassword(pwdForm.old_password, pwdForm.new_password, auth.token)
    ElMessage.success('密码已修改')
    pwdForm.old_password = ''
    pwdForm.new_password = ''
  } catch (e) {
    ElMessage.error((e as Error).message)
  } finally {
    pwdSaving.value = false
  }
}
</script>

<template>
  <div class="profile-page">
    <el-card shadow="never" class="card">
      <div class="card-title">账号信息</div>
      <div class="info-rows">
        <div v-for="row in infoRows" :key="row.label" class="info-row">
          <span class="info-label">{{ row.label }}</span>
          <div class="info-value-wrap">
            <template v-if="row.editable && editName">
              <el-input
                v-model="nameInput"
                size="small"
                class="name-input"
                maxlength="50"
                @keyup.enter="saveName"
              />
              <el-button size="small" type="primary" :loading="nameSaving" @click="saveName">保存</el-button>
              <el-button size="small" @click="cancelEditName">取消</el-button>
            </template>
            <template v-else>
              <span class="info-value">{{ row.value }}</span>
              <el-icon
                v-if="row.editable"
                class="edit-icon"
                :title="'修改姓名'"
                @click="startEditName"
              >
                <Edit />
              </el-icon>
            </template>
          </div>
        </div>
      </div>
    </el-card>

    <el-card shadow="never" class="card">
      <div class="card-title">修改密码</div>
      <el-form label-width="90px" class="pwd-form">
        <el-form-item label="原密码" required>
          <el-input v-model="pwdForm.old_password" type="password" show-password placeholder="请输入原密码" />
        </el-form-item>
        <el-form-item label="新密码" required>
          <el-input v-model="pwdForm.new_password" type="password" show-password placeholder="至少 6 位" />
        </el-form-item>
      </el-form>
      <el-button type="primary" :loading="pwdSaving" @click="submitPwd">保存修改</el-button>
    </el-card>
  </div>
</template>

<style scoped>
.profile-page { display: flex; flex-direction: column; gap: 14px; }
.card { background: v-bind(theme.cardBg); border-radius: v-bind(theme.borderRadius); }
.card-title { font-size: 14px; font-weight: 600; color: v-bind(theme.textColorPrimary); margin-bottom: 12px; }
.info-rows { display: flex; flex-direction: column; gap: 10px; }
.info-row { display: flex; align-items: center; gap: 12px; }
.info-label { flex: none; width: 90px; font-size: 13px; color: v-bind(theme.textColorSecondary); }
.info-value-wrap { display: flex; align-items: center; gap: 8px; }
.info-value { font-size: 13px; color: v-bind(theme.textColorPrimary); }
.edit-icon {
  font-size: 14px;
  color: v-bind(theme.textColorSecondary);
  cursor: pointer;
  opacity: 0.6;
  transition: opacity 0.15s;
}
.edit-icon:hover { opacity: 1; color: v-bind(theme.colorPrimary); }
.name-input { width: 200px; }
.pwd-form { max-width: 420px; }
</style>
