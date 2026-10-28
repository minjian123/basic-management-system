/**
 * 路由守卫接线（**默认开启**）：公开页放行 → 会话就绪（导航挂起，不闪登录页）→ 动态路由装载 →
 * 权限占位判定；跳登录带 `redirect`，已登录访问登录页回跳目标。
 *
 * - **判定落核心**：决策 / 公开页 / 跳登录构造 / 站内回跳校验一律经 `@bms/core` 的
 *   `domain/route-guard`（框架无关纯函数），宿主只做接线与依赖注入；
 * - **会话就绪**：受保护路径与登录页在判定前 `await ensureSession()`（单例续期），
 *   续期期间导航挂起；公开错误页直接放行（不等待）；
 * - **动态路由**：会话就绪后幂等装载菜单路由；装载后按新路由表**重解析**当前地址
 *   （消除「刷新深链落兜底 404」）——可解析性按 `resolve(path)` 命中的**路由记录名**判定，
 *   不用 `router.hasRoute(path)`（其参数是路由 **name**，与路径不同名时恒假）；
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
  /** 会话就绪后装载平台目录快照（可异步；失败不阻断导航，仅记录原因）。 */
  ensureCatalog?: () => void | Promise<void>
  /** 当前权限码与「是否已装载」（RBAC 就绪前 `loaded` 恒假 → 占位放行）。 */
  permissions: () => { codes: readonly string[]; loaded: boolean }
  /** 是否处于「首登强制改密」态（为真时非改密页一律重定向）。 */
  mustChangePassword?: () => boolean
  /** 判定观测记录（缺省不记录）。 */
  record?: (record: AuthGuardRecord) => void
}

/** 自助改密页路径（首登强制改密拦截目标）。 */
export const MUST_CHANGE_PASSWORD_PATH = '/change-password'

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
 * 是否**免会话判定**路径（公开且非登录族；如 `/403` / `/404` / `/500` 与开发态面板）。
 *
 * 应用根以 `session.ready` 渲染骨架屏，而本函数命中的路径**不会触发会话就绪**（守卫「公开页
 * 直接放行，不等待续期」）——若仍按 `session.ready` 等待，冷启动直开错误页会**永久停在骨架屏**。
 * 故这类路径免等（直接渲染）；**登录族**（`/login` 及其子路径）不在其内——登录页需先完成就绪
 * 判定，避免闪登录页（域五 `05_03` 口径）。
 *
 * @param path 目标路径（`route.path`）。
 * @param publicPaths 公开白名单（缺省 `resolvePublicPaths()`）。
 * @returns 免会话判定返回 true。
 */
export function isSessionFreePath(path: string, publicPaths: readonly string[] = resolvePublicPaths()): boolean {
  const isLoginFamily = path === DEFAULT_LOGIN_PATH || path.startsWith(`${DEFAULT_LOGIN_PATH}/`)
  return !isLoginFamily && isPublicPath(path, publicPaths)
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
    // 守卫关闭时**仍触发一次会话就绪**：应用根以 `session.ready` 渲染骨架屏，若无人触发会永久停在
    // 骨架屏（计划 §7 第 29 项）；失败静默（与守卫开启路径同口径：不提示、不跳转）。
    void deps.ensureSession()
    // 目录快照独立于守卫：关闭守卫时同样触发一次（失败静默），避免依赖产品目录的能力无地址可用。
    void Promise.resolve(deps.ensureCatalog?.()).catch(() => undefined)
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

    // 首登强制改密：除改密页外一律重定向（不装载菜单、不做权限判定）。
    if (deps.mustChangePassword?.() === true && to.path !== MUST_CHANGE_PASSWORD_PATH) {
      record('allow', 'must-change-password')
      return { path: MUST_CHANGE_PASSWORD_PATH }
    }

    // 平台目录快照：会话就绪后、动态路由装载前（`03_02`）。失败不阻断导航，只记录原因。
    try {
      await deps.ensureCatalog?.()
    } catch {
      record('allow', 'catalog-failed')
    }

    // 动态路由：会话就绪后幂等装载；装载后若当前地址命中的路由记录发生变化则按新路由表重解析。
    // 可解析性按 `resolve(path)` 命中的**路由记录**判定（不能用 `router.hasRoute(path)`：
    // 其参数是路由 name，通用页面路由 name 为 `SystemUser` 而 path 为 `/sys/users`，恒假）。
    const matchedBefore = matchedRecordKey(router, to.path)
    await deps.ensureRoutes()
    if (matchedBefore !== matchedRecordKey(router, to.path)) {
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
 * 路径当前命中的**路由记录标识**（供「装载前后是否变化」判定，替代 `router.hasRoute`）。
 *
 * 未命中任何业务路由时（仅兜底 404 命中 / 无兜底路由）返回兜底记录标识或空串；动态路由装载后
 * 该标识变化即说明地址已被纳入路由表，须按新路由表重解析。用「记录标识前后对比」而非
 * `router.hasRoute(path)`：后者参数是路由 **name**，通用页面路由（`name: 'SystemUser'`、
 * `path: '/sys/users'`）与模块路由 name 常与 path 不同，按路径查恒假 → 刷新落兜底 404。
 *
 * @param router 路由实例。
 * @param path 目标路径。
 * @returns 路由记录标识（name 优先，无名时取记录路径；未命中返回空串）。
 */
function matchedRecordKey(router: Router, path: string): string {
  const resolved = router.resolve(path)
  const record = resolved.matched[resolved.matched.length - 1]
  if (record === undefined) {
    return ''
  }
  return record.name === undefined || record.name === null ? record.path : String(record.name)
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
