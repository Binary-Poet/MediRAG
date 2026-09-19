import { createRouter, createWebHistory } from 'vue-router'
import { useAuthStore } from '../stores/auth'

// 路由结构与侧边栏 7 个菜单一一对应（截图事实）
const router = createRouter({
  history: createWebHistory(),
  routes: [
    {
      path: '/login',
      name: 'login',
      component: () => import('../views/Login.vue'),
      meta: { title: '登录' },
    },
    {
      path: '/',
      component: () => import('../layouts/MainLayout.vue'),
      redirect: '/qa',
      children: [
        {
          path: 'qa',
          name: 'qa',
          component: () => import('../views/qa/Chat.vue'),
          meta: { title: '辨证问答', breadcrumb: '辨证问答', phase: '阶段 3 完整版' },
        },
        {
          path: 'graph',
          name: 'graph',
          component: () => import('../views/graph/GraphExplore.vue'),
          meta: { title: '本草图谱', breadcrumb: '本草图谱' },
        },
        {
          path: 'library',
          name: 'library',
          component: () => import('../views/knowledge/Library.vue'),
          meta: { title: '典籍知识库', breadcrumb: '典籍知识库' },
        },
        {
          path: 'overview',
          name: 'overview',
          component: () => import('../views/overview/Dashboard.vue'),
          meta: { title: '运行概览', breadcrumb: '运行概览', phase: '阶段 5' },
        },
        {
          path: 'account',
          name: 'account',
          component: () => import('../views/account/Accounts.vue'),
          meta: { title: '账户管理', breadcrumb: '账户管理', phase: '阶段 5' },
        },
        {
          path: 'inference',
          name: 'inference',
          component: () => import('../views/config/Inference.vue'),
          meta: { title: '推理配置', breadcrumb: '推理配置', phase: '阶段 5' },
        },
        {
          path: 'profile',
          name: 'profile',
          component: () => import('../views/account/Profile.vue'),
          meta: { title: '我的档案', breadcrumb: '我的档案', phase: '阶段 5' },
        },
      ],
    },
    { path: '/:pathMatch(.*)*', redirect: '/qa' },
  ],
})

// 登录守卫：未持 token 访问受保护页一律回登录页（登录页本身放行）。
// useAuthStore() 必须在守卫回调内调用 —— 模块顶层调用时 Pinia 尚未被 app.use 激活。
router.beforeEach((to) => {
  const auth = useAuthStore()
  if (to.path !== '/login' && !auth.token) return '/login'
})

// 标签页标题随路由更新：多开标签时可区分页面（无 meta.title 的路由回落到站名）
router.afterEach((to) => {
  document.title = to.meta.title ? `${to.meta.title} · 本草智问` : '本草智问'
})

export default router
