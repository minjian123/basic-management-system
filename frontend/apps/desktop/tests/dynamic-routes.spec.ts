/** 菜单动态路由用例（05_03 / Kiwi 2231）：幂等装载 / 全量卸载（会话清理）/ 重装。 */
// kiwi_id: 2231

import { PLACEHOLDER_MENU } from '@bms/core'
import { createMemoryHistory, createRouter, type Router } from 'vue-router'
import { beforeEach, describe, expect, it } from 'vitest'

import { ensureMenuRoutes, installMenuRoutes, uninstallMenuRoutes, uninstallMenuRoutesAll } from '@/router/dynamic'

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
})
