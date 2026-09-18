/** 会话 store 用例：令牌与权限码汇聚。 */

import { createPinia, setActivePinia } from 'pinia'
import { beforeEach, describe, expect, it } from 'vitest'

import { getAccessToken } from '@/api/token'
import { useSessionStore } from '@/stores/session'
import { getPermissionCodes, hasPerm } from '@/utils/perm'

beforeEach(() => setActivePinia(createPinia()))

describe('useSessionStore', () => {
  it('登录写入令牌与权限码；登出清空', () => {
    const store = useSessionStore()
    store.signIn('token-1', ['user:read'])
    expect(store.token).toBe('token-1')
    expect(store.codes).toEqual(['user:read'])
    expect(getAccessToken()).toBe('token-1')
    expect(hasPerm('user:read')).toBe(true)
    expect(getPermissionCodes()).toEqual(['user:read'])

    store.signOut()
    expect(store.token).toBeNull()
    expect(store.codes).toEqual([])
    expect(getAccessToken()).toBeNull()
    expect(hasPerm('user:read')).toBe(false)
  })
})
