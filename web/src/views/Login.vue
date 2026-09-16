<script setup lang="ts">
// 登录页 —— 布局与文案依据《前端还原规格.md》P0-1（截图原文，不得自造）
// 提交动作接 POST /api/auth/login，成功后写入 store 并进入工作台
import { reactive, ref } from 'vue'
import { useRouter } from 'vue-router'
import { ElMessage } from 'element-plus'
import { useAuthStore } from '../stores/auth'

const router = useRouter()
const auth = useAuthStore()
const loading = ref(false)
const form = reactive({ username: '', password: '', remember: true })

const features = [
  { icon: '📓', title: '典籍文献统一入库', desc: '完整保留原文、章节与切片证据' },
  { icon: '🔗', title: '实体关系审核发布', desc: '候选知识通过人工审核后进入图谱' },
  { icon: '💬', title: '问答结论全程溯源', desc: '同步展示文献证据与图谱关系' },
]

const demoAccounts = [
  { label: '管理员', username: 'admin' },
  { label: '知识用户', username: 'user1' },
]

function fillAccount(username: string) {
  form.username = username
  form.password = ''
}

async function handleLogin() {
  if (!form.username || !form.password) {
    ElMessage.warning('请输入用户名和密码')
    return
  }
  loading.value = true
  try {
    await auth.login(form.username, form.password)
    ElMessage.success('登录成功')
    router.push('/')
  } catch (e) {
    ElMessage.error((e as Error).message)
  } finally {
    loading.value = false
  }
}
</script>

<template>
  <div class="login-page">
    <header class="login-header">
      <div class="brand">
        <div class="brand-icon">🌿</div>
        <div>
          <div class="brand-name">本草智问</div>
          <div class="brand-sub">企业级中医药知识工作台</div>
        </div>
      </div>
      <div class="header-right"><el-icon><Lock /></el-icon> 权限分级 · 知识可追溯</div>
    </header>

    <div class="login-body">
      <!-- 左侧品牌区 -->
      <section class="brand-panel">
        <span class="panel-tag">中医药知识基础设施</span>
        <h1>基于知识图谱与 RAG 的<br />中医药智能问答系统</h1>
        <p class="panel-desc">
          统一连接典籍文献、知识图谱与智能问答，让团队在同一可信语境中检索、审核与复用知识。
        </p>
        <ul class="feature-list">
          <li v-for="f in features" :key="f.title">
            <span class="feature-icon">{{ f.icon }}</span>
            <div>
              <div class="feature-title">{{ f.title }}</div>
              <div class="feature-desc">{{ f.desc }}</div>
            </div>
          </li>
        </ul>
        <div class="panel-tip"><el-icon><InfoFilled /></el-icon> 候选知识经人工审核后发布，回答结论保留原文证据</div>
      </section>

      <!-- 右侧登录表单区 -->
      <section class="form-panel">
        <div class="form-header">
          <div class="org">组织账号</div>
          <h2>登录工作台</h2>
          <p>使用您的本草智问账号继续</p>
        </div>

        <el-form label-position="top">
          <el-form-item label="用户名" required>
            <el-input v-model="form.username" placeholder="admin">
              <template #prefix><el-icon><User /></el-icon></template>
            </el-input>
          </el-form-item>
          <el-form-item label="密码" required>
            <el-input v-model="form.password" type="password" placeholder="请输入密码" show-password>
              <template #prefix><el-icon><Lock /></el-icon></template>
            </el-input>
          </el-form-item>
        </el-form>

        <div class="form-aux">
          <el-checkbox v-model="form.remember">记住用户名</el-checkbox>
          <el-link type="primary" :underline="false">忘记密码？</el-link>
        </div>

        <el-button type="primary" class="login-btn" :loading="loading" @click="handleLogin">登录工作台</el-button>

        <div class="register-tip">还没有组织账号？ <el-link type="primary">申请注册</el-link></div>

        <div class="demo-area">
          <div class="demo-head">
            <span>体验环境</span>
            <span class="demo-sub">选择账号后自动填充</span>
            <el-tag size="small" type="info">仅开发环境</el-tag>
          </div>
          <div
            v-for="acc in demoAccounts"
            :key="acc.username"
            class="demo-card"
            @click="fillAccount(acc.username)"
          >
            <div>
              <div class="demo-label">{{ acc.label }}</div>
              <div class="demo-user">{{ acc.username }}</div>
            </div>
            <el-icon><ArrowRight /></el-icon>
          </div>
        </div>

        <p class="security-tip">系统仅面向授权用户，访问行为受角色权限控制。</p>
      </section>
    </div>
  </div>
