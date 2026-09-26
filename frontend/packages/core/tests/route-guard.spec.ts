/** 路由守卫判定用例（04-1-1 / Kiwi 2191）：公开白名单 / 令牌 / 登录路径。 */
// kiwi_id: 2191

import { describe, expect, it } from 'vitest'

import { DEFAULT_LOGIN_PATH, DEFAULT_PUBLIC_PATHS, resolveAuthRedirect } from '../src'

describe('resolveAuthRedirect（Kiwi 2191）', () => {
  it('已持令牌一律放行', () => {
    expect(resolveAuthRedirect({ hasToken: true, path: '/org/users' })).toBeNull()
  })

  it('无令牌且非公开路径 → 跳登录', () => {
    expect(resolveAuthRedirect({ hasToken: false, path: '/org/users' })).toBe(DEFAULT_LOGIN_PATH)
  })

  it('公开白名单精确与子路径均放行', () => {
    for (const path of DEFAULT_PUBLIC_PATHS) {
      expect(resolveAuthRedirect({ hasToken: false, path })).toBeNull()
    }
    expect(resolveAuthRedirect({ hasToken: false, path: '/login/callback' })).toBeNull()
  })

  it('白名单前缀不误伤同段前缀路径', () => {
    expect(resolveAuthRedirect({ hasToken: false, path: '/loginfo' })).toBe(DEFAULT_LOGIN_PATH)
  })

  it('支持自定义白名单与登录路径', () => {
    expect(resolveAuthRedirect({ hasToken: false, path: '/public', publicPaths: ['/public'] })).toBeNull()
    expect(resolveAuthRedirect({ hasToken: false, path: '/x', loginPath: '/signin' })).toBe('/signin')
  })
})
