/**
 * 值语义能力基类：值归一 / 三态 / 变更上报（输入与展示共用）。
 */

import { BasePlaceholderState } from './placeholder-state'

/** 值变更监听器。 */
export type ValueListener<T> = (value: T | undefined) => void

/** 值能力基类（抽象）。 */
export abstract class BaseValue<T = unknown> extends BasePlaceholderState {
  /** 能力键。 */
  readonly identifier: string = 'value'
  /** 当前值。 */
  #value: T | undefined
  /** 变更监听器。 */
  #listeners = new Set<ValueListener<T>>()

  /** 当前值。 */
  get value(): T | undefined {
    return this.#value
  }

  /** 空态（`null` / `undefined` / 空字符串）。 */
  get isEmpty(): boolean {
    const value = this.#value
    return value == null || value === ''
  }

  /** 只读态（缺省 false；具体组件可覆写）。 */
  get readOnly(): boolean {
    return false
  }

  /**
   * 设置值（值未变不触发）。
   *
   * @param next 新值。
   */
  setValue(next: T | undefined): void {
    if (Object.is(next, this.#value)) {
      return
    }
    this.#value = next
    this.#emit()
    if (!this.isDisposed) {
      this.notifyLifecycle('update')
    }
  }

  /**
   * 订阅值变更。
   *
   * @param listener 监听器。
   * @returns 取消函数（幂等）。
   */
  onChange(listener: ValueListener<T>): () => void {
    this.#listeners.add(listener)
    return () => {
      this.#listeners.delete(listener)
    }
  }

  /** 可订阅快照。 */
  getSnapshot(): T | undefined {
    return this.#value
  }

  /** 广播值变更（异常上报后继续）。 */
  #emit(): void {
    for (const listener of [...this.#listeners]) {
      try {
        listener(this.#value)
      } catch (error) {
        this.reportError(error, { scope: 'BaseValue.onChange' })
      }
    }
  }
}
