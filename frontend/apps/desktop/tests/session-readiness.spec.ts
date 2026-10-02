/** 会话就绪单例用例（05_03 / Kiwi 2231）：并发共享一次续期 / 失败静默且置就绪 / 短路 / 失效不误放行。 */
// kiwi_id: 2231

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
import { setAccessToken } from '@/api/token'
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

const REFRESHED = { access_token: 'a1', token_type: 'Bearer', expires_in: 1800 }

beforeEach(() => {
  setActivePinia(createPinia())
  setTenantCode(null)
  setAccessToken(null)
  vi.clearAllMocks()
})

describe('ensureReady（Kiwi 2231）', () => {
  it('已持令牌短路：不发起续期，直接标记就绪', async () => {
    const store = useSessionStore()
    store.applyToken('existing')
    expect(store.ready).toBe(false)

    expect(await store.ensureReady()).toBe(true)
    expect(refreshAccessToken).not.toHaveBeenCalled()
    expect(store.ready).toBe(true)
  })

  it('并发调用共享同一次续期（单例）', async () => {
    vi.mocked(refreshAccessToken).mockResolvedValue(REFRESHED)
    vi.mocked(fetchCurrentUser).mockResolvedValue(USER)
    const store = useSessionStore()

    const [first, second] = await Promise.all([store.ensureReady(), store.ensureReady()])

    expect(first).toBe(true)
    expect(second).toBe(true)
    expect(refreshAccessToken).toHaveBeenCalledTimes(1)
    expect(store.user).toEqual(USER)
    expect(store.ready).toBe(true)
  })

  it('续期失败：静默返回 false 且标记就绪（由守卫按未登录处理）', async () => {
    vi.mocked(refreshAccessToken).mockRejectedValue(new Error('20001'))
    const store = useSessionStore()

    expect(await store.ensureReady()).toBe(false)
    expect(store.ready).toBe(true)
    expect(store.token).toBeNull()
  })

  it('续期失败后再次调用命中单例，不重复发起续期', async () => {
    vi.mocked(refreshAccessToken).mockRejectedValue(new Error('20001'))
    const store = useSessionStore()

    await store.ensureReady()
    expect(await store.ensureReady()).toBe(false)
    expect(refreshAccessToken).toHaveBeenCalledTimes(1)
  })

  it('续期成功后会话被清空 → ensureReady 返回 false（不误判为已登录）', async () => {
    vi.mocked(refreshAccessToken).mockResolvedValue(REFRESHED)
    vi.mocked(fetchCurrentUser).mockResolvedValue(USER)
    const store = useSessionStore()

    expect(await store.ensureReady()).toBe(true)
    store.clearSession()

    expect(await store.ensureReady()).toBe(false)
    expect(refreshAccessToken).toHaveBeenCalledTimes(1)
  })

  it('登录（signIn）后标记就绪，不再等待', async () => {
    const store = useSessionStore()
    store.signIn({ token: 't1', user: USER, tenant: 'demo' })

    expect(store.ready).toBe(true)
    expect(await store.ensureReady()).toBe(true)
    expect(refreshAccessToken).not.toHaveBeenCalled()
  })
})
