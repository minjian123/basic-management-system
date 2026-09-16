/** 路由骨架：静态壳路由 + 动态路由注入位（业务路由表不硬编码，阶段二按权限注入）。 */

import { createRouter, createWebHistory, type RouteRecordRaw } from 'vue-router'

import BasicLayout from '@/layouts/BasicLayout.vue'

const routes: RouteRecordRaw[] = [
  {
    path: '/',
    component: BasicLayout,
    children: [{ path: '', name: 'home', component: () => import('@/views/HomeView.vue') }],
  },
  // 错误页独立路由（懒加载；共享 ErrorPage 组件，按 code 区分）
  {
    path: '/403',
    name: 'error-403',
    component: () => import('@/components/feedback/ErrorPage.vue'),
    props: { code: 403 },
  },
  {
    path: '/404',
    name: 'error-404',
    component: () => import('@/components/feedback/ErrorPage.vue'),
    props: { code: 404 },
  },
  {
    path: '/500',
    name: 'error-500',
    component: () => import('@/components/feedback/ErrorPage.vue'),
    props: { code: 500 },
  },
  // 未知路径兜底 404
  { path: '/:pathMatch(.*)*', name: 'not-found', redirect: { name: 'error-404' } },
]

export const router = createRouter({
  history: createWebHistory(),
  routes,
})
