/**
 * 占位基类（框架无关核心）：占位先行统一语义。
 *
 * 三类原因（`pending` 待实现 / `null` 后端未就绪 / `stub` 桩）× 三类降级
 * （`empty` 空态 / `disabled` 禁用 / `hidden` 隐藏）；约定：**占位不发起请求、不写缓存、无副作用**。
 */

import { BaseComponent, type ComponentBaseOptions } from '../base/BaseComponent'

export type PlaceholderReason = 'pending' | 'null' | 'stub'
export type PlaceholderFallback = 'empty' | 'disabled' | 'hidden'

export interface PlaceholderOptions extends ComponentBaseOptions {
  reason: PlaceholderReason
  fallback?: PlaceholderFallback
  /** 占位说明（调试 / 日志用） */
  note?: string
}

export class BasePlaceholder extends BaseComponent {
  readonly reason: PlaceholderReason
  readonly fallback: PlaceholderFallback
  readonly note: string | undefined

  constructor(options: PlaceholderOptions) {
    super(options)
    this.reason = options.reason
    this.fallback = options.fallback ?? 'empty'
    this.note = options.note
  }

  describe(): Record<string, unknown> {
    return { reason: this.reason, fallback: this.fallback, note: this.note }
  }
}
