/** 基础类用例（Kiwi 21）：契约类型 / BaseApi / createCrudStore / stableStringify。 */

import { createPinia, setActivePinia } from 'pinia'
import { beforeEach, describe, expect, it, vi } from 'vitest'

import { BaseApi } from '@/api/base'
import type { BaseEntity, BasePageQuery, PageResponse } from '@/api/types'
import { createCrudStore, type CrudApi } from '@/stores/base'
import { stableStringify } from '@/utils/serialize'

vi.mock('@/api/http', () => ({ request: vi.fn() }))

import { request } from '@/api/http'

interface Demo extends BaseEntity {
  name: string
}

interface DemoQuery extends BasePageQuery {
  keyword?: string
}

class DemoApi extends BaseApi {
  constructor() {
    super('/api/v1/demos')
  }

  listDemos(query: DemoQuery): Promise<PageResponse<Demo>> {
    return this.get('', { params: query })
  }

  createDemo(data: Record<string, unknown>): Promise<Demo> {
    return this.post('', data)
  }

  updateDemo(id: string, data: Record<string, unknown>): Promise<Demo> {
    return this.put(`/${id}`, data)
  }

  removeDemo(id: string): Promise<void> {
    return this.delete(`/${id}`)
  }
}

describe('基础类（Kiwi 21）', () => {
  beforeEach(() => {
    vi.mocked(request).mockReset()
  })

  it('BaseApi 拼接路径并透传方法与参数', async () => {
    vi.mocked(request).mockResolvedValue({ list: [], total: 0, page: 1, size: 20 })
    const api = new DemoApi()
    await api.listDemos({ page: 1, size: 20, keyword: 'k' })
    expect(request).toHaveBeenCalledWith({
      url: '/api/v1/demos',
      method: 'GET',
      params: { page: 1, size: 20, keyword: 'k' },
    })

    const demo: Demo = { id: '1', name: 'a', createdAt: '', updatedAt: '' }
    vi.mocked(request).mockResolvedValue(demo)
    await api.createDemo({ name: 'a' })
    expect(request).toHaveBeenCalledWith({ url: '/api/v1/demos', method: 'POST', data: { name: 'a' } })

    await api.updateDemo('1', { name: 'b' })
    expect(request).toHaveBeenCalledWith({ url: '/api/v1/demos/1', method: 'PUT', data: { name: 'b' } })

    await api.removeDemo('1')
    expect(request).toHaveBeenCalledWith({ url: '/api/v1/demos/1', method: 'DELETE' })
  })

  it('createCrudStore 提供通用 CRUD 字段与动作', async () => {
    const item: Demo = { id: '1', name: 'a', createdAt: '', updatedAt: '' }
    const api: CrudApi<Demo, DemoQuery> = {
      list: vi.fn().mockResolvedValue({ list: [item], total: 1, page: 1, size: 20 }),
      get: vi.fn().mockResolvedValue(item),
      create: vi.fn().mockResolvedValue(item),
      update: vi.fn().mockResolvedValue({ ...item, name: 'b' }),
      remove: vi.fn().mockResolvedValue(undefined),
    }
    setActivePinia(createPinia())
    const useStore = createCrudStore<Demo, DemoQuery>('demo', api)
    const store = useStore()

    await store.fetchList({ page: 1, size: 20 })
    expect(store.list).toHaveLength(1)
    expect(store.total).toBe(1)
    expect(store.loading).toBe(false)

    await store.remove('1')
    expect(store.list).toHaveLength(0)
    expect(store.total).toBe(0)

    expect(await store.fetchOne('1')).toEqual(item)
    expect(await store.create({ name: 'c' })).toEqual(item)
    expect(await store.update('1', { name: 'd' })).toEqual({ ...item, name: 'b' })
  })

  it('stableStringify 输出稳定序', () => {
    expect(stableStringify({ b: 1, a: { d: 2, c: [3, { f: 4, e: 5 }] } })).toBe(
      '{"a":{"c":[3,{"e":5,"f":4}],"d":2},"b":1}',
    )
    expect(stableStringify(new Set([3, 1, 2]))).toBe('[1,2,3]')
    const sameTime = new Set([new Date(0), new Date(0)])
    expect(stableStringify(sameTime)).toBe('["1970-01-01T00:00:00.000Z","1970-01-01T00:00:00.000Z"]')
    expect(stableStringify(new Map([['b', 2], ['a', 1]]))).toBe('{"a":1,"b":2}')
    expect(stableStringify({ id: 1800000000000000123n })).toBe('{"id":"1800000000000000123"}')
    expect(stableStringify({ at: new Date('2026-09-10T00:00:00.000Z') })).toBe(
      '{"at":"2026-09-10T00:00:00.000Z"}',
    )
  })
})
