/**
 * 路由（骨架）：登录占位 + 首页 + 403 / 404 / 500，未知路径兜底 404；`meta.title` / `meta.keepAlive`
 * 驱动页签与缓存。
 *
 * 认证守卫（默认开启）改由宿主入口装配（`main.ts`）——守卫依赖会话 store，须在 pinia 就绪后注入。
 */

import { createRouter, createWebHistory, type RouteRecordRaw } from 'vue-router'

const routes: RouteRecordRaw[] = [
  { path: '/login', name: 'Login', component: () => import('@/views/LoginView.vue'), meta: { title: '登录' } },
  {
    path: '/login/qr',
    name: 'QrLogin',
    component: () => import('@/views/QrLoginView.vue'),
    meta: { title: '扫码登录', public: true },
  },
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
  // 用户详情宿主页（具名插槽宿主 `sys.user.detail.tabs`）：静态路由不进路由·菜单注册表，
  // 故不出现于生产菜单；阶段七用户管理可在此基础上接管真实用户详情能力。
  {
    path: '/sys/users/:id',
    name: 'SysUserDetail',
    component: () => import('@/views/SysUserDetailView.vue'),
    meta: { title: '用户详情' },
  },
  // 角色管理（平台内建页）：菜单 `/sys/roles` 由 `seed_menu.py` 下发并经动态菜单装载；
  // 此处静态注册真实路由（`installMenuRoutes` 对已存在路径跳过，占位路由不顶替）。
  {
    path: '/sys/roles',
    name: 'SystemRole',
    component: () => import('@/views/system/RoleView.vue'),
    meta: { title: '角色管理', keepAlive: true },
  },
  // 用户管理 / 账号锁定（平台内建页）：菜单 `/sys/users`、`/sys/account-locks` 由 `seed_menu.py` 下发
  // 并经动态菜单装载；此处静态注册真实路由（`installMenuRoutes` 对已存在路径跳过）。
  {
    path: '/sys/users',
    name: 'SystemUser',
    component: () => import('@/views/system/user/UserView.vue'),
    meta: { title: '用户管理', keepAlive: true },
  },
  {
    path: '/sys/account-locks',
    name: 'SystemAccountLock',
    component: () => import('@/views/system/user/AccountLockView.vue'),
    meta: { title: '账号锁定', keepAlive: true },
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
