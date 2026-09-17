/**
 * HTTP 适配注入：统一提示 / 登录与 403 跳转 / 刷新处理器。
 *
 * 核心层（`http` / `request` / `token`）**框架无关**，不直接依赖 UI 库与路由；
 * 各端入口按需注入（PC：`ElMessage` + `router.push`；移动端：Vant 轻提示）。
 * 未注入时：提示仅走根系日志、跳转为空操作、刷新按占位降级（视为未接入）。
 */

/** HTTP 适配钩子 */
export interface HttpAdapter {
  /** 统一错误提示（缺省不弹 UI） */
  notify?: (message: string, level?: 'error' | 'warning') => void
  /** 会话失效跳登录（`redirect` 为当前路径） */
  redirectToLogin?: (redirect?: string) => void
  /** 403 跳无权限页 */
  redirectToForbidden?: () => void
  /** 刷新处理器：返回新 access token；`null` = 失败 / 未接入（占位降级） */
  refreshHandler?: () => Promise<string | null>
}

let current: HttpAdapter = {}

/** 注入适配（可多次调用增量覆盖；各端入口调用一次） */
export function configureHttpAdapter(adapter: HttpAdapter): void {
  current = { ...current, ...adapter }
}

/** 取当前适配 */
export function getHttpAdapter(): HttpAdapter {
  return current
}

/** 重置适配（测试用） */
export function resetHttpAdapter(): void {
  current = {}
}
