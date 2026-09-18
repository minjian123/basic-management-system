/** 请求层错误（继承核心错误基座，保留 `instanceof Error` 与错误码段位）。 */

import { BaseError, ErrorCodes } from '@bms/core'

/** 模块 API 错误。 */
export class ApiError extends BaseError {
  constructor(code: number, message: string, options: { userMessage?: string; cause?: unknown } = {}) {
    super(code, message, options)
  }
}

/** 会话失效（401）。 */
export class SessionExpiredError extends ApiError {
  constructor(message = '会话已失效') {
    super(ErrorCodes.PERMISSION_DENIED, message, { userMessage: message })
  }
}
