/**
 * 路由守卫判定（框架无关纯函数）：登录态 / 公开页 / 权限的决策，跳登录目标构造与站内回跳校验。
 *
 * 宿主在 `router.beforeEach` 中消费本模块：公开页先放行 → 受保护路径等会话就绪（见域五 `05_03`）
 * → 权限占位判定；**跳登录目标与回跳目标一律经本模块构造与校验**（单一来源，杜绝开放重定向与
 * 回跳循环）。
 */

import { evaluatePermission } from './permission'

/** 默认公开白名单（免登录路径）：登录页与错误页。 */
export const DEFAULT_PUBLIC_PATHS: readonly string[] = ['/login', '/403', '/404', '/500']

/** 默认登录路径。 */
export const DEFAULT_LOGIN_PATH = '/login'

/** 默认首页（登录后回跳兜底）。 */
export const DEFAULT_HOME_PATH = '/'

/** 默认无权限路径。 */
export const DEFAULT_FORBIDDEN_PATH = '/403'

/** 回跳参数名。 */
export const REDIRECT_QUERY_KEY = 'redirect'

/** 守卫决策。 */
export type AuthGuardDecision = 'allow' | 'login' | 'forbidden'

/** 守卫判定入参。 */
export interface AuthGuardInput {
  /** 是否已持有访问令牌。 */
  hasToken: boolean
  /** 目标路径（不含查询串）。 */
  path: string
  /** 公开白名单（缺省 `DEFAULT_PUBLIC_PATHS`）。 */
  publicPaths?: readonly string[]
  /** 路由是否声明为公开页（`meta.public === true`）。 */
  isPublicRoute?: boolean
  /** 路由声明的权限码（`meta.perm`；缺省 / 空数组不判定）。 */
  requiredPermissions?: readonly string[]
  /** 当前用户权限码。 */
  permissions?: readonly string[]
  /** 权限码是否已装载（RBAC 就绪前为 `false` → 占位放行，由调用方登记）。 */
  permissionsLoaded?: boolean
}

/** 登录跳转判定入参（`resolveAuthRedirect` 兼容形态）。 */
export interface AuthRedirectInput extends AuthGuardInput {
  /** 登录路径（缺省 `DEFAULT_LOGIN_PATH`）。 */
  loginPath?: string
}

/** 登录跳转目标。 */
export interface LoginLocation {
  /** 登录路径。 */
  path: string
  /** 查询参数（受保护路径回带 `redirect`）。 */
  query?: Record<string, string>
}

/**
 * 是否公开路径（精确命中或其子路径）。
 *
 * @param path 目标路径（不含查询串）。
 * @param publicPaths 公开白名单（缺省 `DEFAULT_PUBLIC_PATHS`）。
 * @returns 是否公开。
 */
export function isPublicPath(path: string, publicPaths: readonly string[] = DEFAULT_PUBLIC_PATHS): boolean {
  return publicPaths.some((prefix) => path === prefix || path.startsWith(`${prefix}/`))
}

/**
 * 判定守卫决策：未登录且非公开页 → 跳登录；已登录按权限判定（未声明 / 未装载 → 放行）。
 *
 * 不含「已登录访问登录页回跳」语义（由宿主按回跳目标处理）。
 *
 * @param input 判定入参。
 * @returns 决策。
 */
export function resolveAuthGuard(input: AuthGuardInput): AuthGuardDecision {
  const isPublic = input.isPublicRoute === true || isPublicPath(input.path, input.publicPaths)
  if (isPublic) {
    return 'allow'
  }
  if (!input.hasToken) {
    return 'login'
  }
  const required = input.requiredPermissions ?? []
  if (required.length === 0 || input.permissionsLoaded !== true) {
    return 'allow'
  }
  return evaluatePermission(input.permissions ?? [], required, 'any') ? 'allow' : 'forbidden'
}

/**
 * 判定是否需跳转登录（**兼容保留**：阶段二守卫骨架口径；完整决策请用 `resolveAuthGuard`）。
 *
 * @param input 判定入参。
 * @returns 登录跳转目标路径；无需跳转返回 `null`。
 */
export function resolveAuthRedirect(input: AuthRedirectInput): string | null {
  const loginPath = input.loginPath ?? DEFAULT_LOGIN_PATH
  return resolveAuthGuard(input) === 'login' ? loginPath : null
}

/**
 * 构造登录跳转目标：受保护路径回带 `redirect`（原 `fullPath`）；公开路径与登录页自身不带。
 *
 * @param path 目标地址（受保护路径传 `fullPath`，保留查询串与片段）。
 * @param options `loginPath` 登录路径 / `publicPaths` 公开白名单。
 * @returns 登录跳转目标。
 */
export function buildLoginLocation(
  path: string,
  options: { loginPath?: string; publicPaths?: readonly string[] } = {},
): LoginLocation {
  const loginPath = options.loginPath ?? DEFAULT_LOGIN_PATH
  const publicPaths = options.publicPaths ?? DEFAULT_PUBLIC_PATHS
  if (path === '' || path === loginPath || isPublicPath(path, publicPaths)) {
    return { path: loginPath }
  }
  return { path: loginPath, query: { [REDIRECT_QUERY_KEY]: path } }
}

/**
 * 站内回跳解析与校验（唯一安全口径）：仅接受站内相对路径，其余一律回落 `fallback`。
 *
 * 拒绝：非字符串 / 空串 / 不以单个 `/` 开头（含 `http(s)://` 等协议地址）/ 协议相对地址（`//`）/
 * 含反斜杠 / 含控制字符 / 命中公开白名单（防回跳循环）。
 *
 * @param raw 原始回跳值（通常取路由 `redirect` 查询参数）。
 * @param options `fallback` 回落目标（缺省 `DEFAULT_HOME_PATH`）/ `publicPaths` 公开白名单。
 * @returns 可安全跳转的站内目标。
 */
export function resolveSafeRedirect(
  raw: unknown,
  options: { fallback?: string; publicPaths?: readonly string[] } = {},
): string {
  const fallback = options.fallback ?? DEFAULT_HOME_PATH
  const publicPaths = options.publicPaths ?? DEFAULT_PUBLIC_PATHS
  if (typeof raw !== 'string') {
    return fallback
  }
  const target = raw.trim()
  if (!target.startsWith('/') || target.startsWith('//') || hasUnsafeChar(target)) {
    return fallback
  }
  if (isPublicPath(stripLocationSuffix(target), publicPaths)) {
    return fallback
  }
  return target
}

/**
 * 目标是否含反斜杠或控制字符（`\`、`\u0000`~`\u001f`、`\u007f`）。
 *
 * @param target 目标地址。
 */
function hasUnsafeChar(target: string): boolean {
  for (const char of target) {
    const code = char.codePointAt(0) ?? 0
    if (char === '\\' || code <= 0x1f || code === 0x7f) {
      return true
    }
  }
  return false
}

/**
 * 去掉地址的查询串与片段（公开白名单只按路径判定）。
 *
 * @param target 目标地址。
 */
function stripLocationSuffix(target: string): string {
  const index = target.search(/[?#]/)
  return index === -1 ? target : target.slice(0, index)
}
