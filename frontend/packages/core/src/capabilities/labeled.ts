/**
 * 标签语义能力基类：label 文案 / 位置 / 宽度、必填标记、帮助与错误位。
 */

import { BaseComponent } from '../base/BaseComponent'

/** 标签位置。 */
export type LabelPosition = 'top' | 'left' | 'right'

/** 标签能力基类（抽象）。 */
export abstract class BaseLabeled extends BaseComponent {
  /** 能力键。 */
  readonly identifier: string = 'labeled'
  /** 标签文案。 */
  label = ''
  /** 标签位置。 */
  labelPosition: LabelPosition = 'top'
  /** 标签宽度（数字按像素）。 */
  labelWidth: number | string | undefined
  /** 是否必填。 */
  required = false
  /** 帮助提示。 */
  helpText: string | undefined
  /** 错误提示（由校验回填）。 */
  errorText: string | undefined
}
