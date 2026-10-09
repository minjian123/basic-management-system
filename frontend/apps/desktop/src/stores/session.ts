/**
 * 会话 store：访问令牌、用户概要、租户编码与权限码汇聚。
 *
 * - **access 仅内存**（`token` + `api/token` 内存模块）；刷新页面后由 `bootstrapSession()` 经
 *   `/auth/refresh` + `/auth/me` 静默续期恢复；
 * - **租户编码**为非敏感持久化项（`api/tenant`），供 refresh / logout 注入 `X-Tenant-ID`；
 * - 用户概要**不落持久化**（避免 PII 与陈旧），登录或首屏续期时写入；
 * - **会话就绪**：`ready` 标记「就绪判定是否完成」，`ensureReady()` 为**单例**（并发共享一次续期），
 *   供路由守卫等待（导航挂起，不闪登录页）与应用根骨架屏消费（域五 `05_03`）。
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
  /** 会话就绪判定是否已完成（守卫等待态与首屏骨架屏依据）。 */
  ready: boolean
}

/** 会话就绪单例（按 store 实例缓存，避免并发触发多次续期；弱引用不阻回收）。 */
const readiness = new WeakMap<object, Promise<boolean>>()

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
  state: (): SessionState => ({ token: null, user: null, tenant: null, codes: [], ready: false }),
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
      this.ready = true
      setAccessToken(payload.token)
      setTenantCode(payload.tenant)
      this.setCodes(codes)
    },
    /**
     * 写入权限码（**单一来源**：登录载荷 / 动态菜单装载结果）。
     *
     * 交互登录时登录载荷不含权限码，真实权限码由动态菜单接口（`/menus/my`）下发；菜单装载落地后
     * 经本动作回填 `codes`（`stores/menu.ts`），使「按权限显隐」的宿主页与指令口径一致。
     *
     * @param codes 权限码集合。
     */
    setCodes(codes: readonly string[]): void {
      this.codes = [...codes]
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
     * 会话就绪（**单例**）：已持有令牌直接就绪；否则执行一次首屏静默续期，并发调用共享同一次。
     *
     * 续期失败**静默**（不提示、不跳转）并置 `ready`——由路由守卫按「未登录」处理（跳登录带 `redirect`）。
     *
     * @returns 是否具备可用登录态。
     */
    async ensureReady(): Promise<boolean> {
      if (this.token !== null) {
        this.ready = true
        return true
      }
      let pending = readiness.get(this)
      if (pending === undefined) {
        pending = this.bootstrapSession().finally(() => {
          this.ready = true
        })
        readiness.set(this, pending)
      }
      await pending
      // 续期可能已被并发路径清空（会话失效），以**当次结果**为准。
      return this.token !== null
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
      setAccessToken(null)
      setTenantCode(null)
      this.setCodes([])
    },
  },
})
