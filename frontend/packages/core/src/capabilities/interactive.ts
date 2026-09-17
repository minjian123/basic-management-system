/** 交互形态能力：可点击组件的公共（loading / disabled / 防抖 / 危险确认骨架）。 */

import { BaseCapability, type CapabilityOptions } from '../mechanisms/capability'
import { observable } from '../base/observable'

export interface InteractiveOptions extends Omit<CapabilityOptions, 'key'> {
  key?: string
  disabled?: boolean
  loading?: boolean
  /** 防抖（ms；0 表示不防抖） */
  debounce?: number
}

export class BaseInteractive extends BaseCapability {
  /** 忙碌（域语义名，避让组件根 `loading`） */
  readonly busy = observable(false)
  /** 自身禁用（域语义名，避让组件根 `disabled`） */
  readonly inactive = observable(false)
  private lastInvokeAt = 0

  constructor(options: InteractiveOptions = {}) {
    super({ ...options, key: options.key ?? 'interactive' })
    this.busy.set(options.loading ?? false)
    this.inactive.set(options.disabled ?? false)
    this.debounceMs = options.debounce ?? 0
  }

  private readonly debounceMs: number

  /** 触发可执行动作：禁用 / 加载中 / 防抖窗口内拒绝 */
  invoke(action: () => void): boolean {
    if (this.inactive.get() || this.busy.get()) {
      return false
    }
    const now = Date.now()
    if (this.debounceMs > 0 && now - this.lastInvokeAt < this.debounceMs) {
      return false
    }
    this.lastInvokeAt = now
    action()
    return true
  }

  describe(): Record<string, unknown> {
    return { ...super.describe(), debounce: this.debounceMs }
  }
}
