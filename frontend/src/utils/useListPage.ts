/**
 * 分页列表公共逻辑：查询条件（**reactive**）、列表 / 总数、搜索 / 重置 / 翻页 / 排序 /
 * 选择 / 删除（基于 `useRequest`，在途请求经 `AbortSignal` 取消）。
 *
 * 约定：排序字段写 `query.sort` / `query.order`（`asc` / `desc`）；
 * 服务端数据不重复入 store（列表 / 详情由页面组件持有）。
 */

import { computed, reactive, ref, type ComputedRef, type Ref } from 'vue'

import type { BasePageQuery, PageResponse } from '@/api/types'

import { useRequest } from './useRequest'

/** 列表接口契约（删除能力可选） */
export interface UseListPageApi<Entity, Query extends BasePageQuery> {
  list(query: Query, options?: { signal?: AbortSignal }): Promise<PageResponse<Entity>>
  remove?: (id: string) => Promise<void>
}

export interface UseListPageOptions<Entity, Query extends BasePageQuery> {
  api: UseListPageApi<Entity, Query>
  defaultQuery: Query
  /** 挂载即查询（缺省 false） */
  immediate?: boolean
}

export interface UseListPageResult<Entity, Query extends BasePageQuery> {
  /** 查询条件（reactive；直接改字段即可） */
  query: Query
  list: ComputedRef<Entity[]>
  total: ComputedRef<number>
  data: Ref<PageResponse<Entity> | null>
  loading: Ref<boolean>
  error: Ref<unknown>
  /** 已选行（批量操作启用依据） */
  selection: Ref<Entity[]>
  /** 按当前条件查询（回第 1 页） */
  search(): Promise<PageResponse<Entity> | null>
  /** 恢复默认条件并查询（保持查询对象身份，响应式不失效） */
  reset(): Promise<PageResponse<Entity> | null>
  /** 用当前条件重发 */
  reload(): Promise<PageResponse<Entity> | null>
  /** 翻页（保留筛选条件） */
  onPageChange(page: number): Promise<PageResponse<Entity> | null>
  /** 排序变化（保留筛选条件；写 `sort` / `order`） */
  onSortChange(sort: { prop?: string; order?: 'ascending' | 'descending' | null }): Promise<PageResponse<Entity> | null>
  /** 删除后刷新（二次确认由调用方完成；未提供 `api.remove` 时拒绝） */
  remove(id: string): Promise<boolean>
  clearSelection(): void
}

export function useListPage<Entity, Query extends BasePageQuery>(
  options: UseListPageOptions<Entity, Query>,
): UseListPageResult<Entity, Query> {
  const query = reactive({ ...options.defaultQuery }) as Query
  const selection = ref<Entity[]>([]) as Ref<Entity[]>
  const request = useRequest<PageResponse<Entity>>((signal) => options.api.list(query, { signal }), {
    immediate: options.immediate === true,
  })
  const list = computed(() => request.data.value?.list ?? [])
  const total = computed(() => request.data.value?.total ?? 0)

  async function search(): Promise<PageResponse<Entity> | null> {
    ;(query as BasePageQuery).page = 1
    return request.run()
  }

  async function reset(): Promise<PageResponse<Entity> | null> {
    const target = query as Record<string, unknown>
    for (const key of Object.keys(target)) {
      delete target[key]
    }
    Object.assign(target, options.defaultQuery)
    selection.value = []
    return request.run()
  }

  async function onPageChange(page: number): Promise<PageResponse<Entity> | null> {
    ;(query as BasePageQuery).page = page
    return request.run()
  }

  async function onSortChange(sort: {
    prop?: string
    order?: 'ascending' | 'descending' | null
  }): Promise<PageResponse<Entity> | null> {
    const target = query as Record<string, unknown>
    if (sort.prop) {
      target.sort = sort.prop
    }
    if (sort.order) {
      target.order = sort.order === 'ascending' ? 'asc' : 'desc'
    } else {
      delete target.order
    }
    return request.run()
  }

  async function remove(id: string): Promise<boolean> {
    if (!options.api.remove) {
      throw new Error('useListPage.remove：未提供删除接口（api.remove）')
    }
    await options.api.remove(id)
    await request.run()
    return true
  }

  return {
    query,
    list,
    total,
    data: request.data,
    loading: request.loading,
    error: request.error,
    selection,
    search,
    reset,
    reload: request.run,
    onPageChange,
    onSortChange,
    remove,
    clearSelection: () => {
      selection.value = []
    },
  }
}
