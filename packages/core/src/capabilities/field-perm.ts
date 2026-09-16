/**
 * 字段权限能力（核心试点）：可见 / 可编辑 / 必填 三态 + 脱敏；元数据来源随后端接入（占位）。
 */

import { BaseCapability, type CapabilityOptions } from '../mechanisms/capability'

export interface FieldPermOptions extends Omit<CapabilityOptions, 'key'> {
  key?: string
  visible?: boolean
  editable?: boolean
  required?: boolean
  /** 脱敏（展示侧按规则掩码；规则细节随后端接入） */
  masked?: boolean
}

export class BaseFieldPerm extends BaseCapability {
  readonly visible: boolean
  readonly editable: boolean
  readonly required: boolean
  readonly masked: boolean

  constructor(options: FieldPermOptions = {}) {
    super({ ...options, key: options.key ?? 'field-perm' })
    this.visible = options.visible ?? true
    this.editable = options.editable ?? true
    this.required = options.required ?? false
    this.masked = options.masked ?? false
  }

  /** 合并禁用语义（不可编辑即禁用；域语义名，不占用组件根通用 `disabled`） */
  get permDisabled(): boolean {
    return !this.editable
  }

  describe(): Record<string, unknown> {
    return { ...super.describe(), visible: this.visible, editable: this.editable, masked: this.masked }
  }
}
