/**
 * 校验能力基类：规则汇总 / 触发时机 / 结果回传 / 错误定位。
 */

import { BaseLabeled } from './labeled'

/** 单条校验器（返回错误文案或 `undefined` 表示通过）。 */
export type Validator<T> = (value: T | undefined) => string | undefined

/** 校验能力基类（抽象）。 */
export abstract class BaseValidatable<T = unknown> extends BaseLabeled {
  /** 能力键。 */
  override readonly identifier: string = 'validatable'
  /** 依赖能力键。 */
  override readonly depends = ['labeled']
  /** 校验规则（按序执行，遇错即止）。 */
  readonly rules: Validator<T>[] = []
  /** 当前错误。 */
  #errors: string[] = []

  /** 当前错误清单（只读）。 */
  get errors(): readonly string[] {
    return this.#errors
  }

  /** 是否校验通过。 */
  get valid(): boolean {
    return this.#errors.length === 0
  }

  /**
   * 执行校验并回填错误位（`errorText`）。
   *
   * @param value 待校验值。
   * @returns 是否通过。
   */
  validate(value: T | undefined): boolean {
    const errors: string[] = []
    for (const rule of this.rules) {
      const message = rule(value)
      if (message !== undefined) {
        errors.push(message)
        break
      }
    }
    this.#errors = errors
    this.errorText = errors[0]
    return errors.length === 0
  }

  /** 清空错误。 */
  clearErrors(): void {
    this.#errors = []
    this.errorText = undefined
  }
}
