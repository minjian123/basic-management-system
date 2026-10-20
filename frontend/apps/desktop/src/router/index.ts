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
  // 角色管理 / 用户管理（平台内建页）：菜单 `/sys/roles`、`/sys/users` 由 `seed_menu.py` 下发，
  // 路由改由**通用页面路由**统一装载（`router/page-route.ts` 声明装载，02_13）；`installMenuRoutes`
  // 对已存在路径跳过，占位路由不顶替。
  // 账号锁定（平台内建页）：`sys_account_lock` 未入表单标识清单，仍静态注册。
  {
    path: '/sys/account-locks',
    name: 'SystemAccountLock',
    component: () => import('@/views/system/user/AccountLockView.vue'),
    meta: { title: '账号锁定', keepAlive: true },
  },
  // 自助改密（首登强制改密 / 常规改密）：受保护静态路由，守卫在 `must_change_password` 时强制跳转。
  {
    path: '/change-password',
    name: 'ChangePassword',
    component: () => import('@/views/ChangePasswordView.vue'),
    meta: { title: '修改密码' },
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
