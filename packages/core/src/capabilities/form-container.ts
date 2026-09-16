/** 表单容器形态能力：label 位置 / 栅格 / 规则汇总 / 校验触发（表单渲染器对接点）。 */

import { BaseCapability, type CapabilityOptions } from '../mechanisms/capability'
import { observable } from '../base/observable'

export type LabelPosition = 'top' | 'left' | 'right'

export interface FormContainerOptions extends Omit<CapabilityOptions, 'key'> {
  key?: string
  labelPosition?: LabelPosition
  columns?: number
  readonly?: boolean
}

export class BaseFormContainer extends BaseCapability {
  readonly labelPosition: LabelPosition
  readonly columns: number
  readonly readonly = observable(false)
  readonly errors = observable<Readonly<Record<string, string>>>({})

  constructor(options: FormContainerOptions = {}) {
    super({ ...options, key: options.key ?? 'form-container' })
    this.labelPosition = options.labelPosition ?? 'top'
    this.columns = Math.max(1, options.columns ?? 1)
    this.readonly.set(options.readonly ?? false)
  }

  setError(field: string, message: string): void {
    this.errors.set({ ...this.errors.get(), [field]: message })
  }

  clearError(field?: string): void {
    if (field === undefined) {
      this.errors.set({})
      return
    }
    const next = { ...this.errors.get() }
    delete next[field]
    this.errors.set(next)
  }

  get hasErrors(): boolean {
    return Object.keys(this.errors.get()).length > 0
  }

  describe(): Record<string, unknown> {
    return { ...super.describe(), labelPosition: this.labelPosition, columns: this.columns }
  }
}
