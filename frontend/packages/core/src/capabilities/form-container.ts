/**
 * 表单容器基类（表单容器族）：label 位置与宽度 / 规则汇总 / 字段错误定位 / 只读态。
 */

import { BaseValidatable } from './validatable'

/** 表单容器基类（抽象）。 */
export abstract class BaseFormContainer extends BaseValidatable<Record<string, unknown>> {
  /** 能力键（组件基类身份）。 */
  override readonly identifier: string = 'form-container'
  /** 表单只读态。 */
  formReadOnly = false
  /** 字段错误（字段名 → 错误文案）。 */
  #fieldErrors = new Map<string, string>()

  /** 字段错误映射（只读）。 */
  get fieldErrors(): Record<string, string> {
    return Object.fromEntries(this.#fieldErrors)
  }

  /** 表单是否有效（无字段错误）。 */
  get isFormValid(): boolean {
    return this.#fieldErrors.size === 0
  }

  /**
   * 设置字段错误（`undefined` 清除该字段）。
   *
   * @param field 字段名。
   * @param message 错误文案。
   */
  setFieldError(field: string, message: string | undefined): void {
    if (message === undefined) {
      this.#fieldErrors.delete(field)
    } else {
      this.#fieldErrors.set(field, message)
    }
  }

  /** 清空全部字段错误。 */
  clearFieldErrors(): void {
    this.#fieldErrors.clear()
  }
}
