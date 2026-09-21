// kiwi_id: 977
/** 模块宿主装配用例（清单驱动加载 → 按 mode 分派入口 → 路由注册 → 注册表派生菜单 → 卸载清理与消费接线还原）。 */

import { ComponentProvider, type ModuleRouteDeclaration } from '@bms/core'
import type { Router } from 'vue-router'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'

import { clearModuleError, useModuleError } from '@/module/boundary'
import { getModuleLoader, installModules, moduleMenuNodes, mountModule, unmountModule } from '@/module/host'
import { MODULE_REMOTE_ENTRY_TYPE } from '@/module/federation'
import { moduleI18n } from '@/module/i18n'
import { registries } from '@/module/registries'
import { router } from '@/router'
import { registerModuleRoutes, unregisterModuleRoutes } from '@/router/dynamic'

import { demoDefinition, LOCAL_ENTRY, REMOTE_ENTRY } from './support/module-fixture'

/** Module Federation 运行时替身（插件在 Vitest 环境空转，见任务 02_01 详细设计 §3.7）。 */
const { registerRemotes, loadRemote } = vi.hoisted(() => ({ registerRemotes: vi.fn(), loadRemote: vi.fn() }))
vi.mock('@module-federation/runtime', () => ({ registerRemotes, loadRemote }))

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
  registerRemotes.mockReset()
  loadRemote.mockReset()
  loadRemote.mockResolvedValue({ default: demoDefinition() })
  stubManifest([REMOTE_ENTRY])
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

describe('宿主编装载（清单驱动 · 按 mode 分派入口）', () => {
  it('清单未装载时挂载拒绝（未注册不可用）', async () => {
    await expect(mountModule('demo')).rejects.toThrow(/模块清单未装载/)
  })

  it('按清单挂载远端模块：动态路由生效、菜单取注册表快照、卸载无残留', async () => {
    const summary = await installModules({ router })
    expect(summary.mounted).toEqual(['demo'])
    expect(summary.failures).toEqual([])
    expect(getModuleLoader()?.isMounted('demo')).toBe(true)
    expect(router.hasRoute('DemoHome')).toBe(true)

    // 远端容器按清单名 / 入口 URL / 入口类型（ESM）经运行时登记，并按暴露键加载
    expect(registerRemotes).toHaveBeenCalledWith(
      [{ name: 'demo', entry: REMOTE_ENTRY.entry, type: MODULE_REMOTE_ENTRY_TYPE }],
      { force: true },
    )
    expect(loadRemote).toHaveBeenCalledWith('demo/module')

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

  it('两形态共存：remote 走 MF 运行时、local 走宿主本地入口表（未登记即拒绝）', async () => {
    stubManifest([REMOTE_ENTRY, LOCAL_ENTRY])
    const summary = await installModules({ router })

    expect(summary.mounted).toEqual(['demo'])
    expect(summary.failures.map((item) => item.name)).toEqual(['legacy'])
    expect(summary.failures[0]?.reason).toContain('模块入口未登记')
    expect(router.hasRoute('DemoHome')).toBe(true)
  })

  it('停用项（enabled: false）不加载：计入 disabled、不挂载、菜单无该项、不记错误状态', async () => {
    stubManifest([{ ...REMOTE_ENTRY, enabled: false }])
    const summary = await installModules({ router })

    expect(summary.mounted).toEqual([])
    expect(summary.disabled).toEqual(['demo'])
    expect(summary.failures).toEqual([])
    expect(getModuleLoader()?.isMounted('demo')).toBe(false)
    expect(router.hasRoute('DemoHome')).toBe(false)
    expect(moduleMenuNodes()).toEqual([])
    expect(useModuleError().value).toBeNull()
  })

  it('契约版本不匹配拒绝加载：不挂载、记错误状态（契约升级须模块适配）', async () => {
    loadRemote.mockResolvedValue({
      default: { manifest: { name: 'demo', version: '0.1.0', contractVersion: 999 }, setup: () => ({}) },
    })
    const summary = await installModules({ router })

    expect(summary.mounted).toEqual([])
    expect(summary.failures[0]?.reason).toContain('模块契约版本不匹配')
    expect(router.hasRoute('DemoHome')).toBe(false)
  })

  it('版本不匹配拒绝加载：不挂载、菜单无该项、记错误状态', async () => {
    loadRemote.mockResolvedValue({
      default: { manifest: { name: 'demo', version: '9.9.9', contractVersion: 1 }, setup: () => ({}) },
    })
    const summary = await installModules({ router })

    expect(summary.mounted).toEqual([])
    expect(summary.failures.map((item) => item.name)).toEqual(['demo'])
    expect(summary.failures[0]?.reason).toContain('模块版本与清单不一致')
    expect(router.hasRoute('DemoHome')).toBe(false)
    expect(moduleMenuNodes()).toEqual([])
    expect(useModuleError().value?.module).toBe('demo')
  })

  it('远端不可达拒绝加载且其余项照常（错误原样上抛、记错误状态）', async () => {
    stubManifest([
      { name: 'broken', entry: 'http://localhost:5002/missing/remoteEntry.js', version: '1.0.0', mode: 'remote' },
      REMOTE_ENTRY,
    ])
    loadRemote.mockImplementation(async (id: string) => {
      if (id.startsWith('broken/')) {
        throw new Error('远端入口加载失败：HTTP 404')
      }
      return { default: demoDefinition() }
    })

    const summary = await installModules({ router })

    expect(summary.mounted).toEqual(['demo'])
    expect(summary.failures[0]?.reason).toContain('远端入口加载失败')
    expect(router.hasRoute('DemoHome')).toBe(true)
  })

  it('清单缺字段项被拒并记错误状态（其余项照常）', async () => {
    stubManifest([{ name: 'demo', entry: 'http://localhost:5002/remoteEntry.js' }, REMOTE_ENTRY])

    const summary = await installModules({ router })

    expect(summary.mounted).toEqual(['demo'])
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
