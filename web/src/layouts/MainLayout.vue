<script setup lang="ts">
// 主布局：深墨绿侧边栏（7 菜单）+ 顶栏（面包屑 + 服务标签 + 用户下拉）
// 结构依据《前端还原规格.md》全局规范；文案与截图一致
import { useRoute, useRouter } from 'vue-router'
import { computed, onMounted, onUnmounted, ref } from 'vue'
import { useAuthStore } from '../stores/auth'
import { theme } from '../styles/theme'

const route = useRoute()
const router = useRouter()
const auth = useAuthStore()
const pageTitle = computed(() => (route.meta.title as string) ?? '')

// ===== 侧边栏折叠（规格全局规范「可折叠」） =====
const collapsed = ref(false)

// ===== 顶栏服务状态灯：轮询后端 /health（无鉴权、不依赖外部服务），真实反映在线状态 =====
// null = 尚未完成首次探测。30s 一轮：状态灯不需要秒级实时，频繁探测只添噪声。
const serviceUp = ref<boolean | null>(null)
let healthTimer: number | undefined

async function checkHealth() {
  try {
    // 后端停机时 fetch 可能长时间挂起，5s 内无响应即按不可用处理
    const ctrl = new AbortController()
    const abortTimer = window.setTimeout(() => ctrl.abort(), 5000)
    const r = await fetch('/health', { signal: ctrl.signal })
    window.clearTimeout(abortTimer)
    serviceUp.value = r.ok
  } catch {
    serviceUp.value = false   // 网络层失败（后端停机/代理不可达）同视为服务不可用
  }
}

const serviceLabel = computed(() =>
  serviceUp.value === true ? '中医药知识服务'
    : serviceUp.value === false ? '服务连接异常' : '服务检测中')

onMounted(() => {
  checkHealth()
  healthTimer = window.setInterval(checkHealth, 30000)
})
onUnmounted(() => window.clearInterval(healthTimer))

// 登出后 store 清空，此时回落到「未登录」占位文案。
// 注意用 || 而非 ??：display_name 可以为空串（新建用户时姓名非必填），?? 不兜空串会导致侧栏显示空白。
const displayName = computed(() => auth.user?.display_name || '未登录')
const roleLabel = computed(() => auth.user?.role ?? '')
const avatarText = computed(() => displayName.value.slice(0, 1))

// 角色徽章按权限分级着色（与账户管理页共用同一套口径）
const ROLE_TAG: Record<string, 'warning' | 'primary' | 'info'> = {
  管理员: 'warning', 中医药从业者: 'primary', 知识用户: 'info',
}
const roleTagType = computed(() => ROLE_TAG[auth.user?.role ?? ''] ?? 'info')

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
    <el-aside :width="collapsed ? '64px' : '220px'" class="sidebar" :class="{ collapsed }">
      <div class="logo">
        <div class="logo-icon">🌿</div>
        <div v-if="!collapsed" class="logo-text">
          <div class="logo-name">本草智问</div>
          <div class="logo-sub">中医药知识系统</div>
        </div>
      </div>
      <el-menu
        :default-active="$route.path"
        router
        class="sidebar-menu"
        :collapse="collapsed"
        :collapse-transition="false"
        :background-color="theme.sidebarBg"
        :text-color="theme.sidebarText"
        :active-text-color="theme.sidebarText"
      >
        <el-menu-item v-for="m in menus" :key="m.path" :index="m.path">
          <el-icon><component :is="m.icon" /></el-icon>
          <template #title>{{ m.title }}</template>
        </el-menu-item>
      </el-menu>
      <div class="sidebar-footer">
        <el-avatar :size="32" class="footer-avatar">{{ avatarText }}</el-avatar>
        <div v-if="!collapsed" class="footer-info">
          <span class="footer-name">{{ displayName }}</span>
          <el-tag v-if="roleLabel" size="small" :type="roleTagType" effect="light" class="footer-role">{{ roleLabel }}</el-tag>
        </div>
      </div>
    </el-aside>

    <el-container>
      <el-header class="topbar" height="56px">
        <div class="topbar-left">
          <el-icon
            class="collapse-btn"
            :title="collapsed ? '展开侧边栏' : '收起侧边栏'"
            @click="collapsed = !collapsed"
          >
            <component :is="collapsed ? 'Expand' : 'Fold'" />
          </el-icon>
          <el-breadcrumb separator="/">
            <el-breadcrumb-item>知识工作台</el-breadcrumb-item>
            <el-breadcrumb-item>{{ pageTitle }}</el-breadcrumb-item>
          </el-breadcrumb>
        </div>
        <div class="topbar-right">
          <span
            class="service-tag"
            :class="{ up: serviceUp === true, down: serviceUp === false }"
            :title="serviceUp === true ? '服务运行正常' : serviceUp === false ? '无法连接后端服务' : '正在检测服务状态'"
          >
            <i class="service-dot" />{{ serviceLabel }}
          </span>
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
  background: v-bind(theme.sidebarBg);
  display: flex;
  flex-direction: column;
}

