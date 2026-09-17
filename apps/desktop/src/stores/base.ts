/** Pinia 通用 CRUD store 工厂（Pinia 惯例为组合式函数，以工厂实现「BaseStore」能力）。 */

import { defineStore } from 'pinia'
import { ref, type Ref } from 'vue'

import type { BaseEntity, BasePageQuery, PageResponse } from '@/api/types'
import { useFrontendBase } from '@/base/useFrontendBase'

/** 模块 API 接入约定：实现五个方法即可接入 createCrudStore。 */
export interface CrudApi<Entity extends BaseEntity, Query extends BasePageQuery> {
  list(query: Query): Promise<PageResponse<Entity>>
  get(id: string): Promise<Entity>
  create(data: Record<string, unknown>): Promise<Entity>
  update(id: string, data: Record<string, unknown>): Promise<Entity>
  remove(id: string): Promise<void>
}

export function createCrudStore<Entity extends BaseEntity, Query extends BasePageQuery>(
  storeId: string,
  api: CrudApi<Entity, Query>,
) {
  return defineStore(storeId, () => {
    /** store 级根系组合：日志与错误上报出口（契约/数据根接根系；随 store 作用域释放）。 */
    const base = useFrontendBase({ ns: 'store', identifier: storeId })

    const list = ref<Entity[]>([]) as Ref<Entity[]>
    const total = ref(0)
    const loading = ref(false)

    async function fetchList(query: Query): Promise<void> {
      loading.value = true
      try {
        const page = await api.list(query)
        list.value = page.list
        total.value = page.total
      } catch (error) {
        // 统一上报后原样抛出：错误处理仍由调用方（页面 / useListPage）决定
        base.reportError(error, { store: storeId })
        throw error
      } finally {
        loading.value = false
      }
    }

    async function fetchOne(id: string): Promise<Entity> {
      return api.get(id)
    }

    async function create(data: Record<string, unknown>): Promise<Entity> {
      return api.create(data)
    }

    async function update(id: string, data: Record<string, unknown>): Promise<Entity> {
      return api.update(id, data)
    }

    async function remove(id: string): Promise<void> {
      await api.remove(id)
      list.value = list.value.filter((item) => item.id !== id)
      total.value = Math.max(0, total.value - 1)
    }

    return { list, total, loading, fetchList, fetchOne, create, update, remove }
  })
}
