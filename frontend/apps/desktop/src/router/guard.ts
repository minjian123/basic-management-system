/** 路由守卫接线：无令牌访问受保护路径 → 跳登录（默认关闭，`VITE_AUTH_GUARD=on` 启用）。 */

import { resolveAuthRedirect } from '@bms/core'
import type { Router } from 'vue-router'

import { getAccessToken } from '@/api/token'

/**
 * 守卫是否启用强制跳转（缺省关闭；阶段六登录链路就绪后改默认开启）。
 *
 * @returns `VITE_AUTH_GUARD === 'on'` 时为 `true`。
 */
export function isAuthGuardEnabled(): boolean {
  return import.meta.env.VITE_AUTH_GUARD === 'on'
}

/**
 * 安装认证守卫；开关关闭时不注册任何钩子（空操作）。
 *
 * @param router 路由实例。
 * @returns 是否已注册守卫。
 */
export function installAuthGuard(router: Router): boolean {
  if (!isAuthGuardEnabled()) {
    return false
  }
  router.beforeEach((to) => {
    const redirect = resolveAuthRedirect({ hasToken: getAccessToken() !== null, path: to.path })
    return redirect === null ? true : redirect
  })
  return true
}