</template>

<style scoped>
.login-page {
  min-height: 100%;
  background: #f5f7f5;
  display: flex;
  flex-direction: column;
}

.login-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  padding: 16px 32px;
  background: #fff;
  border-bottom: 1px solid #e5e7eb;
}

.brand {
  display: flex;
  align-items: center;
  gap: 10px;
}

.brand-icon {
  width: 36px;
  height: 36px;
  border-radius: 8px;
  background: #2d6a4f;
  display: flex;
  align-items: center;
  justify-content: center;
  font-size: 18px;
}

.brand-name {
  font-weight: 600;
  font-size: 16px;
}

.brand-sub {
  font-size: 12px;
  color: #6b7280;
}

.header-right {
  display: flex;
  align-items: center;
  gap: 4px;
  color: #6b7280;
  font-size: 13px;
}

.login-body {
  flex: 1;
  display: grid;
  grid-template-columns: 55% 45%;
  min-height: 0;
}

/* 左侧品牌区 */
.brand-panel {
  background: #1a3220;
  color: #fff;
  padding: 56px 64px;
  display: flex;
  flex-direction: column;
  gap: 22px;
}

.panel-tag {
  align-self: flex-start;
  background: rgba(255, 255, 255, 0.12);
  color: rgba(255, 255, 255, 0.85);
  border-radius: 999px;
  padding: 4px 14px;
  font-size: 13px;
}

.brand-panel h1 {
  font-size: 28px;
  font-weight: 600;
  line-height: 1.4;
  margin: 0;
}

.panel-desc {
  color: rgba(255, 255, 255, 0.75);
  line-height: 1.7;
  margin: 0;
}

.feature-list {
  list-style: none;
  padding: 0;
  margin: 12px 0 0;
  display: flex;
  flex-direction: column;
  gap: 18px;
}

.feature-list li {
  display: flex;
  gap: 12px;
  align-items: flex-start;
}

.feature-icon {
  font-size: 20px;
}

.feature-title {
  font-weight: 600;
  font-size: 15px;
}

.feature-desc {
  color: rgba(255, 255, 255, 0.7);
  font-size: 13px;
  margin-top: 2px;
}

.panel-tip {
  margin-top: auto;
  display: flex;
  align-items: center;
  gap: 6px;
  color: rgba(255, 255, 255, 0.7);
  font-size: 13px;
}

/* 右侧表单区 */
.form-panel {
  background: #fff;
  padding: 48px 56px;
  display: flex;
  flex-direction: column;
  overflow-y: auto;
}

.org {
  font-size: 13px;
  color: #6b7280;
}

.form-header h2 {
  margin: 4px 0;
  font-size: 22px;
}

.form-header p {
  color: #6b7280;
  font-size: 13px;
  margin: 0 0 20px;
}

.form-aux {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-bottom: 18px;
}

.login-btn {
  width: 100%;
  height: 42px;
  font-size: 15px;
}

.register-tip {
  text-align: center;
  font-size: 13px;
  color: #6b7280;
  margin: 14px 0 22px;
}

.demo-area {
  border: 1px solid #e5e7eb;
  border-radius: 10px;
  padding: 14px;
  background: #fafbfa;
}

.demo-head {
  display: flex;
  align-items: center;
  gap: 8px;
  font-weight: 600;
  margin-bottom: 10px;
}

.demo-sub {
  font-weight: 400;
  color: #6b7280;
  font-size: 12px;
  flex: 1;
}

.demo-card {
  display: flex;
  justify-content: space-between;
  align-items: center;
  border: 1px solid #e5e7eb;
  border-radius: 8px;
  background: #fff;
  padding: 10px 14px;
  margin-top: 8px;
  cursor: pointer;
  transition: border-color 0.2s;
}

.demo-card:hover {
  border-color: #2d6a4f;
}

.demo-label {
  font-size: 14px;
  font-weight: 600;
}

.demo-user {
  font-size: 12px;
  color: #6b7280;
}

.security-tip {
  margin-top: 18px;
  font-size: 12px;
  color: #9ca3af;
  text-align: center;
}
</style>
