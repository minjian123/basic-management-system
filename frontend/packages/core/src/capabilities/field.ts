/**
 * 字段编排能力（核心试点）：组合「值 + 壳 + 权限」，做校验触发与门禁合并（不重复实现下层片段能力）。
 */

import { BaseCapability, type CapabilityOptions } from '../mechanisms/capability'
import { BaseFieldPerm, type FieldPermOptions } from './field-perm'
import { BaseFieldShell, type FieldShellOptions } from './field-shell'
import { BaseValue, type ValueOptions } from './value'

export interface FieldOptions<T = unknown> extends Omit<CapabilityOptions, 'key'> {
  key?: string
  value?: Omit<ValueOptions<T>, 'key'>
  shell?: Omit<FieldShellOptions, 'key'>
  perm?: Omit<FieldPermOptions, 'key'>
  disabled?: boolean
}

export class BaseField<T = unknown> extends BaseCapability {
  readonly value: BaseValue<T>
  readonly shell: BaseFieldShell
  readonly perm: BaseFieldPerm

  private readonly externalDisabled: boolean

  constructor(options: FieldOptions<T> = {}) {
    super({ ...options, key: options.key ?? 'field' })
    this.value = new BaseValue<T>({ ...options.value, key: 'value' })
    this.shell = new BaseFieldShell({ ...options.shell, key: 'field-shell' })
    this.perm = new BaseFieldPerm({ ...options.perm, key: 'field-perm' })
    this.externalDisabled = options.disabled ?? false
  }

  /** 门禁合并（props 禁用 || 字段权限不可编辑；优先级显式、单一出口；域语义名） */
  get effectiveDisabled(): boolean {
    return this.externalDisabled || this.perm.permDisabled
  }

  getValue(): T {
    return this.value.getValue()
  }

  setValue(value: T): void {
    if (this.effectiveDisabled) {
      return
    }
    this.value.setValue(value)
    void this.validate()
  }

  /** 校验（骨架：必填；规则体系随后续任务扩展） */
  validate(): boolean {
    if (this.effectiveRequired && this.value.isEmpty) {
      this.shell.setError('required')
      return false
    }
    this.shell.clearError()
    return true
  }

  get effectiveRequired(): boolean {
    return this.shell.required || this.perm.required
  }

  describe(): Record<string, unknown> {
    return { ...super.describe(), disabled: this.effectiveDisabled, required: this.effectiveRequired }
  }
}
