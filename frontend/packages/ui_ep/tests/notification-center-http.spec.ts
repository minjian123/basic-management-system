// kiwi_id: 2524
/** 通知 HTTP 适配器（09_01）：列表参数 / 未读数 / 详情 / 已读 / 删除的路径与解包。 */

import { afterEach, describe, expect, it, vi } from 'vitest'

import { createHttpNotificationJobs } from '../src'

/** 统一响应包装。 */
function wrap(data: unknown): unknown {
  return { code: 0, message: '', data }
}

afterEach(() => {
  vi.unstubAllGlobals()
})

describe('createHttpNotificationJobs（09_01）', () => {
  it('列表参数映射（type / is_read / 分页）并解包', async () => {
    const fetchMock = vi.fn(async () => ({
      ok: true,
      json: async () => wrap({ list: [{ id: '1', title: 't', type: 'approval', is_read: false }], total: 1 }),
    }))
    vi.stubGlobal('fetch', fetchMock)
    const jobs = createHttpNotificationJobs({ endpoint: '/api/v1', headers: { Authorization: 'Bearer t' } })

    const raw = await jobs.load?.({ type: 'todo', read: 'unread', page: 2, pageSize: 10 })
    const [url, init] = fetchMock.mock.calls[0] as unknown as [string, RequestInit]
    expect(url).toContain('/api/v1/notifications?')
    expect(url).toContain('page=2')
    expect(url).toContain('size=10')
    expect(url).toContain('type=approval')
    expect(url).toContain('is_read=false')
    expect((init.headers as Record<string, string>).Authorization).toBe('Bearer t')
    expect(raw).toMatchObject({ total: 1 })
  })

  it('未读数 / 详情 / 批量已读 / 全部已读 / 删除', async () => {
    const calls: string[] = []
    const fetchMock = vi.fn(async (url: string, init?: RequestInit) => {
      calls.push(`${init?.method ?? 'GET'} ${url}`)
      if (url.includes('unread-count')) {
        return { ok: true, json: async () => wrap({ count: 7 }) }
      }
      if (url.includes('/read-all')) {
        return { ok: true, json: async () => wrap({ count: 0 }) }
      }
      if (url.includes('/read')) {
        return { ok: true, json: async () => wrap({ count: 3 }) }
      }
      if ((init?.method ?? 'GET') === 'DELETE') {
        return { ok: true, json: async () => wrap(true) }
      }
      return { ok: true, json: async () => wrap({ id: '9', title: '详情' }) }
    })
    vi.stubGlobal('fetch', fetchMock)
    const jobs = createHttpNotificationJobs({ endpoint: '/api/v1' })

    expect(await jobs.loadUnread?.()).toBe(7)
    expect(await jobs.detail?.('9')).toMatchObject({ id: '9' })
    expect(await jobs.markRead?.(['1', '2'])).toEqual({ unreadCount: 3 })
    expect(await jobs.markAllRead?.()).toEqual({ unreadCount: 0 })
    expect(await jobs.remove?.('9')).toBe(true)

    expect(calls.some((line) => line.includes('GET') && line.includes('/notifications/9?mark_read=true'))).toBe(true)
    expect(calls.some((line) => line.startsWith('DELETE ') && line.includes('/notifications/9'))).toBe(true)
  })

  it('无 fetch 能力时调用即失败（编排回错误态）', async () => {
    vi.stubGlobal('fetch', undefined)
    const jobs = createHttpNotificationJobs()
    await expect(jobs.loadUnread?.()).rejects.toThrow('通知服务不可用')
  })
})
