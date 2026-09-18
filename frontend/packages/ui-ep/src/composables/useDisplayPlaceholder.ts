/** 占位展示组合式：依赖后端的展示件在数据通路未就绪时的降级语义（只读 / 不请求 / 就绪切换）。 */

import { computed, ref, type Ref } from 'vue'

import { useBaseDisplay } from './useBaseDisplay'

/** 选项。 */
export interface UseDisplayPlaceholderOptions {
  /** 数据通路是否就绪（缺省 false）。 */
  ready?: boolean
  /** 初始值（只读展示值）。 */
  value?: unknown
}

/** `useDisplayPlaceholder` 返回面。 */
export interface UseDisplayPlaceholderResult {
  /** 是否就绪（响应式）。 */
  ready: Ref<boolean>
  /** 是否降级（占位）态（响应式）。 */
  degraded: Ref<boolean>
  /** 已发起加载次数（占位态必须保持 0）。 */
  requestCount: Ref<number>
  /** 切换就绪态。 */
  setReady: (value: boolean) => void
  /** 标记一次加载（真实实现接入后调用）。 */
  markLoaded: () => void
  /** 展示值（只读，经展示件投影）。 */
  value: Ref<unknown>
  /** 设置值。 */
  setValue: (value: unknown) => void
}

/**
 * 使用占位展示降级语义。
 *
 * @param options 选项。
 * @returns 就绪 / 降级与请求计数。
 */
export function useDisplayPlaceholder(options: UseDisplayPlaceholderOptions = {}): UseDisplayPlaceholderResult {
  const ready = ref(options.ready ?? false)
  const requestCount = ref(0)
  const base = useBaseDisplay<unknown>()
  if (options.value !== undefined) {
    base.setValue(options.value)
  }
  const degraded = computed(() => !ready.value)

  return {
    ready,
    degraded,
    requestCount,
    setReady: (value) => {
      ready.value = value
    },
    markLoaded: () => {
      if (!ready.value) {
        return
      }
      requestCount.value += 1
    },
    value: base.value,
    setValue: (value) => base.setValue(value),
  }
}
