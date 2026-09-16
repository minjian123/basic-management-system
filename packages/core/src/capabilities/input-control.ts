/** 输入形态能力：受控绑定壳状态（composition / 焦点 / 清空），不含字段语义。 */

import { BaseCapability, type CapabilityOptions } from '../mechanisms/capability'
import { observable } from '../base/observable'

export interface InputControlOptions extends Omit<CapabilityOptions, 'key'> {
  key?: string
  clearable?: boolean
}

export class BaseInputControl extends BaseCapability {
  readonly focused = observable(false)
  readonly composing = observable(false)
  readonly clearable: boolean

  constructor(options: InputControlOptions = {}) {
    super({ ...options, key: options.key ?? 'input-control' })
    this.clearable = options.clearable ?? true
  }

  onFocus(): void {
    this.focused.set(true)
  }

  onBlur(): void {
    this.focused.set(false)
  }

  /** composition 期间不提交值（由绑定层在 compositionend 后提交） */
  onCompositionStart(): void {
    this.composing.set(true)
  }

  onCompositionEnd(): void {
    this.composing.set(false)
  }

  describe(): Record<string, unknown> {
    return { ...super.describe(), clearable: this.clearable }
  }
}
