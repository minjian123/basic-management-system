/** 菜单数据层与路由守卫用例（Kiwi 738）：占位加载 / 展开持久化 / 权限跳转。 */

import { beforeEach, describe, expect, it, vi } from 'vitest'
import { createPinia, setActivePinia } from 'pinia'
import { createMemoryHistory, createRouter, type Router } from 'vue-router'

import { tokenManager } from '@/api/token'
import { PLACEHOLDER_MENU } from '@/config/placeholder-menu'
import { setupRouterGuard } from '@/router/guard'
import { MENU_EXPANDED_KEY, useMenuStore } from '@/stores/menu'

const hasPermMock = vi.hoisted(() => vi.fn<(codes: string | string[]) => boolean>(() => true))

vi.mock('@/utils/perm', () => ({
  hasPerm: (codes: string | string[]) => hasPermMock(codes),
  canAccess: (target: unknown) => {
    if (target === null || target === undefined) {
      return true
    }
    if (typeof target === 'string' || Array.isArray(target)) {
      return hasPermMock(target)
    }
    const node = target as { public?: boolean; permission?: string | string[] }
    if (node.public === true || node.permission === undefined) {
      return true
    }
    return hasPermMock(node.permission)
  },
}))

beforeEach(() => {
  setActivePinia(createPinia())
  localStorage.clear()
  tokenManager.setAccessToken(null)
  hasPermMock.mockReset().mockReturnValue(true)
})

async function loadPlaceholder(): Promise<ReturnType<typeof useMenuStore>> {
  const store = useMenuStore()
  store.configureLoader({ load: async () => PLACEHOLDER_MENU })
  await store.load()
  return store
}

function makeRouter(options: { login?: boolean } = {}): Router {
  const routes = [
    { path: '/public', name: 'public', component: { template: '<div />' }, meta: { public: true } },
    { path: '/secret', name: 'secret', component: { template: '<div />' } },
    { path: '/perm', name: 'perm', component: { template: '<div />' }, meta: { perm: 'x:view' } },
    { path: '/403', name: 'forbidden', component: { template: '<div />' }, meta: { public: true } },
    ...(options.login
      ? [{ path: '/login', name: 'login', component: { template: '<div />' }, meta: { public: true } }]
      : []),
  ]
  const router = createRouter({ history: createMemoryHistory(), routes })
  setupRouterGuard(router)
  return router
}

describe('菜单数据层与路由守卫（Kiwi 738）', () => {
  it('store 占位语义与加载：未注入 loader 空清单；注入后过滤 hidden 与排序', async () => {
    const bare = useMenuStore()
    await bare.load()
    expect(bare.menus).toEqual([])
    expect(bare.loaded).toBe(true)

    const store = await loadPlaceholder()
    expect(store.visibleMenus.map((item) => item.name)).toEqual([
      '工作台',
      '系统管理',
      '内容管理',
      '平台文档',
    ])
    expect(store.visibleMenus.some((item) => item.name === '隐藏页面')).toBe(false)
  })

  it('展开集：toggle / expandByPath 父链 / 持久化 / collapseAll', async () => {
    const store = await loadPlaceholder()

    store.toggleExpanded('系统管理')
    expect(store.expandedKeys).toEqual(['系统管理'])
    expect(JSON.parse(localStorage.getItem(MENU_EXPANDED_KEY) ?? '[]')).toEqual(['系统管理'])

    const chain = store.expandByPath('/system/user')
    expect(chain).toEqual(['系统管理'])
    expect(store.expandedKeys).toContain('系统管理')

    store.collapseAll()
    expect(store.expandedKeys).toEqual([])
  })

  it('搜索 filteredMenus 保留父链', async () => {
    const store = await loadPlaceholder()
    store.setKeyword('文章')
    expect(store.filteredMenus.map((item) => item.name)).toEqual(['内容管理'])
    expect(store.filteredMenus[0]?.children?.map((item) => item.name)).toEqual(['文章管理'])
  })

  it('守卫：public 放行 / 无 token 跳登录（登录路由存在）/ 权限跳 403', async () => {
    const router = makeRouter({ login: true })

    await router.push('/public')
    expect(router.currentRoute.value.path).toBe('/public')

    await router.push('/secret')
    expect(router.currentRoute.value.path).toBe('/login')
    expect(router.currentRoute.value.query.redirect).toBe('/secret')

    tokenManager.setAccessToken('test-token')
    await router.push('/secret')
    expect(router.currentRoute.value.path).toBe('/secret')

    hasPermMock.mockReturnValue(false)
    await router.push('/perm')
    expect(router.currentRoute.value.path).toBe('/403')

    hasPermMock.mockReturnValue(true)
    await router.push('/perm')
    expect(router.currentRoute.value.path).toBe('/perm')
  })

  it('守卫：登录页未就绪时放行占位（不跳不存在的 /login）', async () => {
    const router = makeRouter({ login: false })
    await router.push('/secret')
    expect(router.currentRoute.value.path).toBe('/secret')
  })
})
