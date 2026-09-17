/**
 * 路由守卫：登录态 / 权限码 / 错误页跳转（《布局设计 · 导航》§6 口径）。
 *
 * - `meta.public === true` 公开路由放行（错误页等）；
 * - 无 token → 跳 `/login?redirect=`（**登录页未就绪时放行占位**：由请求层 401 会话失效兜底，
 *   登录页本体归页面任务）；
 * - `meta.perm` → `canAccess` 判定，无权跳 `/403`（后端 `require_permission` 为最终强校验）。
 */

import type { Router } from 'vue-router'

import { tokenManager } from '@/api/token'
import { canAccess } from '@/utils/perm'

export function setupRouterGuard(router: Router): void {
  router.beforeEach((to) => {
    if (to.meta.public === true) {
      return true
    }
    if (!tokenManager.hasToken()) {
      const loginReady = router.resolve('/login').matched.length > 0
      if (loginReady) {
        return { path: '/login', query: { redirect: to.fullPath } }
      }
      // 登录页未就绪（页面任务前）：放行占位，由请求层 401 兜底
      return true
    }
    if (to.meta.perm !== undefined && !canAccess(to.meta.perm as string | string[])) {
      return { path: '/403' }
    }
    return true
  })
}
