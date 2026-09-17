/**
 * access token 内存管理：单一内存源 + 单飞刷新（并发 401 收敛为一次）+ 清会话。
 *
 * 口径（《组件设计 · 请求封装》§5）：access token 仅存内存、refresh 走 HttpOnly Cookie；
 * 后端 `/auth` 未接入时 `refreshHandler` 未注入 → `refresh()` 返回 `null`（占位降级）。
 */

import { getHttpAdapter } from './adapter'

let accessToken: string | null = null
let refreshing: Promise<string | null> | null = null

export const tokenManager = {
  /** 取 access token（未登录为 `null`） */
  getAccessToken(): string | null {
    return accessToken
  },

  /** 设置 / 清空 access token（空串归一为 `null`） */
  setAccessToken(token: string | null): void {
    accessToken = token && token.trim().length > 0 ? token : null
  },

  /** 是否持有 token */
  hasToken(): boolean {
    return Boolean(accessToken)
  },

  /**
   * 刷新 access token（并发收敛：同一时刻仅一次刷新）。
   *
   * 返回新 token；失败或未注入刷新处理器返回 `null`（由拦截器按会话失效兜底）。
   */
  refresh(): Promise<string | null> {
    if (refreshing) {
      return refreshing
    }
    const handler = getHttpAdapter().refreshHandler
    if (!handler) {
      return Promise.resolve(null)
    }
    refreshing = (async (): Promise<string | null> => {
      try {
        const token = await handler()
        if (token && token.trim().length > 0) {
          accessToken = token
          return token
        }
        return null
      } catch {
        return null
      } finally {
        refreshing = null
      }
    })()
    return refreshing
  },

  /** 清会话（登出 / 刷新失败） */
  clear(): void {
    accessToken = null
  },
}
