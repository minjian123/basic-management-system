/**
 * 通用异步请求状态：loading / data / error + 竞态保护（仅最新请求写回）+ 取消。
 *
 * - `run()`：手动发起（`fetcher` 收到 `AbortSignal`，可透传给 `request` 取消在途）；
 * - `refresh()`：重发（重试 / 刷新按钮）；
 * - `cancel()`：中止在途请求并使响应过期（`loading` 复位）；
 * - `immediate: true`：挂载即发起（缺省 false，保持既有行为）。
 */

import { ref, type Ref } from 'vue'

export interface UseRequestOptions<T> {
  /** 挂载即发起（缺省 false） */
  immediate?: boolean
  onSuccess?: (data: T) => void
  onError?: (error: unknown) => void
}

export interface UseRequestResult<T> {
  data: Ref<T | null>
  loading: Ref<boolean>
  error: Ref<unknown>
  run: () => Promise<T | null>
  /** 用当前 fetcher 重发（重试） */
  refresh: () => Promise<T | null>
  /** 取消在途请求（主动取消不写 error、不提示） */
  cancel: () => void
}

function isAbortError(error: unknown): boolean {
  return typeof error === 'object' && error !== null && (error as { name?: string }).name === 'AbortError'
}

export function useRequest<T>(
  fetcher: (signal: AbortSignal) => Promise<T>,
  options: UseRequestOptions<T> = {},
): UseRequestResult<T> {
  const data = ref<T | null>(null) as Ref<T | null>
  const loading = ref(false)
  const error = ref<unknown>(null)
  let sequence = 0
  let controller: AbortController | null = null

  async function run(): Promise<T | null> {
    const current = ++sequence
    controller?.abort()
    controller = new AbortController()
    const { signal } = controller
    loading.value = true
    error.value = null
    try {
      const result = await fetcher(signal)
      if (current === sequence) {
        data.value = result
        options.onSuccess?.(result)
      }
      return result
    } catch (err) {
      if (isAbortError(err)) {
        return null
      }
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

  function cancel(): void {
    controller?.abort()
    controller = null
    // 使在途响应过期（不写回状态）
    sequence += 1
    loading.value = false
  }

  if (options.immediate === true) {
    void run()
  }

  return {
    data,
    loading,
    error,
    run,
    refresh: () => run(),
    cancel,
  }
}
