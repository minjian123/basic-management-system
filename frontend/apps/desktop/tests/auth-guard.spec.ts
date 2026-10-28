/**
 * 路由守卫接线用例：04-1-1 / Kiwi 2191（骨架：开关 / 令牌判定 / 登录占位页）、
 * 05_03 / Kiwi 2231（默认开启 / 公开页 / 会话就绪不闪登录页 / 回跳 / 权限占位 / 重解析 / 观测）、
 * 01_07 / Kiwi 2243（守卫关闭仍触发一次会话就绪，避免停在骨架屏）。
 */
// kiwi_id: 2191, 2231, 2243
// kiwi_id: 2363

import { DEFAULT_PUBLIC_PATHS, PLACEHOLDER_MENU } from '@bms/core'
import { flushPromises, mount } from '@vue/test-utils'
import { createPinia } from 'pinia'
import { createMemoryHistory, createRouter, type Router } from 'vue-router'
import { afterEach, describe, expect, it, vi } from 'vitest'

import { setAccessToken } from '@/api/token'
import {
  DEV_PUBLIC_PATHS,
  installAuthGuard,
  isAuthGuardEnabled,
  isSessionFreePath,
  resolvePublicPaths,
  toRequiredPermissions,
  type AuthGuardDeps,
} from '@/router/guard'
import LoginView from '@/views/LoginView.vue'

/** 导航目标（守卫消费的字段子集）。 */
interface GuardTarget {
  /** 路径（不含查询串）。 */
  path: string
  /** 完整地址（含查询串与片段）。 */
  fullPath: string
  /** 查询参数。 */
  query: Record<string, unknown>
  /** 片段。 */
  hash: string
  /** 路由元信息。 */
  meta: { public?: boolean; perm?: string | readonly string[] }
}

/** 守卫回调（假 router 捕获用）。 */
type GuardFn = (to: GuardTarget) => unknown

/**
 * 构造导航目标。
 *
 * @param path 路径。
 * @param options `query` / `meta` / `fullPath`（缺省等于 `path`）。
 */
function target(
  path: string,
  options: { query?: Record<string, unknown>; meta?: GuardTarget['meta']; fullPath?: string } = {},
): GuardTarget {
  return {
    path,
    fullPath: options.fullPath ?? path,
    query: options.query ?? {},
    hash: '',
    meta: options.meta ?? {},
  }
}

/**
 * 装配守卫并返回触发入口。
 *
 * @param overrides 依赖覆盖项。
 * @param options `routes` 路由表模拟（路径 → 路由记录 name，`null` 表示无名记录）；
 *   `unmatched` 未命中时是否命中兜底记录（`fallback` 缺省 / `none` 无兜底路由）。
 */
function install(
  overrides: Partial<AuthGuardDeps> = {},
  options: { routes?: () => Record<string, string | null>; unmatched?: 'fallback' | 'none' } = {},
) {
  const guards: GuardFn[] = []
  /** 兜底记录 name（真实路由表 `/:pathMatch(.*)*` 的 name）。 */
  const fallback = 'NotFound'
  const routes = options.routes ?? (() => ({}))
  const router = {
    beforeEach: (fn: GuardFn) => {
      guards.push(fn)
    },
    /**
     * 模拟 `router.resolve(path)`：命中业务路由返回该记录，否则命中兜底记录或空匹配。
     *
     * @param path 目标路径。
     */
    resolve: (path: string) => {
      const table = routes()
      if (!(path in table)) {
        return { matched: options.unmatched === 'none' ? [] : [{ name: fallback, path }] }
      }
      const name = table[path]
      return { matched: [name === null ? { path } : { name, path }] }
    },
  } as unknown as Router
  const deps: AuthGuardDeps = {
    ensureSession: vi.fn().mockResolvedValue(true),
    ensureRoutes: vi.fn(),
    permissions: () => ({ codes: [], loaded: false }),
    ...overrides,
  }
  const installed = installAuthGuard(router, deps)
  /**
   * 触发守卫一次。
   *
   * @param to 导航目标。
   */
  const run = async (to: GuardTarget): Promise<unknown> => {
    const guard = guards[0]
    return guard === undefined ? undefined : await guard(to)
  }
  return { installed, run, deps }
}

afterEach(() => {
  setAccessToken(null)
  vi.unstubAllEnvs()
})

