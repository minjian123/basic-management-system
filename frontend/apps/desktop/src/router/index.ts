/** 路由（骨架）：首页 + 403 / 404 / 500，未知路径兜底 404；`meta.title` / `meta.keepAlive` 驱动页签与缓存。 */

import { createRouter, createWebHistory, type RouteRecordRaw } from 'vue-router'

const routes: RouteRecordRaw[] = [
  { path: '/', name: 'HomeView', component: () => import('@/views/HomeView.vue'), meta: { title: '工作台', keepAlive: true } },
  { path: '/403', name: 'Forbidden', component: () => import('@/views/ForbiddenView.vue'), meta: { title: '无访问权限' } },
  { path: '/500', name: 'ServerError', component: () => import('@/views/ServerErrorView.vue'), meta: { title: '服务异常' } },
  { path: '/:pathMatch(.*)*', name: 'NotFound', component: () => import('@/views/NotFoundView.vue'), meta: { title: '页面不存在' } },
]

/** 应用路由。 */
export const router = createRouter({ history: createWebHistory(), routes })
