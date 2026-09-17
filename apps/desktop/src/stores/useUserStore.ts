/** 用户状态：展示态与 access token 同步（token 唯一内存源在 `tokenManager`）。 */

import { defineStore } from 'pinia'

import { tokenManager } from '@/api/token'

export const useUserStore = defineStore('user', {
  state: () => ({
    token: tokenManager.getAccessToken() ?? '',
  }),
  actions: {
    setToken(token: string): void {
      this.token = token
      tokenManager.setAccessToken(token)
    },
    clear(): void {
      this.token = ''
      tokenManager.clear()
    },
  },
})
