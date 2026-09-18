/** 路由（骨架）：首页 + 403 / 404 兜底。 */

import { createRouter, createWebHistory, type RouteRecordRaw } from 'vue-router'

const routes: RouteRecordRaw[] = [
  { path: '/', name: 'Home', component: () => import('@/views/HomeView.vue') },
  { path: '/403', name: 'Forbidden', component: () => import('@/views/ForbiddenView.vue') },
  { path: '/:pathMatch(.*)*', name: 'NotFound', component: () => import('@/views/NotFoundView.vue') },
]

/** 应用路由。 */
export const router = createRouter({ history: createWebHistory(), routes })
