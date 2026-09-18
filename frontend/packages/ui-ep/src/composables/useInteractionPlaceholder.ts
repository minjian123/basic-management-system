/** 交互类占位组合式：依赖后端的交互件在数据通路未就绪时的降级语义（禁用 / 不请求 / 就绪切换）。 */

import type { BaseDataState, DataStateName, SettleState } from '@bms/core'
import { computed, ref, watch, type Ref } from 'vue'

import { useBaseDataState } from './useBaseDataState'

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
  /** 数据状态基类实例（经 `BaseDataState` 挂链）。 */
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
  const ready = ref(options.ready ?? false)
  const requestCount = ref(0)
  const data = useBaseDataState()
  const degraded = computed(() => !ready.value)
  const disabled = computed(() => !ready.value)

  watch(
    ready,
    (value) => {
      data.setState(value ? 'ready' : 'empty')
    },
    { immediate: true, flush: 'sync' },
  )

  return {
    ready,
    degraded,
    disabled,
    requestCount,
    state: data.state,
    dataState: data.dataState,
    setReady: (value) => {
      ready.value = value
    },
    markLoaded: () => {
      if (!ready.value) {
        return
      }
      requestCount.value += 1
    },
    begin: data.begin,
    settle: data.settle,
  }
}
