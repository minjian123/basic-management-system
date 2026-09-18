/** 分页列表组合式：分页 / 筛选 / 刷新 / 重置（经核心 `request`）。 */

import { request, type PageResponse } from '@bms/core'
import { ref, type Ref } from 'vue'

/** 选项。 */
export interface UseListPageOptions {
  /** 列表地址（含前缀）。 */
  url: string
  /** 页长（缺省 20）。 */
  size?: number
  /** 筛选参数提供者。 */
  query?: () => Record<string, unknown>
}

/** `useListPage` 返回面。 */
export interface UseListPageResult<T> {
  /** 列表数据。 */
  list: Ref<T[]>
  /** 总条数。 */
  total: Ref<number>
  /** 页码。 */
  page: Ref<number>
  /** 页长。 */
  size: Ref<number>
  /** 加载中。 */
  loading: Ref<boolean>
  /** 错误。 */
  error: Ref<unknown>
  /** 加载当前页。 */
  load: () => Promise<void>
  /** 回到第 1 页并加载（筛选变化）。 */
  search: () => Promise<void>
  /** 重置页码并加载。 */
  reset: () => Promise<void>
  /** 翻页。 */
  changePage: (page: number) => Promise<void>
  /** 刷新当前页。 */
  refresh: () => Promise<void>
}

/**
 * 分页列表组合式。
 *
 * @param options 选项。
 */
export function useListPage<T>(options: UseListPageOptions): UseListPageResult<T> {
  const list = ref([]) as Ref<T[]>
  const total = ref(0)
  const page = ref(1)
  const size = ref(options.size ?? 20)
  const loading = ref(false)
  const error = ref<unknown>()

  async function load(): Promise<void> {
    loading.value = true
    error.value = undefined
    try {
      const params: Record<string, unknown> = { page: page.value, size: size.value, ...options.query?.() }
      const response = await request<PageResponse<T>>({ method: 'GET', url: options.url, params })
      list.value = response.list
      total.value = response.total
    } catch (caught) {
      error.value = caught
    } finally {
      loading.value = false
    }
  }

  async function search(): Promise<void> {
    page.value = 1
    await load()
  }

  async function reset(): Promise<void> {
    page.value = 1
    await load()
  }

  async function changePage(next: number): Promise<void> {
    page.value = next
    await load()
  }

  return { list, total, page, size, loading, error, load, search, reset, changePage, refresh: load }
}
