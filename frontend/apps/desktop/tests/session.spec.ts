/** 会话 store 用例（05_02 / Kiwi 2230）：令牌 / 用户概要 / 租户编码汇聚与登出清理。 */
// kiwi_id: 2230

import { createPinia, setActivePinia } from 'pinia'
import { beforeEach, describe, expect, it } from 'vitest'

import type { UserSummary } from '@/api/identity'
import { getTenantCode, setTenantCode } from '@/api/tenant'
import { getAccessToken } from '@/api/token'
import { useSessionStore } from '@/stores/session'
import { getPermissionCodes, hasPerm } from '@/utils/perm'

const USER: UserSummary = {
  id: '1001',
  username: 'admin',
  name: '管理员',
  tenant: 'demo',
  locale: 'zh-cn',
  timezone: null,
  must_change_password: false,
}

beforeEach(() => {
  setActivePinia(createPinia())
  setTenantCode(null)
})

describe('useSessionStore（Kiwi 2230）', () => {
  it('登录写入令牌 / 用户概要 / 租户编码 / 权限码；登出清空', async () => {
    const store = useSessionStore()
    store.signIn({ token: 'token-1', user: USER, tenant: 'demo', codes: ['user:read'] })
    expect(store.token).toBe('token-1')
    expect(store.user).toEqual(USER)
    expect(store.tenant).toBe('demo')
    expect(store.codes).toEqual(['user:read'])
    expect(getAccessToken()).toBe('token-1')
    expect(getTenantCode()).toBe('demo')
    expect(hasPerm('user:read')).toBe(true)
    expect(getPermissionCodes()).toEqual(['user:read'])

    // 未注入请求适配器 → 服务端登出失败，但本地仍清空（尽力而为、本地必清）。
    await store.signOut()
    expect(store.token).toBeNull()
    expect(store.user).toBeNull()
    expect(store.tenant).toBeNull()
    expect(store.codes).toEqual([])
    expect(getAccessToken()).toBeNull()
    expect(getTenantCode()).toBeNull()
    expect(getPermissionCodes()).toEqual([])
    expect(hasPerm('user:read')).toBe(false)
  })

  it('applyToken 仅更新访问令牌；clearSession 清内存态', () => {
    const store = useSessionStore()
    store.signIn({ token: 'token-1', user: USER, tenant: 'demo' })

    store.applyToken('token-2')
    expect(store.token).toBe('token-2')
    expect(getAccessToken()).toBe('token-2')
    expect(store.user).toEqual(USER)

    store.clearSession()
    expect(store.token).toBeNull()
    expect(store.user).toBeNull()
    expect(getTenantCode()).toBeNull()
  })
})
