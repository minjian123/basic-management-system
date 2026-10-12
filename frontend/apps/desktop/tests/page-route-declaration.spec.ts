// kiwi_id: 2291
/**
 * 通用页面路由接线补充分支用例（02_13）：清单适配器（数据源 / 表单标识）真实接线、
 * 平台表单页声明懒加载器可解析，以及「未声明路由名（取路径）」「未声明 meta（归一空对象）」回落。
 */

import { createMemoryHistory, createRouter, type Router } from 'vue-router'
import { describe, expect, it, vi } from 'vitest'

import { FORM_PAGE_DECLARATIONS, ensureFormPageRoutes, pageRoute, uninstallFormPageRoutes } from '@/router/page-route'

vi.mock('@/api/registry', () => ({
  fetchDataSourceList: vi.fn(async () => ({ items: [] })),
  fetchFormKeyList: vi.fn(async () => ({ items: [] })),
}))

/** 用例自持空路由表实例（不污染应用路由单例）。 */
function createTestRouter(): Router {
  return createRouter({ history: createMemoryHistory(), routes: [] })
}

describe('通用页面路由接线补充分支（02_13）', () => {
  it('清单适配器接线：数据源与表单标识加载器可用', async () => {
    const adapter = pageRoute.adapter
    expect(adapter).toBeDefined()
    await expect(adapter?.loadDataSources?.()).resolves.toEqual({ items: [] })
    await expect(adapter?.loadFormKeys?.()).resolves.toEqual({ items: [] })
  })

  it('平台表单页声明的懒加载器可解析（列表视图按需加载）', async () => {
    for (const declaration of FORM_PAGE_DECLARATIONS) {
      const loader = declaration.list as (() => Promise<unknown>) | undefined
      expect(typeof loader).toBe('function')
      await expect(loader?.()).resolves.toBeDefined()
    }
  }, 30000)

  it('声明未声明 name / meta：路由名取路径、meta 归一为标题', () => {
    const router = createTestRouter()
    // 前置清空本模块装载登记（模块级幂等清单须为空才会走装载循环）。
    uninstallFormPageRoutes(router)

    const baseline = FORM_PAGE_DECLARATIONS.length
    FORM_PAGE_DECLARATIONS.push(
      // 未声明 name：路由名取路径；未声明 meta：归一为 `{ title }`。
      {
        formKey: 'probe-no-name',
        title: '无名页',
        path: '/probe/no-name',
        list: () => import('@/views/PlaceholderView.vue'),
      },
      {
        formKey: 'probe-no-meta',
        title: '无 meta 页',
        path: '/probe/no-meta',
        name: 'ProbeNoMeta',
        list: () => import('@/views/PlaceholderView.vue'),
      },
    )
    try {
      const names = ensureFormPageRoutes(router)
      expect(names).toContain('/probe/no-name')
      expect(names).toContain('ProbeNoMeta')
      expect(router.getRoutes().find((route) => route.name === '/probe/no-name')?.meta).toEqual({ title: '无名页' })
      expect(router.getRoutes().find((route) => route.name === 'ProbeNoMeta')?.meta).toEqual({ title: '无 meta 页' })
    } finally {
      FORM_PAGE_DECLARATIONS.splice(baseline)
      uninstallFormPageRoutes(router)
    }
  })
})
