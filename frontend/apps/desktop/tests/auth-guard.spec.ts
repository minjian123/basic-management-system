/** 路由守卫接线用例（04-1-1 / Kiwi 2191）：开关 / 令牌判定 / 登录占位页。 */
// kiwi_id: 2191

import { mount } from '@vue/test-utils'
import type { Router } from 'vue-router'
import { afterEach, describe, expect, it, vi } from 'vitest'

import { setAccessToken } from '@/api/token'
import { installAuthGuard, isAuthGuardEnabled } from '@/router/guard'
import LoginView from '@/views/LoginView.vue'

afterEach(() => {
  setAccessToken(null)
  vi.unstubAllEnvs()
})

describe('isAuthGuardEnabled（Kiwi 2191）', () => {
  it('缺省关闭', () => {
    expect(isAuthGuardEnabled()).toBe(false)
  })

  it('VITE_AUTH_GUARD=on 启用', () => {
    vi.stubEnv('VITE_AUTH_GUARD', 'on')
    expect(isAuthGuardEnabled()).toBe(true)
  })
})

describe('installAuthGuard（Kiwi 2191）', () => {
  it('开关关闭时不注册钩子', () => {
    const beforeEach = vi.fn()
    const router = { beforeEach } as unknown as Router
    expect(installAuthGuard(router)).toBe(false)
    expect(beforeEach).not.toHaveBeenCalled()
  })

  it('启用时注册钩子并按令牌判定', () => {
    vi.stubEnv('VITE_AUTH_GUARD', 'on')
    let guard: ((to: { path: string }) => unknown) | undefined
    const router = {
      beforeEach: (fn: (to: { path: string }) => unknown) => {
        guard = fn
      },
    } as unknown as Router
    expect(installAuthGuard(router)).toBe(true)
    expect(guard?.({ path: '/org/users' })).toBe('/login')
    expect(guard?.({ path: '/login' })).toBe(true)
    setAccessToken('t1')
    expect(guard?.({ path: '/org/users' })).toBe(true)
  })
})

describe('LoginView 占位页（Kiwi 2191）', () => {
  it('渲染登录占位提示', () => {
    const wrapper = mount(LoginView)
    expect(wrapper.text()).toContain('登录')
    expect(wrapper.text()).toContain('阶段六')
  })
})