describe('isAuthGuardEnabled（Kiwi 2191 / 2231）', () => {
  it('缺省开启（不再依赖显式 on）', () => {
    expect(isAuthGuardEnabled()).toBe(true)
  })

  it('VITE_AUTH_GUARD=on 仍开启（兼容旧值）', () => {
    vi.stubEnv('VITE_AUTH_GUARD', 'on')
    expect(isAuthGuardEnabled()).toBe(true)
  })

  it('VITE_AUTH_GUARD=off 关闭', () => {
    vi.stubEnv('VITE_AUTH_GUARD', 'off')
    expect(isAuthGuardEnabled()).toBe(false)
  })
})

describe('toRequiredPermissions（Kiwi 2231）', () => {
  it('权限码归一：单码 / 数组去空 / 未声明；空串视为未声明', () => {
    expect(toRequiredPermissions(undefined)).toEqual([])
    expect(toRequiredPermissions('')).toEqual([])
    expect(toRequiredPermissions('user:query')).toEqual(['user:query'])
    expect(toRequiredPermissions(['user:query', '', 'user:edit'])).toEqual(['user:query', 'user:edit'])
  })
})

describe('resolvePublicPaths（Kiwi 2231）', () => {
  it('开发态含 DEV 专属路由（观测面板免登录）', () => {
    const paths = resolvePublicPaths(true)
    for (const path of DEFAULT_PUBLIC_PATHS) {
      expect(paths).toContain(path)
    }
    for (const path of DEV_PUBLIC_PATHS) {
      expect(paths).toContain(path)
    }
  })

  it('生产态不含 DEV 路由', () => {
    expect(resolvePublicPaths(false)).toEqual(DEFAULT_PUBLIC_PATHS)
  })
})

describe('installAuthGuard 开关（Kiwi 2191 / 2231）', () => {
  it('开关关闭时不注册钩子，但仍触发一次会话就绪（计划 §7 第 29 项）', () => {
    vi.stubEnv('VITE_AUTH_GUARD', 'off')
    const ensureSession = vi.fn().mockResolvedValue(false)
    const { installed } = install({ ensureSession })
    expect(installed).toBe(false)
    expect(ensureSession).toHaveBeenCalledTimes(1)
  })

  it('默认开启时注册钩子', () => {
    expect(install().installed).toBe(true)
  })
})

describe('installAuthGuard 目录钩子（07B 03_02）', () => {
  it('会话就绪后、动态路由装载前调用一次', async () => {
    setAccessToken('t1')
    const order: string[] = []
    const ensureCatalog = vi.fn(() => {
      order.push('catalog')
    })
    const ensureRoutes = vi.fn(() => {
      order.push('routes')
    })
    const { run } = install({ ensureCatalog, ensureRoutes })

    expect(await run(target('/sys/users'))).toBe(true)
    expect(order).toEqual(['catalog', 'routes'])
  })

  it('目录钩子抛错不阻断导航，观测记 catalog-failed', async () => {
    setAccessToken('t1')
    const record = vi.fn()
    const ensureCatalog = vi.fn().mockRejectedValue(new Error('boom'))
    const { run } = install({ ensureCatalog, record })

    expect(await run(target('/sys/users'))).toBe(true)
    expect(record).toHaveBeenCalledWith(expect.objectContaining({ reason: 'catalog-failed' }))
  })

  it('守卫关闭时仍触发一次目录装载（失败静默）', async () => {
    vi.stubEnv('VITE_AUTH_GUARD', 'off')
    const ensureCatalog = vi.fn().mockRejectedValue(new Error('boom'))

    install({ ensureCatalog })
    await flushPromises()

    expect(ensureCatalog).toHaveBeenCalledTimes(1)
  })
})

