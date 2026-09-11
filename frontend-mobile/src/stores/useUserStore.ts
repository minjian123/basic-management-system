/** 用户状态占位：token 仅存内存（持久化与刷新口径阶段二定案）。 */

import { defineStore } from 'pinia'

export const useUserStore = defineStore('user', {
  state: () => ({
    token: '',
  }),
  actions: {
    setToken(token: string): void {
      this.token = token
    },
    clear(): void {
      this.token = ''
    },
  },
})
