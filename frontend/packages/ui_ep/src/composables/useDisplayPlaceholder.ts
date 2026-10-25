/** 占位展示组合式：展示组件基类 `BaseDisplay`（经 `BaseValue` → `BasePlaceholderState` 继承占位语义）的薄投影。 */

import { BaseDisplay } from '@bms/core'
import { onScopeDispose, ref, type Ref } from 'vue'

/** 具体占位展示件（直接继承展示组件基类，占位语义经链上继承取得）。 */
class DisplayPlaceholderState extends BaseDisplay<unknown> {}

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
  const state = new DisplayPlaceholderState()
  if (options.value !== undefined) {
    state.setValue(options.value)
  }
  state.setReady(options.ready ?? false)

  const ready = ref(state.ready)
  const degraded = ref(state.degraded)
  const requestCount = ref(state.requestCount)
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
    requestCount,
    setReady: (value) => state.setReady(value),
    markLoaded: () => state.markLoaded(),
    value,
    setValue: (value) => state.setValue(value),
  }
}
