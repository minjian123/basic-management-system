/** 交互类占位组合式：数据状态能力基类 `BaseDataState`（经 `BasePlaceholderState` 继承占位语义）的薄投影。 */

import type { DataStateName, SettleState } from '@bms/core'
import { BaseDataState } from '@bms/core'
import { computed, onScopeDispose, ref, watch, type Ref } from 'vue'

/** 具体占位数据状态件（直接继承数据状态能力基类，占位语义经链上继承取得）。 */
class InteractionPlaceholderState extends BaseDataState {}

/** 选项。 */
export interface UseInteractionPlaceholderOptions {
  /** 数据通路是否就绪（缺省 false）。 */
  ready?: boolean
}

/** `useInteractionPlaceholder` 返回面。 */
export interface UseInteractionPlaceholderResult {
  /** 是否就绪（响应式）。 */
  ready: Ref<boolean>
  /** 是否降级（占位）态（响应式）。 */
  degraded: Ref<boolean>
  /** 生效禁用（占位态强制禁用，响应式）。 */
  disabled: Ref<boolean>
  /** 已发起加载次数（占位态必须保持 0）。 */
  requestCount: Ref<number>
  /** 数据状态（`loading` / `ready` / `empty` / `error`，响应式）。 */
  state: Ref<DataStateName>
  /** 数据状态基类实例（即占位状态件本身）。 */
  dataState: BaseDataState
  /** 切换就绪态。 */
  setReady: (value: boolean) => void
  /** 标记一次加载（真实实现接入后调用）。 */
  markLoaded: () => void
  /** 开始一次加载（返回竞态令牌）。 */
  begin: () => number
  /** 以令牌结算（非最新令牌忽略）。 */
  settle: (token: number, state: SettleState) => boolean
}

/**
 * 使用交互件占位降级语义。
 *
 * @param options 选项。
 * @returns 就绪 / 降级 / 禁用与请求计数。
 */
export function useInteractionPlaceholder(
  options: UseInteractionPlaceholderOptions = {},
): UseInteractionPlaceholderResult {
  const state = new InteractionPlaceholderState()
  state.setReady(options.ready ?? false)

  const ready = ref(state.ready)
  const degraded = ref(state.degraded)
  const requestCount = ref(state.requestCount)
  const currentState = ref<DataStateName>(state.state)
  const disabled = computed(() => !ready.value)

  const off = state.onLifecycle((event) => {
    if (event === 'update') {
      ready.value = state.ready
      degraded.value = state.degraded
      requestCount.value = state.requestCount
    }
  })
  const offState = state.onStateChange((next) => {
    currentState.value = next
  })
  onScopeDispose(() => {
    off()
    offState()
    state.dispose()
  })

  watch(
    ready,
    (value) => {
      const token = state.begin()
      state.settle(token, value ? 'ready' : 'empty')
    },
    { immediate: true, flush: 'sync' },
  )

  return {
    ready,
    degraded,
    disabled,
    requestCount,
    state: currentState,
    dataState: state,
    setReady: (value) => state.setReady(value),
    markLoaded: () => state.markLoaded(),
    begin: () => state.begin(),
    settle: (token, next) => state.settle(token, next),
  }
}
