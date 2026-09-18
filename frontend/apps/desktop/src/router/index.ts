/** 路由（骨架）：首页 + 403 / 404 / 500，未知路径兜底 404。 */

import { createRouter, createWebHistory, type RouteRecordRaw } from 'vue-router'

const routes: RouteRecordRaw[] = [
  { path: '/', name: 'Home', component: () => import('@/views/HomeView.vue') },
  { path: '/403', name: 'Forbidden', component: () => import('@/views/ForbiddenView.vue') },
  { path: '/500', name: 'ServerError', component: () => import('@/views/ServerErrorView.vue') },
  { path: '/:pathMatch(.*)*', name: 'NotFound', component: () => import('@/views/NotFoundView.vue') },
]

/** 应用路由。 */
export const router = createRouter({ history: createWebHistory(), routes })
