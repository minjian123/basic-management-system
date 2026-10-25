/** 数据状态投影：把核心数据状态能力基类 `BaseDataState` 投影为组合式（`loading → ready / empty / error` 状态机与竞态）。 */

import { BaseDataState, type DataStateName, type SettleState } from '@bms/core'
import { onScopeDispose, ref, type Ref } from 'vue'

/** 具体数据状态件（可实例化）。 */
class DataStateHolder extends BaseDataState {}

/** `useBaseDataState` 返回面。 */
export interface UseBaseDataStateResult {
  /** 数据状态基类实例。 */
  dataState: BaseDataState
  /** 当前状态（响应式）。 */
  state: Ref<DataStateName>
  /** 开始一次加载（置 `loading` 并返回竞态令牌）。 */
  begin: () => number
  /** 以令牌结算（非最新令牌忽略）。 */
  settle: (token: number, state: SettleState) => boolean
  /** 便捷置状态（`loading` 走 `begin`，其余自动取令牌结算）。 */
  setState: (state: DataStateName) => void
}

/**
 * 使用数据状态投影。
 *
 * @returns 数据状态基类实例与响应式面。
 */
export function useBaseDataState(): UseBaseDataStateResult {
  const dataState = new DataStateHolder()
  const state = ref<DataStateName>(dataState.state)
  const off = dataState.onStateChange((next) => {
    state.value = next
  })
  onScopeDispose(off)

  return {
    dataState,
    state,
    begin: () => dataState.begin(),
    settle: (token, next) => dataState.settle(token, next),
    setState: (next) => {
      const token = dataState.begin()
      if (next !== 'loading') {
        dataState.settle(token, next)
      }
    },
  }
}
