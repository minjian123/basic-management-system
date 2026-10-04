/**
 * 登录族独立渲染用例（需求 05-1）：登录页（`/login`，含 `/login/qr`）为**独立全屏页**——
 * 不套主框架外壳、不入页签；其余路由（首页 / 错误页 / 业务页 / 模块页）仍在主框架内渲染。
 */

import { describe, expect, it } from 'vitest'

import { isStandalonePath } from '@/router/layout-scope'

describe('isStandalonePath（登录族独立全屏）', () => {
  it('登录页与扫码登录页：独立渲染（不套主框架）', () => {
    for (const path of ['/login', '/login/qr']) {
      expect(isStandalonePath(path)).toBe(true)
    }
  })

  it('登录族子路径：独立渲染（前缀匹配）', () => {
    expect(isStandalonePath('/login/qr/scan')).toBe(true)
  })

  it('框架内页（首页 / 错误页 / 业务页 / 模块页 / 开发态面板）：仍套主框架', () => {
    for (const path of ['/', '/403', '/404', '/500', '/sys/users/1', '/demo', '/dev/module-observability']) {
      expect(isStandalonePath(path)).toBe(false)
    }
  })

  it('相似前缀不误判（`/login-x` 非登录族）', () => {
    expect(isStandalonePath('/login-x')).toBe(false)
  })
})
