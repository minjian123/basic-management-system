/** 展示形态能力：密度 / 空值占位 / 省略骨架，不含字段格式化编排。 */

import { BaseCapability, type CapabilityOptions } from '../mechanisms/capability'
import { observable } from '../base/observable'

export interface DisplayControlOptions extends Omit<CapabilityOptions, 'key'> {
  key?: string
  /** 空值占位（缺省 `—`） */
  emptyText?: string
  ellipsis?: boolean
}

export class BaseDisplayControl extends BaseCapability {
  readonly emptyText: string
  readonly ellipsis: boolean
  readonly hovered = observable(false)

  constructor(options: DisplayControlOptions = {}) {
    super({ ...options, key: options.key ?? 'display-control' })
    this.emptyText = options.emptyText ?? '—'
    this.ellipsis = options.ellipsis ?? false
  }

  /** 空值占位派生（值来源由调用方传入，避免重复实现值语义） */
  text(model: unknown): string {
    if (model === undefined || model === null || model === '') {
      return this.emptyText
    }
    return String(model)
  }

  describe(): Record<string, unknown> {
    return { ...super.describe(), ellipsis: this.ellipsis }
  }
}
