/**
 * 可点击（交互）能力基类：loading / disabled / 防抖 / 危险确认 / 键盘触发 / 埋点钩子。
 */

import { BaseComponent } from '../base/BaseComponent'

/** 可点击能力基类（抽象）。 */
export abstract class BaseClickable extends BaseComponent {
  /** 能力键。 */
  readonly identifier: string = 'clickable'
  /** 防抖间隔（毫秒；0 表示不防抖）。 */
  debounceMs = 0
  /** 是否危险操作（需二次确认）。 */
  dangerConfirm = false
  /** 危险确认处理器（宿主注入；返回是否放行）。 */
  confirmHandler: ((action: string) => boolean | Promise<boolean>) | undefined
  /** 键盘触发键。 */
  keyboardTrigger: 'enter' | 'space' | 'none' = 'enter'
  /** 埋点记录（占位：本地累计，实际上报由宿主注入）。 */
  readonly tracked: string[] = []
  /** 上次触发时间戳（防抖用）。 */
  #lastAt = 0

  /**
   * 触发闸门：禁用 / 加载中 / 防抖内均拒绝。
   *
   * @param action 动作名（埋点 / 确认用）。
   * @param now 当前时间戳（缺省 `Date.now()`，测试可注入）。
   * @returns 是否放行。
   */
  tryTrigger(action: string, now: number = Date.now()): boolean {
    if (this.disabled || this.loading) {
      return false
    }
    if (this.debounceMs > 0 && now - this.#lastAt < this.debounceMs) {
      return false
    }
    this.#lastAt = now
    this.track(action)
    return true
  }

  /**
   * 记录埋点。
   *
   * @param event 事件名。
   */
  track(event: string): void {
    this.tracked.push(event)
  }
}
