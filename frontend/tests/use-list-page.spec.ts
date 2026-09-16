/** 组合式用例（Kiwi 718）：useRequest 竞态取消 / useListPage 分页排序选择（双端同款）。 */

import { describe, expect, it, vi } from 'vitest'

import type { BasePageQuery, PageResponse } from '@/api/types'
import { useListPage } from '@/utils/useListPage'
import { useRequest } from '@/utils/useRequest'

interface Row {
  id: string
}

type Query = BasePageQuery & { keyword?: string; sort?: string; order?: string }

function pageData(rows: Row[], page = 1, size = 20, total = rows.length): PageResponse<Row> {
  return { list: rows, total, page, size }
}

describe('组合式（Kiwi 718）', () => {
  it('① useRequest：immediate / refresh / cancel', async () => {
    const fetcher = vi.fn().mockResolvedValue('ok')
    const request = useRequest(fetcher, { immediate: true })
    await Promise.resolve()
    expect(fetcher).toHaveBeenCalledTimes(1)
    await request.refresh()
    expect(fetcher).toHaveBeenCalledTimes(2)
    expect(request.data.value).toBe('ok')
    request.cancel()
    expect(request.loading.value).toBe(false)
  })

  it('② useRequest：cancel 中止在途并复位状态（不写 error）', async () => {
    let abortSignal: AbortSignal | undefined
    const request = useRequest((signal) => {
      abortSignal = signal
      return new Promise<string>((_resolve, reject) => {
        signal.addEventListener('abort', () => reject(Object.assign(new Error('cancelled'), { name: 'AbortError' })))
      })
    })
    const pending = request.run()
    expect(request.loading.value).toBe(true)
    request.cancel()
    expect(abortSignal?.aborted).toBe(true)
    await pending
    expect(request.loading.value).toBe(false)
    expect(request.error.value).toBeNull()
  })

  it('③ useListPage：reactive 查询 / 搜索回第 1 页 / 重置保持对象身份', async () => {
    const list = vi.fn(async (query: Query) => pageData([], query.page, query.size))
    const page = useListPage<Row, Query>({ api: { list }, defaultQuery: { page: 1, size: 20 } })
    page.query.keyword = 'k'
    await page.search()
    expect(list).toHaveBeenLastCalledWith({ page: 1, size: 20, keyword: 'k' }, expect.anything())
    page.query.page = 5
    await page.reload()
    expect(list).toHaveBeenLastCalledWith({ page: 5, size: 20, keyword: 'k' }, expect.anything())
    const identity = page.query
    await page.reset()
    expect(page.query).toBe(identity)
    expect(page.query).toEqual({ page: 1, size: 20 })
  })

  it('④ useListPage：翻页 / 排序保留筛选', async () => {
    const list = vi.fn(async (query: Query) => pageData([], query.page, query.size))
    const page = useListPage<Row, Query>({ api: { list }, defaultQuery: { page: 1, size: 20 } })
    page.query.keyword = 'k'
    await page.onPageChange(3)
    expect(list).toHaveBeenLastCalledWith({ page: 3, size: 20, keyword: 'k' }, expect.anything())
    await page.onSortChange({ prop: 'createdAt', order: 'descending' })
    expect(list).toHaveBeenLastCalledWith(
      { page: 3, size: 20, keyword: 'k', sort: 'createdAt', order: 'desc' },
      expect.anything(),
    )
    await page.onSortChange({ prop: 'createdAt', order: null })
    expect(page.query.order).toBeUndefined()
  })

  it('⑤ useListPage：selection / clearSelection / remove', async () => {
    const list = vi.fn(async () => pageData([{ id: '1' }]))
    const removeApi = vi.fn().mockResolvedValue(undefined)
    const page = useListPage<Row, Query>({ api: { list, remove: removeApi }, defaultQuery: { page: 1, size: 20 } })
    page.selection.value = [{ id: '1' }]
    page.clearSelection()
    expect(page.selection.value).toEqual([])
    await page.search()
    expect(await page.remove('1')).toBe(true)
    expect(removeApi).toHaveBeenCalledWith('1')
    expect(list).toHaveBeenCalledTimes(2)

    const noRemove = useListPage<Row, Query>({ api: { list }, defaultQuery: { page: 1, size: 20 } })
    await expect(noRemove.remove('1')).rejects.toThrow('未提供删除接口')
  })

  it('⑥ useListPage：新旧请求竞态（旧请求中止不写回）', async () => {
    let resolveSecond: ((value: PageResponse<Row>) => void) | undefined
    const list = vi.fn((query: Query, options?: { signal?: AbortSignal }) => {
      if (query.page === 1) {
        return new Promise<PageResponse<Row>>((_resolve, reject) => {
          options?.signal?.addEventListener('abort', () =>
            reject(Object.assign(new Error('cancelled'), { name: 'AbortError' })),
          )
        })
      }
      return new Promise<PageResponse<Row>>((resolve) => {
        resolveSecond = resolve
      })
    })
    const page = useListPage<Row, Query>({ api: { list }, defaultQuery: { page: 1, size: 20 } })
    const first = page.search()
    const second = page.onPageChange(2)
    resolveSecond?.(pageData([{ id: '2' }], 2))
    await Promise.all([first, second])
    expect(page.list.value).toEqual([{ id: '2' }])
    expect(page.total.value).toBe(1)
    expect(page.error.value).toBeNull()
  })
})
