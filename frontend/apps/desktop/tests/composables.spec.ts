/** 组合式用例：useRequest / useListPage。 */

import { configureRequestAdapter, type RequestConfig } from '@bms/core'
import { describe, expect, it } from 'vitest'

import { useListPage } from '@/utils/useListPage'
import { useRequest } from '@/utils/useRequest'

describe('useRequest', () => {
  it('成功：data / loading 复位', async () => {
    configureRequestAdapter({ request: async <T,>(): Promise<T> => ({ id: 1 }) as T })
    const state = useRequest<{ id: number }>(() => ({ method: 'GET', url: '/a' }))
    expect(state.loading.value).toBe(false)
    const result = await state.run()
    expect(result).toEqual({ id: 1 })
    expect(state.data.value).toEqual({ id: 1 })
    expect(state.loading.value).toBe(false)
  })

  it('失败：error 记录并返回 undefined', async () => {
    configureRequestAdapter({
      request: async (): Promise<never> => {
        throw new Error('boom')
      },
    })
    const state = useRequest({ method: 'GET', url: '/a' })
    const result = await state.run({ url: '/b' })
    expect(result).toBeUndefined()
    expect(state.error.value).toBeInstanceOf(Error)
  })
})

describe('useListPage', () => {
  it('加载 / 翻页 / 筛选取参', async () => {
    const calls: RequestConfig[] = []
    configureRequestAdapter({
      request: async <T,>(config: RequestConfig): Promise<T> => {
        calls.push(config)
        return { list: [config.params?.page], total: 2, page: 1, size: 20 } as T
      },
    })
    const page = useListPage<number>({ url: '/api/v1/list', query: () => ({ keyword: 'k' }) })
    await page.load()
    expect(page.list.value).toEqual([1])
    expect(page.total.value).toBe(2)
    expect(calls[0]?.params).toMatchObject({ page: 1, keyword: 'k' })

    await page.changePage(2)
    expect(page.page.value).toBe(2)
    await page.search()
    expect(page.page.value).toBe(1)
    await page.reset()
    expect(page.page.value).toBe(1)
  })

  it('失败记录 error', async () => {
    configureRequestAdapter({
      request: async (): Promise<never> => {
        throw new Error('boom')
      },
    })
    const page = useListPage({ url: '/api/v1/list' })
    await page.load()
    expect(page.error.value).toBeInstanceOf(Error)
  })
})
