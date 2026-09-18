/** 模块宿主装配与路由注册用例（10_01）。 */

import type { ModuleRouteDeclaration } from '@bms/core'
import type { Router } from 'vue-router'
import { afterEach, describe, expect, it, vi } from 'vitest'

import { getModuleLoader, moduleMenuNodes, mountModule, unmountModule } from '@/module/host'
import { registerModuleRoutes, unregisterModuleRoutes } from '@/router/dynamic'
import { router } from '@/router'

const route = (path: string, name?: string): ModuleRouteDeclaration => ({
  path,
  name,
  component: async () => ({}),
  meta: { title: path },
})

afterEach(() => {
  if (getModuleLoader().isMounted('demo')) {
    unmountModule('demo')
  }
})

describe('registerModuleRoutes / unregisterModuleRoutes', () => {
  it('跳过根路径与已存在路由名', () => {
    const fakeRouter = {
      hasRoute: (name: string) => name === 'Exists',
      addRoute: vi.fn(),
      removeRoute: vi.fn(),
    } as unknown as Router

    const names = registerModuleRoutes(fakeRouter, [route('/'), route('/exists', 'Exists'), route('/new', 'New')])
    expect(names).toEqual(['New'])
    expect((fakeRouter.addRoute as unknown as { mock: { calls: unknown[][] } }).mock.calls).toHaveLength(1)
  })

  it('卸载已存在路由', () => {
    const fakeRouter = {
      hasRoute: () => true,
      addRoute: vi.fn(),
      removeRoute: vi.fn(),
    } as unknown as Router
    unregisterModuleRoutes(fakeRouter, ['/a', '/b'])
    expect((fakeRouter.removeRoute as unknown as { mock: { calls: unknown[][] } }).mock.calls).toHaveLength(2)
  })
})

describe('宿主模块装配', () => {
  it('加载演示模块、注册路由并派生菜单，卸载后路由移除', async () => {
    const loaded = await mountModule('demo', { router })
    expect(loaded.manifest).toMatchObject({ name: 'demo', version: '0.1.0' })
    expect(getModuleLoader().isMounted('demo')).toBe(true)
    expect(router.hasRoute('DemoHome')).toBe(true)

    expect(moduleMenuNodes('demo').map((node) => node.path)).toEqual(['/demo', '/demo/toolbox'])

    unmountModule('demo')
    expect(router.hasRoute('DemoHome')).toBe(false)
    expect(getModuleLoader().isMounted('demo')).toBe(false)
    expect(moduleMenuNodes('demo')).toEqual([])
  })
})
