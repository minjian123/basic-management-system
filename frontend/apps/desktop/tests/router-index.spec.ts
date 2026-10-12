// kiwi_id: 2191
/**
 * 应用路由骨架用例（04-1-1）：静态路由表（登录 / 扫码 / 首页 / 错误页 / 用户详情 / 账号锁定 / 未知兜底）、
 * 开发态观测面板路由（生产构建条件恒假）与全部路由入口的懒加载可解析性。
 */

import { describe, expect, it, vi } from 'vitest'

describe('应用路由骨架（Kiwi 2191）', () => {
  it('静态路由表：路径与名一一就位（未知路径兜底 404）', async () => {
    const { router } = await import('@/router/index')
    const named = (name: string): string | undefined => router.getRoutes().find((route) => route.name === name)?.path

    expect(named('Login')).toBe('/login')
    expect(named('QrLogin')).toBe('/login/qr')
    expect(named('HomeView')).toBe('/')
    expect(named('Forbidden')).toBe('/403')
    expect(named('ServerError')).toBe('/500')
    expect(named('SysUserDetail')).toBe('/sys/users/:id')
    expect(named('SystemAccountLock')).toBe('/sys/account-locks')
    expect(named('NotFound')).toBe('/:pathMatch(.*)*')
  })

  it('扫码登录路由声明公开页（meta.public），登录 / 首页保留 keepAlive 语义', async () => {
    const { router } = await import('@/router/index')
    const byName = (name: string): Record<string, unknown> | undefined =>
      router.getRoutes().find((route) => route.name === name)?.meta

    expect(byName('QrLogin')).toMatchObject({ title: '扫码登录', public: true })
    expect(byName('HomeView')).toMatchObject({ title: '工作台', keepAlive: true })
    expect(byName('SystemAccountLock')).toMatchObject({ title: '账号锁定', keepAlive: true })
    expect(byName('Login')).toMatchObject({ title: '登录' })
  })

  it('开发态追加模块观测面板路由；生产构建条件为假时不追加（不进产物）', async () => {
    const dev = await import('@/router/index')
    expect(dev.router.hasRoute('ModuleObservability')).toBe(true)
    const devLoader = dev.router.getRoutes().find((route) => route.name === 'ModuleObservability')?.components
      ?.default as (() => Promise<unknown>) | undefined
    await expect(devLoader?.()).resolves.toBeDefined()

    vi.resetModules()
    vi.stubEnv('DEV', false)
    try {
      const prod = await import('@/router/index')
      expect(prod.router.hasRoute('ModuleObservability')).toBe(false)
    } finally {
      vi.unstubAllEnvs()
    }
  })

  it('全部路由入口为懒加载函数（组件为动态 import 而非静态打包）', async () => {
    const { router } = await import('@/router/index')

    const records = router.getRoutes()
    expect(records.length).toBeGreaterThan(0)
    const loaders = records.map((record) => record.components?.default as (() => Promise<unknown>) | undefined)
    for (const loader of loaders) {
      expect(typeof loader).toBe('function')
      await expect(loader?.()).resolves.toBeDefined()
    }
  }, 120000)
})
