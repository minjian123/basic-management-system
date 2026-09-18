/** 会话 store：令牌与权限码汇聚（判定唯一来源经宿主工具 → 核心纯函数）。 */

import { defineStore } from 'pinia'

import { setAccessToken } from '@/api/token'
import { setPermissionCodes } from '@/utils/perm'

/** 会话状态。 */
interface SessionState {
  /** 访问令牌（内存）。 */
  token: string | null
  /** 权限码。 */
  codes: string[]
}

/** 会话 store。 */
export const useSessionStore = defineStore('session', {
  state: (): SessionState => ({ token: null, codes: [] }),
  actions: {
    /**
     * 登录：写入令牌与权限码。
     *
     * @param token 访问令牌。
     * @param codes 权限码。
     */
    signIn(token: string, codes: readonly string[]): void {
      this.token = token
      this.codes = [...codes]
      setAccessToken(token)
      setPermissionCodes(codes)
    },
    /** 登出：清空令牌与权限码。 */
    signOut(): void {
      this.token = null
      this.codes = []
      setAccessToken(null)
      setPermissionCodes([])
    },
  },
})
