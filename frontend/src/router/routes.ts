/** 路由骨架：静态壳路由 + 动态路由注入位（业务路由表不硬编码，阶段二按权限注入）。 */

import { createRouter, createWebHistory, type RouteRecordRaw } from 'vue-router'

import BasicLayout from '@/layouts/BasicLayout.vue'

const routes: RouteRecordRaw[] = [
  {
    path: '/',
    component: BasicLayout,
    children: [{ path: '', name: 'home', component: () => import('@/views/HomeView.vue') }],
  },
]

export const router = createRouter({
  history: createWebHistory(),
  routes,
})
