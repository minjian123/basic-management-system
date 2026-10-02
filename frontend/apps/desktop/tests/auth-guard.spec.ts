/**
 * 路由守卫接线用例：04-1-1 / Kiwi 2191（骨架：开关 / 令牌判定 / 登录占位页）、
 * 05_03 / Kiwi 2231（默认开启 / 公开页 / 会话就绪不闪登录页 / 回跳 / 权限占位 / 重解析 / 观测）。
 */
// kiwi_id: 2191, 2231

import { DEFAULT_PUBLIC_PATHS, PLACEHOLDER_MENU } from '@bms/core'
import { mount } from '@vue/test-utils'
import { createMemoryHistory, createRouter, type Router } from 'vue-router'
import { afterEach, describe, expect, it, vi } from 'vitest'

import { setAccessToken } from '@/api/token'
import {
  DEV_PUBLIC_PATHS,
  installAuthGuard,
  isAuthGuardEnabled,
  resolvePublicPaths,
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
 * @param options `hasRoute` 判定（缺省恒假）。
 */
function install(overrides: Partial<AuthGuardDeps> = {}, options: { hasRoute?: (path: string) => boolean } = {}) {
  const guards: GuardFn[] = []
  const router = {
    beforeEach: (fn: GuardFn) => {
      guards.push(fn)
    },
    hasRoute: options.hasRoute ?? (() => false),
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
  it('开关关闭时不注册钩子', () => {
    vi.stubEnv('VITE_AUTH_GUARD', 'off')
    const { installed } = install()
    expect(installed).toBe(false)
  })

  it('默认开启时注册钩子', () => {
    expect(install().installed).toBe(true)
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
    const { run } = install({ ensureSession: vi.fn().mockResolvedValue(true), ensureRoutes }, { hasRoute: () => installed })

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
    const { run } = install({ ensureRoutes }, { hasRoute: () => true })

    expect(await run(target('/system/user'))).toBe(true)
    expect(ensureRoutes).toHaveBeenCalledTimes(1)
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
    expect(installAuthGuard(router, {
      ensureSession: vi.fn().mockResolvedValue(false),
      ensureRoutes: vi.fn(),
      permissions: () => ({ codes: [], loaded: false }),
    })).toBe(true)
  })
})

describe('LoginView 占位页（Kiwi 2191）', () => {
  it('渲染登录占位提示', () => {
    const wrapper = mount(LoginView)
    expect(wrapper.text()).toContain('登录')
    expect(wrapper.text()).toContain('阶段六')
  })
})
