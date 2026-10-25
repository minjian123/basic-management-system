/** 占位字段组合式：输入组件基类 `BaseInput`（经 `BaseField` → `BaseValue` → `BasePlaceholderState` 继承占位语义）的薄投影。 */

import { BaseInput } from '@bms/core'
import { computed, onScopeDispose, ref, type Ref } from 'vue'

/** 具体占位字段件（直接继承输入组件基类，占位语义经链上继承取得）。 */
class FieldPlaceholderState extends BaseInput<unknown> {}

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
  const state = new FieldPlaceholderState()
  state.disabled = options.disabled ?? false
  state.setReady(options.ready ?? false)

  const ready = ref(state.ready)
  const degraded = ref(state.degraded)
  const requestCount = ref(state.requestCount)
  const disabled = computed(() => state.disabled || !ready.value)
  const value = ref<unknown>(state.value)
  state.onChange((next) => {
    value.value = next
  })
  const off = state.onLifecycle((event) => {
    if (event === 'update') {
      ready.value = state.ready
      degraded.value = state.degraded
      requestCount.value = state.requestCount
      value.value = state.value
    }
  })
  onScopeDispose(() => {
    off()
    state.dispose()
  })

  return {
    ready,
    degraded,
    disabled,
    requestCount,
    setReady: (value) => state.setReady(value),
    markLoaded: () => state.markLoaded(),
    value,
    setValue: (value) => state.setValue(value),
  }
}