.logo {
  display: flex;
  align-items: center;
  gap: 10px;
  padding: 18px 20px 14px;
}

/* 折叠态：只留图标，居中 */
.sidebar.collapsed .logo {
  justify-content: center;
  padding: 18px 0 14px;
}

.sidebar.collapsed .sidebar-footer {
  justify-content: center;
  padding: 12px 0 14px;
}

.logo-icon {
  width: 34px;
  height: 34px;
  border-radius: 8px;
  background: v-bind(theme.colorPrimary);
  display: flex;
  align-items: center;
  justify-content: center;
  font-size: 18px;
}

.logo-name {
  color: v-bind(theme.sidebarText);
  font-size: 16px;
  font-weight: 600;
  line-height: 1.2;
}

.logo-sub {
  color: v-bind(theme.sidebarTextMuted);
  font-size: 12px;
}

.sidebar-menu {
  border-right: none;
  flex: 1;
}

.sidebar-menu :deep(.el-menu-item.is-active) {
  background: v-bind(theme.sidebarActiveBg);
}

.sidebar-footer {
  display: flex;
  align-items: center;
  gap: 10px;
  padding: 12px 20px 14px;
  border-top: 1px solid v-bind(theme.sidebarDivider);
  flex-shrink: 0;
}

.footer-avatar {
  background: v-bind(theme.colorPrimary);
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
  color: v-bind(theme.sidebarText);
  font-size: 13px;
  line-height: 1.2;
}

.footer-role {
  align-self: flex-start;
  --el-tag-padding-horizontal: 6px;
  --el-tag-font-size: 11px;
}

.topbar {
  background: v-bind(theme.cardBg);
  border-bottom: 1px solid v-bind(theme.borderColor);
  display: flex;
  align-items: center;
  justify-content: space-between;
}

.topbar-left {
  display: flex;
  align-items: center;
  gap: 12px;
  min-width: 0;
}

.collapse-btn {
  font-size: 18px;
  color: v-bind(theme.textColorSecondary);
  cursor: pointer;
  padding: 4px;
  flex: none;
}

.collapse-btn:hover {
  color: v-bind(theme.colorPrimary);
}

.topbar-right {
  display: flex;
  align-items: center;
  gap: 16px;
}

/* 服务状态灯：绿=在线（轮询 /health 真实结果），红=后端不可达，灰=首次探测中 */
.service-tag {
  display: inline-flex;
  align-items: center;
  gap: 6px;
  font-size: 12px;
  color: v-bind(theme.textColorSecondary);
  white-space: nowrap;
}

.service-dot {
  width: 8px;
  height: 8px;
  border-radius: 50%;
  background: v-bind(theme.textColorFaint);
  flex: none;
}

.service-tag.up .service-dot {
  background: v-bind(theme.colorSuccess);
  animation: service-pulse 2.4s ease-in-out infinite;
}

.service-tag.down {
  color: v-bind(theme.colorError);
}

.service-tag.down .service-dot {
  background: v-bind(theme.colorError);
}

@keyframes service-pulse {
  0%,
  100% {
    opacity: 1;
  }
  50% {
    opacity: 0.55;
  }
}

@media (prefers-reduced-motion: reduce) {
  .service-dot {
    animation: none;
  }
}

.user-entry {
  display: flex;
  align-items: center;
  gap: 6px;
  cursor: pointer;
  font-size: 14px;
  color: v-bind(theme.textColorPrimary);
}

.user-avatar {
  background: v-bind(theme.colorPrimary);
  font-size: 12px;
}

.content {
  background: v-bind(theme.pageBg);
}
</style>
