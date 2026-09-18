/**
 * 字段语义能力基类：字段标识 / 校验触发 / 字段上下文（输入族公共能力）。
 */

import { BaseValue } from './value'

/** 校验触发时机。 */
export type FieldTrigger = 'change' | 'blur' | 'submit'

/** 字段能力基类（抽象）。 */
export abstract class BaseField<T = unknown> extends BaseValue<T> {
  /** 能力键。 */
  override readonly identifier: string = 'field'
  /** 依赖能力键。 */
  override readonly depends = ['value']
  /** 字段标识（提交键）。 */
  fieldName = ''
  /** 校验触发时机。 */
  trigger: FieldTrigger = 'change'
}
