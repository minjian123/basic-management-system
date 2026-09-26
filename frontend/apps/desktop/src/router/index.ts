/** 路由（骨架）：登录占位 + 首页 + 403 / 404 / 500，未知路径兜底 404；`meta.title` / `meta.keepAlive` 驱动页签与缓存。 */

import { createRouter, createWebHistory, type RouteRecordRaw } from 'vue-router'

import { installAuthGuard } from './guard'

const routes: RouteRecordRaw[] = [
  { path: '/login', name: 'Login', component: () => import('@/views/LoginView.vue'), meta: { title: '登录' } },
  {
    path: '/',
    name: 'HomeView',
    component: () => import('@/views/HomeView.vue'),
    meta: { title: '工作台', keepAlive: true },
  },
  {
    path: '/403',
    name: 'Forbidden',
    component: () => import('@/views/ForbiddenView.vue'),
    meta: { title: '无访问权限' },
  },
  {
    path: '/500',
    name: 'ServerError',
    component: () => import('@/views/ServerErrorView.vue'),
    meta: { title: '服务异常' },
  },
  {
    path: '/:pathMatch(.*)*',
    name: 'NotFound',
    component: () => import('@/views/NotFoundView.vue'),
    meta: { title: '页面不存在' },
  },
]

// 开发态模块观测面板（dev-only：生产构建条件恒假，路由与视图均不进产物）。
if (import.meta.env.DEV) {
  routes.push({
    path: '/dev/module-observability',
    name: 'ModuleObservability',
    component: () => import('@/views/ModuleObservabilityView.vue'),
    meta: { title: '模块观测' },
  })
}

/** 应用路由。 */
export const router = createRouter({ history: createWebHistory(), routes })

// 认证守卫接线（默认关闭，`VITE_AUTH_GUARD=on` 启用；阶段六登录链路就绪后改默认开启）。
installAuthGuard(router)
