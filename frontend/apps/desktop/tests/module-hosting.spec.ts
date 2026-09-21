// kiwi_id: 977
/** 模块宿主装配用例（清单驱动加载 → 路由注册 → 注册表派生菜单 → 卸载清理与消费接线还原）。 */

import { ComponentProvider, type ModuleRouteDeclaration } from '@bms/core'
import type { Router } from 'vue-router'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'

import { clearModuleError, useModuleError } from '@/module/boundary'
import { getModuleLoader, installModules, moduleMenuNodes, mountModule, unmountModule } from '@/module/host'
import { moduleI18n } from '@/module/i18n'
import { registries } from '@/module/registries'
import { router } from '@/router'
import { registerModuleRoutes, unregisterModuleRoutes } from '@/router/dynamic'

const MANIFEST = [{ name: 'demo', entry: 'demo', version: '0.1.0' }]

const route = (path: string, name?: string): ModuleRouteDeclaration => ({
  path,
  name,
  component: async () => ({}),
  meta: { title: path },
})

/** 以给定清单 stub 全局 fetch（后台服务不可用，一律 mock）。 */
function stubManifest(payload: unknown, ok = true, status = 200): void {
  vi.stubGlobal(
    'fetch',
    vi.fn(async () => ({ ok, status, json: async () => payload })),
  )
}

beforeEach(() => {
  stubManifest(MANIFEST)
  clearModuleError()
})

afterEach(() => {
  if (getModuleLoader()?.isMounted('demo') === true) {
    unmountModule('demo')
  }
  clearModuleError()
  vi.unstubAllGlobals()
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

describe('宿主编装载（清单驱动）', () => {
  it('清单未装载时挂载拒绝（未注册不可用）', async () => {
    await expect(mountModule('demo')).rejects.toThrow(/模块清单未装载/)
  })

  it('按清单挂载：动态路由生效、菜单取注册表快照、卸载无残留', async () => {
    const summary = await installModules({ router })
    expect(summary.mounted).toEqual(['demo'])
    expect(summary.failures).toEqual([])
    expect(getModuleLoader()?.isMounted('demo')).toBe(true)
    expect(router.hasRoute('DemoHome')).toBe(true)

    expect(moduleMenuNodes().map((node) => node.path)).toEqual(['/demo', '/demo/toolbox'])
    expect(registries.routeMenu.get('DemoHome')?.title).toBe('演示模块')

    unmountModule('demo')
    expect(router.hasRoute('DemoHome')).toBe(false)
    expect(getModuleLoader()?.isMounted('demo')).toBe(false)
    expect(moduleMenuNodes()).toEqual([])
    expect(registries.pageArea.resolveByArea('layout.header')).toEqual([])
  })

  it('渲染消费接线成对：令牌注入与文案并入在挂载后生效、卸载后还原', async () => {
    await installModules({ router })

    expect(documentThemeValue('--bms-color-primary')).toBe('#3a7bd5')
    expect(moduleI18n.translate('demo.title')).toBe('演示模块')
    expect(registries.pageArea.resolveByArea('layout.header').map((item) => item.key)).toEqual(['demo:hero'])

    unmountModule('demo')

    expect(documentThemeValue('--bms-color-primary')).toBe('')
    expect(moduleI18n.translate('demo.title')).toBeUndefined()
    expect(registries.pageArea.resolveByArea('layout.header')).toEqual([])
  })

  it('版本不匹配拒绝加载：不挂载、菜单无该项、记错误状态', async () => {
    stubManifest([{ name: 'demo', entry: 'demo', version: '9.9.9' }])
    const summary = await installModules({ router })

    expect(summary.mounted).toEqual([])
    expect(summary.failures.map((item) => item.name)).toEqual(['demo'])
    expect(summary.failures[0]?.reason).toContain('模块版本与清单不一致')
    expect(router.hasRoute('DemoHome')).toBe(false)
    expect(moduleMenuNodes()).toEqual([])
    expect(useModuleError().value?.module).toBe('demo')
  })

  it('入口未登记的模块拒绝加载其余照常', async () => {
    stubManifest([
      { name: 'unknown-module', entry: 'nope', version: '1.0.0' },
      { name: 'demo', entry: 'demo', version: '0.1.0' },
    ])
    const summary = await installModules({ router })

    expect(summary.mounted).toEqual(['demo'])
    expect(summary.failures[0]?.reason).toContain('模块入口未登记')
    expect(router.hasRoute('DemoHome')).toBe(true)
  })

  it('清单缺字段项被拒并记错误状态（其余项照常）', async () => {
    stubManifest([
      { name: 'demo', entry: 'demo' },
      { name: 'unknown-module', entry: 'demo', version: '1.0.0' },
    ])
    const summary = await installModules({ router })

    expect(summary.mounted).toEqual([])
    expect(useModuleError().value?.module).toBeTruthy()
  })

  it('装配冲突回滚本次接线（路由与登记均无残留）', async () => {
    registries.component.register(new ComponentProvider('demo:toolbox', {}))

    const summary = await installModules({ router })

    expect(summary.mounted).toEqual([])
    expect(summary.failures[0]?.reason).toContain('重复登记')
    expect(router.hasRoute('DemoHome')).toBe(false)
    expect(moduleMenuNodes()).toEqual([])
    expect(registries.component.get('demo:toolbox')?.registrationSource).toBeUndefined()

    registries.component.unregister('demo:toolbox')
  })
})

/**
 * 读取根元素令牌值。
 *
 * @param name 令牌名。
 */
function documentThemeValue(name: string): string {
  return document.documentElement.style.getPropertyValue(name)
}
