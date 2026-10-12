// kiwi_id: 977
/** 模块宿主装配用例（清单驱动加载 → 按 mode 分派入口 → 路由注册 → 注册表派生菜单 → 卸载清理与消费接线还原）。 */

import { ComponentProvider, assembleRegistrations, releaseRegistrations, type ModuleRouteDeclaration } from '@bms/core'
import type { Router } from 'vue-router'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'

import { clearModuleError, useModuleError } from '@/module/boundary'
import {
  getModuleLoader,
  installModules,
  moduleMenuGroups,
  moduleMenuNodes,
  mountModule,
  resolveRouteModule,
  retryModule,
  unmountModule,
} from '@/module/host'
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

  // kiwi_id: 983（04_01 首个模块样例：宿主菜单装配泛化）
  it('菜单装配泛化：按 meta.group 归组、meta.devOnly 生产隐藏（卸载后消失）', async () => {
    await installModules({ router })

    const devMenu = moduleMenuGroups(true)
    expect(devMenu.map((node) => node.title)).toEqual(['演示模块'])
    expect(devMenu[0]?.children?.map((node) => node.path)).toEqual(['/demo', '/demo/toolbox'])
    expect(moduleMenuGroups(false)).toEqual([])

    unmountModule('demo')
    expect(moduleMenuGroups(true)).toEqual([])
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

  it('单模块重试：失败后仅重挂该模块（不整页刷新），路由与错误态恢复（Kiwi 982）', async () => {
    loadRemote.mockRejectedValueOnce(new Error('远端入口加载失败：HTTP 503'))
    const first = await installModules({ router })

    expect(first.failures.map((item) => item.name)).toEqual(['demo'])
    expect(router.hasRoute('DemoHome')).toBe(false)
    expect(useModuleError().value?.module).toBe('demo')

    await retryModule('demo')

    expect(getModuleLoader()?.isMounted('demo')).toBe(true)
    expect(router.hasRoute('DemoHome')).toBe(true)
    expect(useModuleError().value).toBeNull()
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

// kiwi_id: 977
describe('宿主编装载补充分支（Kiwi 977）', () => {
  it('非 Error 抛出值按字符串归因（reason 取 String(error)）', async () => {
    loadRemote.mockRejectedValueOnce('远端入口加载失败：字符串抛出')

    const summary = await installModules({ router })

    expect(summary.failures.map((item) => item.reason)).toEqual(['远端入口加载失败：字符串抛出'])
  })

  it('模块未声明路由 / 文案包时按空清单装载（可选声明缺省安全）', async () => {
    loadRemote.mockResolvedValue({
      default: {
        manifest: {
          name: 'demo',
          version: '0.1.0',
          contractVersion: (await import('@bms/core')).MODULE_CONTRACT_VERSION,
        },
        setup: () => ({ components: { 'demo:minimal': {} } }),
      },
    })

    const summary = await installModules({ router })

    expect(summary.mounted).toEqual(['demo'])
    expect(router.hasRoute('DemoHome')).toBe(false)
    expect(moduleMenuNodes()).toEqual([])
    // 卸载路径亦按缺省空清单走（无路由 / 无文案 / 无令牌 / 无登记键可还原）。
    unmountModule('demo')
    expect(getModuleLoader()?.isMounted('demo')).toBe(false)
  })

  it('重试未装载清单：拒绝（未注册不可用）', async () => {
    // 清单装载前 `loader` 未定义（模块级状态）：重置模块图后取全新实例核验该分支。
    vi.resetModules()
    const fresh = await import('@/module/host')
    await expect(fresh.retryModule('demo')).rejects.toThrow(/模块清单未装载/)
    await expect(fresh.mountModule('demo')).rejects.toThrow(/模块清单未装载/)
  })

  it('重试未登记模块拒绝；已挂载模块先卸载再重挂；路由名解析按类型判定', async () => {
    await installModules({ router })
    // ② 清单未登记该模块：拒绝。
    await expect(retryModule('nope')).rejects.toThrow(/模块未登记/)

    // ③ 已挂载：先卸载再重挂（幂等重试），仍处挂载态。
    await retryModule('demo')
    expect(getModuleLoader()?.isMounted('demo')).toBe(true)
    expect(router.hasRoute('DemoHome')).toBe(true)

    // ④ 非字符串路由名不参与模块路由解析。
    expect(resolveRouteModule(undefined)).toBeUndefined()
    expect(resolveRouteModule(42)).toBeUndefined()
    expect(resolveRouteModule('DemoHome')).toEqual({ name: 'demo', version: '0.1.0' })
    expect(resolveRouteModule('Unknown')).toBeUndefined()
  })

  it('未装载模块卸载为幂等空操作（无登记键 / 无路由 / 无文案）', () => {
    expect(() => unmountModule('never-mounted')).not.toThrow()
    expect(moduleMenuNodes()).toEqual([])
  })

  it('菜单分组：顶级项（未声明 group）、组内首项路径与图标回落、组图标缺省回落首项图标', async () => {
    const keys = assembleRegistrations(registries, 'demo', {
      routes: [
        // 顶级项：未声明 group。
        { path: '/demo/top', name: 'DemoTop', component: async () => ({}), meta: { title: '顶级项' } },
        // 分组：显式组图标。
        {
          path: '/demo/g1',
          name: 'DemoG1',
          component: async () => ({}),
          meta: { title: '组一项', group: '演示组', groupIcon: 'grid' },
        },
        {
          path: '/demo/g2',
          name: 'DemoG2',
          component: async () => ({}),
          meta: { title: '组二项', group: '演示组' },
        },
        // 分组：未声明组图标（回落组内首项图标）。
        {
          path: '/demo/h1',
          name: 'DemoH1',
          component: async () => ({}),
          meta: { title: '组一项', group: '无图标组', icon: 'star' },
        },
        // 空串 group / groupIcon 视为未声明（归一为 undefined）。
        {
          path: '/demo/e1',
          name: 'DemoE1',
          component: async () => ({}),
          meta: { title: '空串组', group: '', groupIcon: '' },
        },
      ],
    })

    const menu = moduleMenuGroups(true)

    expect(menu.map((node) => node.title)).toEqual(['顶级项', '演示组', '无图标组', '空串组'])
    expect(menu[0]).toMatchObject({ path: '/demo/top', icon: 'sparkles' })
    expect(menu[1]).toMatchObject({ path: '/demo/g1', icon: 'grid' })
    expect(menu[1]?.children?.map((node) => node.path)).toEqual(['/demo/g1', '/demo/g2'])
    expect(menu[2]).toMatchObject({ path: '/demo/h1', icon: 'star' })
    expect(menu[3]).toMatchObject({ path: '/demo/e1', icon: 'sparkles' })

    releaseRegistrations(registries, keys)
    expect(moduleMenuGroups(true)).toEqual([])
  })

  it('菜单分组：生产态隐藏 devOnly 项；未声明图标回落 sparkles', async () => {
    const keys = assembleRegistrations(registries, 'demo', {
      routes: [
        { path: '/demo/dev', name: 'DemoDev', component: async () => ({}), meta: { title: '仅开发', devOnly: true } },
        { path: '/demo/prod', name: 'DemoProd', component: async () => ({}), meta: { title: '生产可见' } },
      ],
    })

    expect(moduleMenuGroups(false).map((node) => node.title)).toEqual(['生产可见'])
    expect(moduleMenuGroups(true).map((node) => node.title)).toEqual(['仅开发', '生产可见'])

    releaseRegistrations(registries, keys)
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
