/** 表单页组合能力：三态（新增 / 编辑 / 详情）/ 提交编排 / 脏数据（与表单渲染器对称）。 */

import { BaseCapability, type CapabilityOptions } from '../mechanisms/capability'
import { observable } from '../base/observable'

export type FormMode = 'create' | 'edit' | 'detail'

export interface FormPageOptions extends Omit<CapabilityOptions, 'key'> {
  key?: string
  mode?: FormMode
}

export class BaseFormPage extends BaseCapability {
  readonly mode = observable<FormMode>('create')
  readonly dirty = observable(false)
  readonly submitting = observable(false)

  constructor(options: FormPageOptions = {}) {
    super({ ...options, key: options.key ?? 'form-page' })
    this.mode.set(options.mode ?? 'create')
  }

  get readonly(): boolean {
    return this.mode.get() === 'detail'
  }

  markDirty(): void {
    this.dirty.set(true)
  }

  /** 离开守卫（脏数据需确认；实际确认 UI 由插件承担） */
  canLeave(confirmed = false): boolean {
    return !this.dirty.get() || confirmed
  }

  describe(): Record<string, unknown> {
    return { ...super.describe(), mode: this.mode.get() }
  }
}
