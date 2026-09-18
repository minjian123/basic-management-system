/**
 * 展示组件基类（展示族）：只读呈现 / 空值占位 / 省略与取值。
 */

import { BaseValue } from './value'

/** 展示组件基类（抽象）。 */
export abstract class BaseDisplay<T = unknown> extends BaseValue<T> {
  /** 能力键（组件基类身份）。 */
  override readonly identifier: string = 'display'
  /** 空值占位文案。 */
  emptyText = '—'
  /** 是否省略（超出以 tooltip 呈现）。 */
  ellipsis = false

  /** 只读呈现文本（空值用占位）。 */
  get displayText(): string {
    return this.isEmpty ? this.emptyText : String(this.value)
  }

  /** 点击取值。 */
  pick(): T | undefined {
    return this.value
  }
}
