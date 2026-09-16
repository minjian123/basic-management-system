/** 路由骨架：静态壳路由 + 错误页 + 路由守卫（业务路由表不硬编码，随菜单动态注册）。 */

import { createRouter, createWebHistory, type RouteRecordRaw } from 'vue-router'

import BasicLayout from '@/layouts/BasicLayout.vue'

import { setupRouterGuard } from './guard'
import { nameComponent } from './routeComponent'

const routes: RouteRecordRaw[] = [
  {
    path: '/',
    name: 'layout',
    component: BasicLayout,
    children: [
      {
        path: '',
        name: 'home',
        // 组件名约定（keep-alive include 按路由 name 匹配）
        component: nameComponent('home', () => import('@/views/HomeView.vue')),
      },
    ],
  },
  // 错误页独立路由（懒加载；共享 ErrorPage 组件，按 code 区分；公开路由）
  {
    path: '/403',
    name: 'error-403',
    component: () => import('@/components/feedback/ErrorPage.vue'),
    props: { code: 403 },
    meta: { public: true },
  },
  {
    path: '/404',
    name: 'error-404',
    component: () => import('@/components/feedback/ErrorPage.vue'),
    props: { code: 404 },
    meta: { public: true },
  },
  {
    path: '/500',
    name: 'error-500',
    component: () => import('@/components/feedback/ErrorPage.vue'),
    props: { code: 500 },
    meta: { public: true },
  },
  // 未知路径兜底 404
  { path: '/:pathMatch(.*)*', name: 'not-found', redirect: { name: 'error-404' } },
]

export const router = createRouter({
  history: createWebHistory(),
  routes,
})

// 路由守卫：登录态 / 权限码 / 错误页跳转（登录页未就绪时放行占位，见 guard.ts）
setupRouterGuard(router)
