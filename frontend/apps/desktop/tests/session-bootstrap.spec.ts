/** 首屏静默续期用例（05_02 / Kiwi 2230）：refresh + /auth/me 恢复登录态、失败静默、已持令牌短路。 */
// kiwi_id: 2230

import { createPinia, setActivePinia } from 'pinia'
import { beforeEach, describe, expect, it, vi } from 'vitest'

vi.mock('@/api/identity', () => ({
  login: vi.fn(),
  logout: vi.fn().mockResolvedValue(undefined),
  refreshAccessToken: vi.fn(),
  fetchCurrentUser: vi.fn(),
}))

import { fetchCurrentUser, refreshAccessToken } from '@/api/identity'
import type { UserSummary } from '@/api/identity'
import { setTenantCode } from '@/api/tenant'
import { getAccessToken, setAccessToken } from '@/api/token'
import { useSessionStore } from '@/stores/session'

const USER: UserSummary = {
  id: '1001',
  username: 'admin',
  name: '管理员',
  tenant: 'demo',
  locale: null,
  timezone: null,
  must_change_password: false,
}

beforeEach(() => {
  setActivePinia(createPinia())
  setTenantCode(null)
  setAccessToken(null)
  vi.clearAllMocks()
})

describe('bootstrapSession（Kiwi 2230）', () => {
  it('已持有令牌时短路（不重复刷新）', async () => {
    const store = useSessionStore()
    store.applyToken('existing')

    expect(await store.bootstrapSession()).toBe(true)
    expect(refreshAccessToken).not.toHaveBeenCalled()
  })

  it('成功：refresh 取 access 并写内存，再经 /auth/me 恢复用户概要', async () => {
    vi.mocked(refreshAccessToken).mockResolvedValue({ access_token: 'a1', token_type: 'Bearer', expires_in: 1800 })
    vi.mocked(fetchCurrentUser).mockResolvedValue(USER)
    setTenantCode('demo')

    const store = useSessionStore()
    expect(await store.bootstrapSession()).toBe(true)
    expect(store.token).toBe('a1')
    expect(store.tenant).toBe('demo')
    expect(store.user).toEqual(USER)
    expect(getAccessToken()).toBe('a1')
  })

  it('刷新失败：静默返回 false（不提示、不拉概要）', async () => {
    vi.mocked(refreshAccessToken).mockRejectedValue(new Error('20001'))

    const store = useSessionStore()
    expect(await store.bootstrapSession()).toBe(false)
    expect(store.token).toBeNull()
    expect(getAccessToken()).toBeNull()
    expect(fetchCurrentUser).not.toHaveBeenCalled()
  })

  it('概要恢复失败：保留内存令牌、概要留空', async () => {
    vi.mocked(refreshAccessToken).mockResolvedValue({ access_token: 'a1', token_type: 'Bearer', expires_in: 1800 })
    vi.mocked(fetchCurrentUser).mockRejectedValue(new Error('500'))

    const store = useSessionStore()
    expect(await store.bootstrapSession()).toBe(true)
    expect(store.token).toBe('a1')
    expect(store.user).toBeNull()
  })
})
