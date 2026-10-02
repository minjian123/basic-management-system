/**
 * 会话 store：访问令牌、用户概要、租户编码与权限码汇聚。
 *
 * - **access 仅内存**（`token` + `api/token` 内存模块）；刷新页面后由 `bootstrapSession()` 经
 *   `/auth/refresh` + `/auth/me` 静默续期恢复；
 * - **租户编码**为非敏感持久化项（`api/tenant`），供 refresh / logout 注入 `X-Tenant-ID`；
 * - 用户概要**不落持久化**（避免 PII 与陈旧），登录或首屏续期时写入。
 */

import { defineStore } from 'pinia'

import type { UserSummary } from '@/api/identity'
import { fetchCurrentUser, logout, refreshAccessToken } from '@/api/identity'
import { getTenantCode, setTenantCode } from '@/api/tenant'
import { setAccessToken } from '@/api/token'
import { setPermissionCodes } from '@/utils/perm'

/** 会话状态。 */
interface SessionState {
  /** 访问令牌（内存）。 */
  token: string | null
  /** 当前用户概要（登录 / 首屏续期恢复；未恢复为 `null`）。 */
  user: UserSummary | null
  /** 租户编码（非敏感，持久化）。 */
  tenant: string | null
  /** 权限码。 */
  codes: string[]
}

/** 登录载荷。 */
export interface SessionSignIn {
  /** 访问令牌。 */
  token: string
  /** 用户概要。 */
  user: UserSummary
  /** 租户编码（可空；子域名部署时由后端解析）。 */
  tenant: string | null
  /** 权限码（RBAC 就绪前为空集）。 */
  codes?: readonly string[]
}

/** 会话 store。 */
export const useSessionStore = defineStore('session', {
  state: (): SessionState => ({ token: null, user: null, tenant: null, codes: [] }),
  actions: {
    /**
     * 登录：写入令牌、用户概要、租户编码与权限码。
     *
     * @param payload 登录载荷。
     */
    signIn(payload: SessionSignIn): void {
      const codes = payload.codes ?? []
      this.token = payload.token
      this.user = payload.user
      this.tenant = payload.tenant
      this.codes = [...codes]
      setAccessToken(payload.token)
      setTenantCode(payload.tenant)
      setPermissionCodes(codes)
    },
    /**
     * 仅更新访问令牌（401 静默刷新后由宿主刷新处理器调用链写入）。
     *
     * @param token 新访问令牌。
     */
    applyToken(token: string): void {
      this.token = token
      setAccessToken(token)
    },
    /**
     * 首屏静默续期：`/auth/refresh` 取新 access，再经 `/auth/me` 恢复用户概要。
     *
     * **失败静默**（不提示、不跳转）——由路由守卫（`05_03`）按「未登录」处理，避免未登录用户
     * 首次访问被误提示「会话已失效」；已持有令牌时短路。
     *
     * @returns 是否恢复出可用登录态。
     */
    async bootstrapSession(): Promise<boolean> {
      if (this.token !== null) {
        return true
      }
      this.tenant = getTenantCode()
      let access: string
      try {
        access = (await refreshAccessToken()).access_token
      } catch {
        return false
      }
      this.token = access
      setAccessToken(access)
      try {
        this.user = await fetchCurrentUser()
      } catch {
        // 概要恢复失败：保留内存令牌（登录态不完整，权限码归阶段七）。
        this.user = null
      }
      return true
    },
    /**
     * 登出：`/auth/logout` **尽力而为**（失败仅上报，不阻断本地清理），随后清空内存态。
     */
    async signOut(): Promise<void> {
      try {
        await logout()
      } catch {
        // 服务端登出失败不阻断本地清理（refresh cookie 会因会话撤销 / 过期自然失效）。
      } finally {
        this.clearSession()
      }
    },
    /** 清空本地会话（不调服务端；401 会话失效路径使用，避免与刷新链互递归）。 */
    clearSession(): void {
      this.token = null
      this.user = null
      this.tenant = null
      this.codes = []
      setAccessToken(null)
      setTenantCode(null)
      setPermissionCodes([])
    },
  },
})
