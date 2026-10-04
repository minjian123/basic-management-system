/**
 * 路由守卫接线（**默认开启**）：公开页放行 → 会话就绪（导航挂起，不闪登录页）→ 动态路由装载 →
 * 权限占位判定；跳登录带 `redirect`，已登录访问登录页回跳目标。
 *
 * - **判定落核心**：决策 / 公开页 / 跳登录构造 / 站内回跳校验一律经 `@bms/core` 的
 *   `domain/route-guard`（框架无关纯函数），宿主只做接线与依赖注入；
 * - **会话就绪**：受保护路径与登录页在判定前 `await ensureSession()`（单例续期），
 *   续期期间导航挂起；公开错误页直接放行（不等待）；
 * - **动态路由**：会话就绪后幂等装载菜单路由；装载后按新路由表**重解析**当前地址
 *   （消除「刷新深链落兜底 404」）；
 * - **权限占位**：`meta.perm` 判定机制就位，权限未装载（RBAC 就绪前）**放行并记录原因**；
 * - **观测**：每次判定记一条（决策 / 路径 / 原因），经宿主注入的 `record` 落既有观测通道。
 */

import {
  DEFAULT_FORBIDDEN_PATH,
  DEFAULT_LOGIN_PATH,
  DEFAULT_PUBLIC_PATHS,
  buildLoginLocation,
  isPublicPath,
  resolveAuthGuard,
  resolveSafeRedirect,
  type AuthGuardDecision,
} from '@bms/core'
import type { Router } from 'vue-router'

import { getAccessToken } from '@/api/token'

/** 开发态专属公开路由（观测面板；生产无此路由）。 */
export const DEV_PUBLIC_PATHS: readonly string[] = ['/dev/module-observability']

/** 守卫决策记录（观测用：只记路径与原因，不含令牌与查询串）。 */
export interface AuthGuardRecord {
  /** 决策。 */
  decision: AuthGuardDecision
  /** 目标路径（不含查询串）。 */
  path: string
  /** 决策原因（枚举化短句）。 */
  reason: string
}

/** 守卫依赖（由宿主入口注入；守卫自身不依赖 store 与路由实例之外的状态）。 */
export interface AuthGuardDeps {
  /** 会话就绪（单例静默续期；返回是否具备可用登录态）。 */
  ensureSession: () => Promise<boolean>
  /** 会话就绪后幂等装载动态（菜单）路由（可异步：动态菜单需先取数）。 */
  ensureRoutes: () => void | Promise<void>
  /** 当前权限码与「是否已装载」（RBAC 就绪前 `loaded` 恒假 → 占位放行）。 */
  permissions: () => { codes: readonly string[]; loaded: boolean }
  /** 判定观测记录（缺省不记录）。 */
  record?: (record: AuthGuardRecord) => void
}

/**
 * 守卫是否启用（**缺省开启**；显式 `VITE_AUTH_GUARD=off` 关闭）。
 *
 * @returns 是否启用。
 */
export function isAuthGuardEnabled(): boolean {
  return import.meta.env.VITE_AUTH_GUARD !== 'off'
}

/**
 * 公开白名单（核心常量 + 开发态 DEV 专属路由）。
 *
 * @param dev 是否开发态（缺省 `import.meta.env.DEV`）。
 * @returns 公开路径清单。
 */
export function resolvePublicPaths(dev: boolean = import.meta.env.DEV): readonly string[] {
  return dev ? [...DEFAULT_PUBLIC_PATHS, ...DEV_PUBLIC_PATHS] : DEFAULT_PUBLIC_PATHS
}

/**
 * 安装认证守卫；开关关闭（`off`）时不注册任何钩子。
 *
 * @param router 路由实例。
 * @param deps 依赖（会话就绪 / 动态路由 / 权限 / 观测）。
 * @returns 是否已注册守卫。
 */
export function installAuthGuard(router: Router, deps: AuthGuardDeps): boolean {
  if (!isAuthGuardEnabled()) {
    return false
  }
  router.beforeEach(async (to) => {
    const publicPaths = resolvePublicPaths()
    const record = (decision: AuthGuardDecision, reason: string): void => {
      deps.record?.({ decision, path: to.path, reason })
    }
    const hasToken = getAccessToken() !== null
    const isPublicRoute = to.meta.public === true
    const isLoginRoute = to.path === DEFAULT_LOGIN_PATH

    // 公开错误页等：不等待会话续期，直接放行（错误页不被会话链路拖慢）。
    if (!isLoginRoute && (isPublicRoute || isPublicPath(to.path, publicPaths))) {
      record('allow', isPublicRoute ? 'public-route' : 'public')
      return true
    }

    // 会话就绪：单例续期，续期期间导航挂起 → 不闪登录页。
    const ready = hasToken || (await deps.ensureSession())

    // 登录页：已登录回跳目标（无 / 非法回首页）；未登录正常展示登录页。
    if (isLoginRoute) {
      if (!ready) {
        record('allow', 'login-page')
        return true
      }
      const target = resolveSafeRedirect(to.query.redirect, { publicPaths })
      record('allow', 'signed-in-redirect')
      return target
    }

    if (!ready) {
      record('login', 'no-session')
      return buildLoginLocation(to.fullPath, { publicPaths })
    }

    // 动态路由：会话就绪后幂等装载；装载后若当前地址可解析则按新路由表重解析。
    const matchedBefore = router.hasRoute(to.path)
    await deps.ensureRoutes()
    if (!matchedBefore && router.hasRoute(to.path)) {
      record('allow', 'routes-installed')
      return { path: to.path, query: to.query, hash: to.hash, replace: true }
    }

    const required = toRequiredPermissions(to.meta.perm)
    const { codes, loaded } = deps.permissions()
    const decision = resolveAuthGuard({
      hasToken: true,
      path: to.path,
      publicPaths,
      isPublicRoute,
      requiredPermissions: required,
      permissions: codes,
      permissionsLoaded: loaded,
    })
    if (decision === 'forbidden') {
      record('forbidden', 'perm-denied')
      return { path: DEFAULT_FORBIDDEN_PATH }
    }
    record('allow', permissionReason(required, loaded))
    return true
  })
  return true
}

/**
 * 归一化路由声明的权限码（`meta.perm`）。
 *
 * @param raw 单个权限码或权限码数组（可空）。
 * @returns 权限码清单（去空项）。
 */
export function toRequiredPermissions(raw: string | readonly string[] | undefined): readonly string[] {
  if (raw === undefined) {
    return []
  }
  if (typeof raw === 'string') {
    return raw === '' ? [] : [raw]
  }
  return raw.filter((code) => code !== '')
}

/**
 * 放行原因（权限维度）：未声明 / 已授予 / 未装载占位。
 *
 * @param required 路由要求的权限码。
 * @param loaded 权限是否已装载。
 */
function permissionReason(required: readonly string[], loaded: boolean): string {
  if (required.length === 0) {
    return 'session-ready'
  }
  return loaded ? 'perm-granted' : 'perm-not-loaded'
}
