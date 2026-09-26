/**
 * 路由守卫判定（框架无关纯函数）：无令牌访问受保护路径时的登录跳转决策。
 *
 * 宿主在 `router.beforeEach` 中消费本判定，是否启用强制跳转由宿主开关控制
 * （后端登录链路未就绪前默认关闭，见任务 04-1-1 设计 §4.4）。
 */

/** 默认公开白名单（免登录路径）。 */
export const DEFAULT_PUBLIC_PATHS: readonly string[] = ['/login', '/403', '/404', '/500']

/** 默认登录路径。 */
export const DEFAULT_LOGIN_PATH = '/login'

/** 守卫判定入参。 */
export interface AuthGuardInput {
  /** 是否已持有访问令牌。 */
  hasToken: boolean
  /** 目标路径（不含查询串）。 */
  path: string
  /** 公开白名单（缺省 `DEFAULT_PUBLIC_PATHS`）。 */
  publicPaths?: readonly string[]
  /** 登录路径（缺省 `DEFAULT_LOGIN_PATH`）。 */
  loginPath?: string
}

/**
 * 判定是否需跳转登录。
 *
 * 已持令牌放行；路径命中公开白名单（精确或其子路径）放行；否则返回登录路径。
 *
 * @param input 判定入参。
 * @returns 登录跳转目标路径；无需跳转返回 `null`。
 */
export function resolveAuthRedirect(input: AuthGuardInput): string | null {
  if (input.hasToken) {
    return null
  }
  const loginPath = input.loginPath ?? DEFAULT_LOGIN_PATH
  const publicPaths = input.publicPaths ?? DEFAULT_PUBLIC_PATHS
  const isPublic = publicPaths.some((prefix) => input.path === prefix || input.path.startsWith(`${prefix}/`))
  return isPublic ? null : loginPath
}
