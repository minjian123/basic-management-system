/** 占位字段组合式：依赖后端的字段在数据通路未就绪时的降级语义（禁用 / 不请求 / 就绪切换）。 */

import { computed, ref, type Ref } from 'vue'

import { useBaseInput } from './useBaseInput'

/** 选项。 */
export interface UseFieldPlaceholderOptions {
  /** 数据通路是否就绪（缺省 false）。 */
  ready?: boolean
  /** 件级禁用。 */
  disabled?: boolean
}

/** `useFieldPlaceholder` 返回面。 */
export interface UseFieldPlaceholderResult {
  /** 是否就绪（响应式）。 */
  ready: Ref<boolean>
  /** 是否降级（占位）态（响应式）。 */
  degraded: Ref<boolean>
  /** 生效禁用（占位态强制禁用，响应式）。 */
  disabled: Ref<boolean>
  /** 已发起加载次数（占位态必须保持 0）。 */
  requestCount: Ref<number>
  /** 切换就绪态。 */
  setReady: (value: boolean) => void
  /** 标记一次加载（真实实现接入后调用）。 */
  markLoaded: () => void
  /** 值（受控，经输入件投影）。 */
  value: Ref<unknown>
  /** 设置值。 */
  setValue: (value: unknown) => void
}

/**
 * 使用占位字段降级语义。
 *
 * @param options 选项。
 * @returns 就绪 / 降级 / 禁用与请求计数。
 */
export function useFieldPlaceholder(options: UseFieldPlaceholderOptions = {}): UseFieldPlaceholderResult {
  const ready = ref(options.ready ?? false)
  const requestCount = ref(0)
  const base = useBaseInput<unknown>({ disabled: options.disabled })
  const disabled = computed(() => base.disabled.value || !ready.value)
  const degraded = computed(() => !ready.value)

  return {
    ready,
    degraded,
    disabled,
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
