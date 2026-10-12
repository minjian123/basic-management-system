/** 菜单动态路由用例（05_03 / Kiwi 2231）：幂等装载 / 全量卸载（会话清理）/ 重装。 */
// kiwi_id: 2231

import { PLACEHOLDER_MENU } from '@bms/core'
import { createMemoryHistory, createRouter, type Router } from 'vue-router'
import { beforeEach, describe, expect, it } from 'vitest'

import {
  ensureMenuRoutes,
  installMenuRoutes,
  menuPaths,
  registerModuleRoutes,
  uninstallMenuRoutes,
  uninstallMenuRoutesAll,
  unregisterModuleRoutes,
} from '@/router/dynamic'

/** 空路由表实例（用例自持，不污染应用路由单例）。 */
let router: Router

beforeEach(() => {
  router = createRouter({ history: createMemoryHistory(), routes: [] })
  // 清空模块级装载登记（用例隔离；对新实例为空操作）。
  uninstallMenuRoutesAll(router)
})

describe('菜单动态路由（Kiwi 2231）', () => {
  it('幂等装载：注册占位菜单路由并返回路径清单（跳过根路径）', () => {
    const paths = ensureMenuRoutes(router, PLACEHOLDER_MENU)

    expect(paths.length).toBeGreaterThan(0)
    expect(paths).not.toContain('/')
    for (const path of paths) {
      expect(router.hasRoute(path)).toBe(true)
    }
  })

  it('幂等装载：重复调用不重复注册、返回同一清单', () => {
    const first = ensureMenuRoutes(router, PLACEHOLDER_MENU)
    const second = ensureMenuRoutes(router, PLACEHOLDER_MENU)

    expect(second).toEqual(first)
  })

  it('全量卸载（会话清理）：菜单路由不可解析，可重新装载', () => {
    const paths = ensureMenuRoutes(router, PLACEHOLDER_MENU)

    uninstallMenuRoutesAll(router)
    for (const path of paths) {
      expect(router.hasRoute(path)).toBe(false)
    }

    expect(ensureMenuRoutes(router, PLACEHOLDER_MENU)).toEqual(paths)
    for (const path of paths) {
      expect(router.hasRoute(path)).toBe(true)
    }
  })

  it('按路径卸载（既有口径）与幂等装载配套', () => {
    const paths = installMenuRoutes(router, PLACEHOLDER_MENU)

    uninstallMenuRoutes(router, paths)
    for (const path of paths) {
      expect(router.hasRoute(path)).toBe(false)
    }
  })

  it('跳过已存在路由（不覆盖静态 / 模块路由）', () => {
    router.addRoute({ path: '/system/user', name: '/system/user', component: { template: '<div />' } })

    const paths = ensureMenuRoutes(router, PLACEHOLDER_MENU)

    expect(paths).not.toContain('/system/user')
    expect(router.hasRoute('/system/user')).toBe(true)
  })

  it('模块路由注册：跳过根路径与已存在路由名，按名卸载（幂等）', () => {
    router.addRoute({ path: '/exists', name: 'Exists', component: { template: '<div />' } })

    const names = registerModuleRoutes(router, [
      { path: '/', name: 'Root', component: async () => ({}), meta: { title: '根' } },
      { path: '/exists', name: 'Exists', component: async () => ({}), meta: { title: '已存在' } },
      // 未声明 name：以路径为路由名；未声明 meta：归一为空对象。
      { path: '/module/raw', component: async () => ({}) },
    ])

    expect(names).toEqual(['/module/raw'])
    expect(router.hasRoute('/module/raw')).toBe(true)
    expect(router.getRoutes().find((route) => route.name === '/module/raw')?.meta).toEqual({})

    unregisterModuleRoutes(router, names)
    expect(router.hasRoute('/module/raw')).toBe(false)
    // 幂等：重复卸载不抛错。
    unregisterModuleRoutes(router, names)
    expect(router.hasRoute('/module/raw')).toBe(false)
  })

  it('菜单树全部可注册路径（调试用）与占位菜单同源', () => {
    const paths = menuPaths(PLACEHOLDER_MENU)
    expect(paths).toContain('/system/user')
    expect(paths).toContain('/system/dict/data')
    expect(paths).toHaveLength(8)
  })

  it('占位路由组件为可解析的懒加载器（PlaceholderView 按需加载）', async () => {
    const paths = installMenuRoutes(router, PLACEHOLDER_MENU)
    const loader = router.getRoutes().find((route) => route.name === paths[0])?.components?.default as
      (() => Promise<unknown>) | undefined

    expect(typeof loader).toBe('function')
    await expect(loader?.()).resolves.toBeDefined()
  }, 30000)

  it('菜单节点缺标题时按空串回落（后端菜单数据防御）', () => {
    // 菜单标题按契约必带；此处以缺标题节点驱动 `node?.title ?? ''` 回落。
    const menu = [{ path: '/probe/no-title', title: undefined as unknown as string, name: 'NoTitle' }]
    const paths = installMenuRoutes(router, menu)

    expect(paths).toEqual(['/probe/no-title'])
    expect(router.getRoutes().find((route) => route.name === '/probe/no-title')?.meta).toEqual({ title: '' })
  })
})
