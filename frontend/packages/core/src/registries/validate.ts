/** 注册声明校验辅助（组合校验错误文案）。 */

import { BaseError } from '../mechanisms/error'
import { ErrorCodes } from '../mechanisms/error-codes'

/**
 * 构造注册声明校验错误。
 *
 * @param scope 校验范围。
 * @param detail 详情。
 * @returns 错误实例。
 */
export function schemaError(scope: string, detail: string): BaseError {
  return new BaseError(ErrorCodes.CAPABILITY_VIOLATION, `${scope}：${detail}`)
}
