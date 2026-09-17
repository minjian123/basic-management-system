/**
 * 字段壳能力（核心试点）：label / 必填 / 帮助 / 错误 展示状态。
 */

import { BaseCapability, type CapabilityOptions } from '../mechanisms/capability'
import { observable } from '../base/observable'

export interface FieldShellOptions extends Omit<CapabilityOptions, 'key'> {
  key?: string
  label?: string
  required?: boolean
  help?: string
}

export class BaseFieldShell extends BaseCapability {
  readonly label: string
  readonly required: boolean
  readonly help: string
  readonly error: ReturnType<typeof observable<string>>

  constructor(options: FieldShellOptions = {}) {
    super({ ...options, key: options.key ?? 'field-shell' })
    this.label = options.label ?? ''
    this.required = options.required ?? false
    this.help = options.help ?? ''
    this.error = observable('')
  }

  setError(message: string): void {
    this.error.set(message)
  }

  clearError(): void {
    this.error.set('')
  }

  get hasError(): boolean {
    return this.error.get().length > 0
  }

  describe(): Record<string, unknown> {
    return { ...super.describe(), label: this.label, required: this.required }
  }
}
