/** 分页列表公共逻辑：查询条件、列表/总数、搜索/重置/翻页/重载（基于 useRequest）。 */

import { computed, ref, type ComputedRef, type Ref } from 'vue'

import type { BasePageQuery, PageResponse } from '@/api/types'
import { useRequest, type UseRequestResult } from '@/utils/useRequest'

export interface UseListPageOptions<Entity, Query extends BasePageQuery> {
  api: { list(query: Query): Promise<PageResponse<Entity>> }
  defaultQuery: Query
}

export interface UseListPageResult<Entity, Query extends BasePageQuery> extends UseRequestResult<PageResponse<Entity>> {
  query: Ref<Query>
  list: ComputedRef<Entity[]>
  total: ComputedRef<number>
  search: () => Promise<PageResponse<Entity> | null>
  reset: () => Promise<PageResponse<Entity> | null>
  changePage: (page: number) => Promise<PageResponse<Entity> | null>
  reload: () => Promise<PageResponse<Entity> | null>
}

export function useListPage<Entity, Query extends BasePageQuery>(
  options: UseListPageOptions<Entity, Query>,
): UseListPageResult<Entity, Query> {
  const query = ref({ ...options.defaultQuery }) as Ref<Query>
  const request = useRequest<PageResponse<Entity>>(() => options.api.list(query.value))
  const list = computed(() => request.data.value?.list ?? [])
  const total = computed(() => request.data.value?.total ?? 0)

  async function search(): Promise<PageResponse<Entity> | null> {
    query.value.page = 1
    return request.run()
  }

  async function reset(): Promise<PageResponse<Entity> | null> {
    query.value = { ...options.defaultQuery } as Query
    return request.run()
  }

  async function changePage(page: number): Promise<PageResponse<Entity> | null> {
    query.value.page = page
    return request.run()
  }

  return { ...request, query, list, total, search, reset, changePage, reload: request.run }
}
