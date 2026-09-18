/** 请求组合式：loading / 错误 / 结果（经核心 `request`）。 */

import { request, type RequestConfig } from '@bms/core'
import { ref, shallowRef, type Ref, type ShallowRef } from 'vue'

/** `useRequest` 返回面。 */
export interface UseRequestResult<T> {
  /** 加载中。 */
  loading: Ref<boolean>
  /** 结果数据。 */
  data: ShallowRef<T | undefined>
  /** 错误。 */
  error: ShallowRef<unknown>
  /** 执行请求（可覆盖配置）。 */
  run: (override?: Partial<RequestConfig>) => Promise<T | undefined>
}

/**
 * 请求组合式。
 *
 * @param config 请求配置或返回配置的函数（延迟取值）。
 */
export function useRequest<T>(config: RequestConfig | (() => RequestConfig)): UseRequestResult<T> {
  const loading = ref(false)
  const data = shallowRef<T>()
  const error = shallowRef<unknown>()

  async function run(override: Partial<RequestConfig> = {}): Promise<T | undefined> {
    loading.value = true
    error.value = undefined
    try {
      const base = typeof config === 'function' ? config() : config
      const result = await request<T>({ ...base, ...override })
      data.value = result
      return result
    } catch (caught) {
      error.value = caught
      return undefined
    } finally {
      loading.value = false
    }
  }

  return { loading, data, error, run }
}
