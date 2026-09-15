import { createRouter, createWebHistory } from 'vue-router'

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
          component: () => import('../views/Placeholder.vue'),
          meta: { title: '本草图谱', breadcrumb: '本草图谱', phase: '阶段 2/4' },
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
          component: () => import('../views/Placeholder.vue'),
          meta: { title: '运行概览', breadcrumb: '运行概览', phase: '阶段 5' },
        },
        {
          path: 'account',
          name: 'account',
          component: () => import('../views/Placeholder.vue'),
          meta: { title: '账户管理', breadcrumb: '账户管理', phase: '阶段 5 (P2)' },
        },
        {
          path: 'inference',
          name: 'inference',
          component: () => import('../views/Placeholder.vue'),
          meta: { title: '推理配置', breadcrumb: '推理配置', phase: '阶段 5' },
        },
        {
          path: 'profile',
          name: 'profile',
          component: () => import('../views/Placeholder.vue'),
          meta: { title: '我的档案', breadcrumb: '我的档案', phase: '阶段 5 (P2)' },
        },
      ],
    },
    { path: '/:pathMatch(.*)*', redirect: '/qa' },
  ],
})

export default router