describe('installAuthGuard 判定与回跳（Kiwi 2231）', () => {
  it('未登录：先等待会话就绪，再跳登录并带回跳参数', async () => {
    const ensureSession = vi.fn().mockResolvedValue(false)
    const { run } = install({ ensureSession })

    const result = await run(target('/org/users', { query: { page: '2' }, fullPath: '/org/users?page=2' }))

    expect(ensureSession).toHaveBeenCalledTimes(1)
    expect(result).toEqual({ path: '/login', query: { redirect: '/org/users?page=2' } })
  })

  it('刷新页面（内存令牌未恢复）但续期成功 → 放行，不跳登录页（不闪登录页）', async () => {
    const ensureSession = vi.fn().mockResolvedValue(true)
    const { run } = install({ ensureSession })

    expect(await run(target('/org/users'))).toBe(true)
    expect(ensureSession).toHaveBeenCalledTimes(1)
  })

  it('首登强制改密：非改密页重定向到改密页，改密页放行', async () => {
    setAccessToken('t1')
    const { run } = install(
      { mustChangePassword: () => true },
      { routes: () => ({ '/change-password': 'ChangePassword' }) },
    )

    expect(await run(target('/org/users'))).toEqual({ path: '/change-password' })
    expect(await run(target('/change-password'))).toBe(true)
  })

  it('公开错误页不等待会话（直接放行）', async () => {
    const ensureSession = vi.fn()
    const { run } = install({ ensureSession })

    expect(await run(target('/404'))).toBe(true)
    expect(ensureSession).not.toHaveBeenCalled()
  })

  it('公开页（meta.public）放行且不等待会话', async () => {
    const ensureSession = vi.fn()
    const { run } = install({ ensureSession })

    expect(await run(target('/sso/callback', { meta: { public: true } }))).toBe(true)
    expect(ensureSession).not.toHaveBeenCalled()
  })

  it('已登录访问登录页 → 回跳 redirect（非法 / 缺失回首页）', async () => {
    setAccessToken('t1')
    const { run } = install()

    expect(await run(target('/login', { query: { redirect: '/org/users?page=2' } }))).toBe('/org/users?page=2')
    expect(await run(target('/login', { query: { redirect: 'https://evil.example.com' } }))).toBe('/')
    expect(await run(target('/login'))).toBe('/')
    expect(await run(target('/login', { query: { redirect: '/login' } }))).toBe('/')
  })

  it('未登录访问登录页 → 展示登录页（不回跳）', async () => {
    const { run } = install({ ensureSession: vi.fn().mockResolvedValue(false) })
    expect(await run(target('/login', { query: { redirect: '/org/users' } }))).toBe(true)
  })

  it('meta.perm：权限已装载且不满足 → 跳 403；未装载 → 占位放行', async () => {
    setAccessToken('t1')
    const denied = install({ permissions: () => ({ codes: ['user:edit'], loaded: true }) })
    const allowed = install({ permissions: () => ({ codes: [], loaded: false }) })

    expect(await denied.run(target('/org/users', { meta: { perm: 'user:query' } }))).toEqual({ path: '/403' })
    expect(await allowed.run(target('/org/users', { meta: { perm: 'user:query' } }))).toBe(true)
  })

  it('meta.perm：权限已装载且满足 → 放行', async () => {
    setAccessToken('t1')
    const { run } = install({ permissions: () => ({ codes: ['user:query'], loaded: true }) })
    expect(await run(target('/org/users', { meta: { perm: ['user:query', 'user:edit'] } }))).toBe(true)
  })

  it('动态路由：会话就绪后幂等装载，装载后可解析则按新路由表重解析', async () => {
    let installed = false
    const ensureRoutes = vi.fn(() => {
      installed = true
    })
    const { run } = install(
      { ensureSession: vi.fn().mockResolvedValue(true), ensureRoutes },
      { routes: () => (installed ? { '/system/user': '/system/user' } : {}) },
    )

    expect(await run(target('/system/user', { query: { from: 'deep' } }))).toEqual({
      path: '/system/user',
      query: { from: 'deep' },
      hash: '',
      replace: true,
    })
    expect(ensureRoutes).toHaveBeenCalledTimes(1)
  })

  it('动态路由：已在路由表内（装载前后均可解析）不重解析', async () => {
    const ensureRoutes = vi.fn()
    const { run } = install({ ensureRoutes }, { routes: () => ({ '/system/user': '/system/user' }) })

    expect(await run(target('/system/user'))).toBe(true)
    expect(ensureRoutes).toHaveBeenCalledTimes(1)
  })

  it('动态路由：路由 name 与 path 不同（通用页面路由 / 模块路由）同样触发重解析', async () => {
    // 回归用例：曾按 `router.hasRoute(path)` 判定，而该 API 参数是路由 name；通用页面路由
    // `name: 'SystemUser'` / `path: '/sys/users'` 与模块路由 name≠path 时判定恒假 → 刷新落 404。
    let installed = false
    const ensureRoutes = vi.fn(() => {
      installed = true
    })
    const { run, deps } = install({ ensureRoutes }, { routes: () => (installed ? { '/sys/users': 'SystemUser' } : {}) })

    expect(await run(target('/sys/users', { query: { page: '2' } }))).toEqual({
      path: '/sys/users',
      query: { page: '2' },
      hash: '',
      replace: true,
    })
    expect(ensureRoutes).toHaveBeenCalledTimes(1)
    expect(deps.ensureRoutes).toHaveBeenCalledTimes(1)
  })

  it('动态路由：装载后仍不可解析（未下发菜单）→ 不重解析，落兜底 404', async () => {
    const ensureRoutes = vi.fn()
    const { run } = install({ ensureRoutes })

    expect(await run(target('/sys/unknown'))).toBe(true)
    expect(ensureRoutes).toHaveBeenCalledTimes(1)
  })

  it('动态路由：无名记录按记录路径判定；无兜底路由时按空标识判定', async () => {
    let installed = false
    const ensureRoutes = vi.fn(() => {
      installed = true
    })
    // 无名记录（`name` 未声明）装载后出现：记录路径与兜底路径不同 → 判定为「已可解析」。
    const unnamed = install(
      { ensureRoutes },
      { routes: () => (installed ? { '/sys/raw': null } : {}), unmatched: 'none' },
    )
    expect(await unnamed.run(target('/sys/raw'))).toEqual({
      path: '/sys/raw',
      query: {},
      hash: '',
      replace: true,
    })

    // 无兜底路由（空匹配）且装载前后均不可解析 → 标识恒为空串 → 不重解析。
    installed = false
    const empty = install({ ensureRoutes: vi.fn() }, { unmatched: 'none' })
    expect(await empty.run(target('/sys/raw'))).toBe(true)
  })

  it('判定观测：每次判定记一条（决策 / 路径 / 原因），放行也记', async () => {
    const record = vi.fn()
    const { run } = install({ ensureSession: vi.fn().mockResolvedValue(false), record })

    await run(target('/org/users'))
    expect(record).toHaveBeenCalledWith({ decision: 'login', path: '/org/users', reason: 'no-session' })

    record.mockClear()
    setAccessToken('t1')
    await run(target('/org/users'))
    expect(record).toHaveBeenCalledWith({ decision: 'allow', path: '/org/users', reason: 'session-ready' })
  })

  it('判定观测：权限未装载的放行带明确原因（阶段七核对来源）', async () => {
    const record = vi.fn()
    setAccessToken('t1')
    const { run } = install({ record })
    await run(target('/org/users', { meta: { perm: 'user:query' } }))
    expect(record).toHaveBeenCalledWith({ decision: 'allow', path: '/org/users', reason: 'perm-not-loaded' })
  })
})

