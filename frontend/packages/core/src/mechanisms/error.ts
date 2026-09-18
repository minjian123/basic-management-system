/**
 * 错误基座（体系唯一有理由的多重继承）：`BaseObject` 能力 + 原生 `Error` 语义。
 *
 * 经 `withBaseObject(Error)` 混入，保留 `instanceof Error` 与堆栈；`code` 取前端内建错误码段位，
 * 文案映射走 i18n `error.{code}`（由宿主提示层消费）。
 */

import { withBaseObject } from '../base/mixin'

/** `BaseError` 附加选项。 */
export interface BaseErrorOptions {
  /** 用户可读提示（缺省由宿主按 `error.{code}` 取 i18n）。 */
  userMessage?: string
  /** 原始错误（保留因果链）。 */
  cause?: unknown
}

const BaseObjectError = withBaseObject(Error, 'bms:error')

/** 错误基座。 */
export class BaseError extends BaseObjectError {
  /** 错误码（前端内建码 / 平台段位）。 */
  readonly code: number
  /** 用户可读提示。 */
  readonly userMessage: string | undefined

  constructor(code: number, message: string, options: BaseErrorOptions = {}) {
    super(message)
    this.name = 'BaseError'
    this.code = code
    this.userMessage = options.userMessage
    if (options.cause !== undefined) {
      this.cause = options.cause
    }
  }
}
