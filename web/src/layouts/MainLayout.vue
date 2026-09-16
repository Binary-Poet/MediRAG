<script setup lang="ts">
// 主布局：深墨绿侧边栏（7 菜单）+ 顶栏（面包屑 + 服务标签 + 用户下拉）
// 结构依据《前端还原规格.md》全局规范；文案与截图一致
import { useRoute, useRouter } from 'vue-router'
import { computed } from 'vue'
import { useAuthStore } from '../stores/auth'
import { theme } from '../styles/theme'

const route = useRoute()
const router = useRouter()
const auth = useAuthStore()
const pageTitle = computed(() => (route.meta.title as string) ?? '')

// 登出后 store 清空，此时回落到「未登录」占位文案。
// 注意用 || 而非 ??：display_name 可以为空串（新建用户时姓名非必填），?? 不兜空串会导致侧栏显示空白。
const displayName = computed(() => auth.user?.display_name || '未登录')
const roleLabel = computed(() => auth.user?.role ?? '')
const avatarText = computed(() => displayName.value.slice(0, 1))

function handleCommand(command: string) {
  if (command === 'logout') {
    auth.logout()
    router.push('/login')
  }
}

const menus = [
  { path: '/qa', title: '辨证问答', icon: 'ChatDotRound' },
  { path: '/graph', title: '本草图谱', icon: 'Share' },
  { path: '/library', title: '典籍知识库', icon: 'Reading' },
  { path: '/overview', title: '运行概览', icon: 'DataLine' },
  { path: '/account', title: '账户管理', icon: 'User' },
  { path: '/inference', title: '推理配置', icon: 'Setting' },
  { path: '/profile', title: '我的档案', icon: 'Files' },
]
</script>

<template>
  <el-container class="main-layout">
    <el-aside width="220px" class="sidebar">
      <div class="logo">
        <div class="logo-icon">🌿</div>
        <div class="logo-text">
          <div class="logo-name">本草智问</div>
          <div class="logo-sub">中医药知识系统</div>
        </div>
      </div>
      <el-menu
        :default-active="$route.path"
        router
        class="sidebar-menu"
        background-color="#1a3220"
        text-color="#ffffff"
        active-text-color="#ffffff"
      >
        <el-menu-item v-for="m in menus" :key="m.path" :index="m.path">
          <el-icon><component :is="m.icon" /></el-icon>
          <span>{{ m.title }}</span>
        </el-menu-item>
      </el-menu>
      <div class="sidebar-footer">
        <el-avatar :size="32" class="footer-avatar">{{ avatarText }}</el-avatar>
        <div class="footer-info">
          <span class="footer-name">{{ displayName }}</span>
          <el-tag v-if="roleLabel" size="small" type="warning" effect="light" class="footer-role">{{ roleLabel }}</el-tag>
        </div>
      </div>
    </el-aside>

    <el-container>
      <el-header class="topbar" height="56px">
        <el-breadcrumb separator="/">
          <el-breadcrumb-item>知识工作台</el-breadcrumb-item>
          <el-breadcrumb-item>{{ pageTitle }}</el-breadcrumb-item>
        </el-breadcrumb>
        <div class="topbar-right">
          <span class="service-tag">● 中医药知识服务</span>
          <el-dropdown @command="handleCommand">
            <span class="user-entry">
              <el-avatar :size="26" class="user-avatar">{{ avatarText }}</el-avatar>
              {{ displayName }}
              <el-icon><ArrowDown /></el-icon>
            </span>
            <template #dropdown>
              <el-dropdown-menu>
                <el-dropdown-item command="logout">退出登录</el-dropdown-item>
              </el-dropdown-menu>
            </template>
          </el-dropdown>
        </div>
      </el-header>
      <el-main class="content">
        <router-view />
      </el-main>
    </el-container>
  </el-container>
</template>

<style scoped>
.main-layout {
  height: 100%;
}

.sidebar {
  background: #1a3220;
  display: flex;
  flex-direction: column;
}

.logo {
  display: flex;
  align-items: center;
  gap: 10px;
  padding: 18px 20px 14px;
}

.logo-icon {
  width: 34px;
  height: 34px;
  border-radius: 8px;
  background: #2d6a4f;
  display: flex;
  align-items: center;
  justify-content: center;
  font-size: 18px;
}

.logo-name {
  color: #fff;
  font-size: 16px;
  font-weight: 600;
  line-height: 1.2;
}

.logo-sub {
  color: rgba(255, 255, 255, 0.6);
  font-size: 12px;
}

.sidebar-menu {
  border-right: none;
  flex: 1;
}

.sidebar-menu :deep(.el-menu-item.is-active) {
  background: #2d6a4f;
}

.sidebar-footer {
  display: flex;
  align-items: center;
  gap: 10px;
  padding: 12px 20px 14px;
  border-top: 1px solid rgba(255, 255, 255, 0.08);
  flex-shrink: 0;
}

.footer-avatar {
  background: #2d6a4f;
  font-size: 13px;
  flex-shrink: 0;
}

.footer-info {
  display: flex;
  flex-direction: column;
  gap: 4px;
  min-width: 0;
}

.footer-name {
  color: #fff;
  font-size: 13px;
  line-height: 1.2;
}

.footer-role {
  align-self: flex-start;
  --el-tag-padding-horizontal: 6px;
  --el-tag-font-size: 11px;
}

.topbar {
  background: #fff;
  border-bottom: 1px solid #e5e7eb;
  display: flex;
  align-items: center;
  justify-content: space-between;
}

.topbar-right {
  display: flex;
  align-items: center;
  gap: 16px;
}

.service-tag {
  font-size: 12px;
  color: #2d6a4f;
}

.user-entry {
  display: flex;
  align-items: center;
  gap: 6px;
  cursor: pointer;
  font-size: 14px;
  color: #1f2937;
}

.user-avatar {
  background: v-bind(theme.colorPrimary);
  font-size: 12px;
}

.content {
  background: #f5f7f5;
}
</style>