describe('菜单动态路由与守卫协同（Kiwi 2231）', () => {
  it('公开白名单与占位菜单不冲突（占位菜单路径均非公开）', () => {
    const publicPaths = resolvePublicPaths(false)
    for (const node of PLACEHOLDER_MENU) {
      expect(publicPaths).not.toContain(node.path)
    }
  })

  it('memory router 可注册守卫（集成：beforeEach 已装配）', () => {
    const router = createRouter({ history: createMemoryHistory(), routes: [] })
    expect(
      installAuthGuard(router, {
        ensureSession: vi.fn().mockResolvedValue(false),
        ensureRoutes: vi.fn(),
        permissions: () => ({ codes: [], loaded: false }),
      }),
    ).toBe(true)
  })
})

describe('LoginView 登录页可达（Kiwi 2191）', () => {
  it('渲染真实登录表单（占位页已由 05_01 替换，登录页自身用例见 Kiwi 2232）', async () => {
    const router = createRouter({
      history: createMemoryHistory(),
      routes: [{ path: '/login', name: 'Login', component: { template: '<div />' } }],
    })
    await router.push('/login')
    const wrapper = mount(LoginView, { global: { plugins: [createPinia(), router] } })
    await flushPromises()
    expect(wrapper.find('[data-test="login-view"]').exists()).toBe(true)
    expect(wrapper.find('[data-test="login-form"]').exists()).toBe(true)
    expect(wrapper.find('[data-test="login-account"]').exists()).toBe(true)
    expect(wrapper.find('[data-test="login-password"]').exists()).toBe(true)
  })
})

describe('isSessionFreePath（免会话判定路径：错误页冷启动不落骨架屏）', () => {
  it('错误页与开发态面板：免判定（不等待会话就绪）', () => {
    for (const path of ['/403', '/404', '/500', '/dev/module-observability']) {
      expect(isSessionFreePath(path, resolvePublicPaths())).toBe(true)
    }
  })

  it('登录族（含子路径）：仍需等待就绪判定（避免闪登录页）', () => {
    for (const path of ['/login', '/login/qr', '/login/qr/scan']) {
      expect(isSessionFreePath(path, resolvePublicPaths())).toBe(false)
    }
  })

  it('受保护路径：不属免判定（公开白名单之外）', () => {
    for (const path of ['/', '/sys/users', '/sys/users/1', '/demo']) {
      expect(isSessionFreePath(path, resolvePublicPaths())).toBe(false)
    }
  })

  it('缺省白名单参数：与显式传入等价', () => {
    expect(isSessionFreePath('/404')).toBe(true)
    expect(isSessionFreePath('/login')).toBe(false)
  })
})
