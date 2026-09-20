/**
 * 数据状态能力基类：`loading → ready / empty / error` 状态机与竞态处理。
 */

import { BasePlaceholderState } from './placeholder-state'

/** 数据状态。 */
export type DataStateName = 'loading' | 'ready' | 'empty' | 'error'
/** 结算状态（非加载中）。 */
export type SettleState = Exclude<DataStateName, 'loading'>
/** 状态变更监听器。 */
export type DataStateListener = (state: DataStateName) => void

/** 数据状态能力基类（抽象）。 */
export abstract class BaseDataState extends BasePlaceholderState {
  /** 能力键。 */
  readonly identifier: string = 'data-state'
  /** 当前状态。 */
  #state: DataStateName = 'loading'
  /** 竞态序号。 */
  #seq = 0
  /** 状态监听器。 */
  #listeners = new Set<DataStateListener>()

  /** 当前状态。 */
  get state(): DataStateName {
    return this.#state
  }

  /**
   * 开始一次加载（递增竞态令牌并置 `loading`）。
   *
   * @returns 本次加载的竞态令牌。
   */
  begin(): number {
    this.#seq += 1
    this.#set('loading')
    return this.#seq
  }

  /**
   * 以令牌结算（非最新令牌忽略，防竞态覆盖）。
   *
   * @param token `begin` 返回的令牌。
   * @param state 结算状态。
   * @returns 是否生效。
   */
  settle(token: number, state: SettleState): boolean {
    if (token !== this.#seq) {
      return false
    }
    this.#set(state)
    return true
  }

  /**
   * 订阅状态变更。
   *
   * @param listener 监听器。
   * @returns 取消函数（幂等）。
   */
  onStateChange(listener: DataStateListener): () => void {
    this.#listeners.add(listener)
    return () => {
      this.#listeners.delete(listener)
    }
  }

  /** 设置状态并广播（同态不触发）。 */
  #set(state: DataStateName): void {
    if (state === this.#state) {
      return
    }
    this.#state = state
    for (const listener of [...this.#listeners]) {
      try {
        listener(state)
      } catch (error) {
        this.reportError(error, { scope: 'BaseDataState.onStateChange' })
      }
    }
    if (!this.isDisposed) {
      this.notifyLifecycle('update')
    }
  }
}
