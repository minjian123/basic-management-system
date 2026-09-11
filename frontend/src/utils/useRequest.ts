/** 通用异步请求状态：loading / error / run + 竞态保护（仅最新请求写入状态）。 */

import { ref, type Ref } from 'vue'

export interface UseRequestOptions<T> {
  onSuccess?: (data: T) => void
  onError?: (error: unknown) => void
}

export interface UseRequestResult<T> {
  data: Ref<T | null>
  loading: Ref<boolean>
  error: Ref<unknown>
  run: () => Promise<T | null>
}

export function useRequest<T>(fetcher: () => Promise<T>, options: UseRequestOptions<T> = {}): UseRequestResult<T> {
  const data = ref<T | null>(null) as Ref<T | null>
  const loading = ref(false)
  const error = ref<unknown>(null)
  let sequence = 0

  async function run(): Promise<T | null> {
    const current = ++sequence
    loading.value = true
    error.value = null
    try {
      const result = await fetcher()
      if (current === sequence) {
        data.value = result
        options.onSuccess?.(result)
      }
      return result
    } catch (err) {
      if (current === sequence) {
        error.value = err
        options.onError?.(err)
      }
      return null
    } finally {
      if (current === sequence) {
        loading.value = false
      }
    }
  }

  return { data, loading, error, run }
}
