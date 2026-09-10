/** 路由骨架：静态壳路由 + 动态路由注入位（业务路由表不硬编码，阶段二按权限注入）。 */

import { createRouter, createWebHistory, type RouteRecordRaw } from 'vue-router'

import HomeView from '@/views/HomeView.vue'

const routes: RouteRecordRaw[] = [
  { path: '/', name: 'home', component: HomeView },
  // 业务路由随阶段二权限体系动态注入
]

export const router = createRouter({
  history: createWebHistory(),
  routes,
})
