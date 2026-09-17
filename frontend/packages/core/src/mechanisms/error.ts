/**
 * 错误基类（对齐后端 `BizError`）：错误码 + 用户提示 + 上报委托。
 *
 * 前端内建码段位：`19xxx` 为前端保留子段（如 `19001` 未实现）；片段声明违规 `10001`、
 * 注册表冲突 `10003`、限流 `10005`、权限 `30001`（《命名规范》§9）。
 */

export interface BaseErrorOptions {
  /** 用户可读提示（缺省由渲染插件按 `error.{code}` 取 i18n） */
  userMessage?: string
  cause?: unknown
}

export class BaseError extends Error {
  readonly code: number
  readonly userMessage: string | undefined

  constructor(code: number, message: string, options: BaseErrorOptions = {}) {
    super(message, options.cause !== undefined ? { cause: options.cause } : undefined)
    this.name = 'BaseError'
    this.code = code
    this.userMessage = options.userMessage
  }
}

/** 前端内建码（骨架集；扩充走《命名规范》段位登记） */
export const ErrorCodes = {
  /** 片段声明违规（参数校验失败） */
  CAPABILITY_VIOLATION: 10001,
  /** 注册表唯一性冲突 */
  REGISTRY_CONFLICT: 10003,
  /** 未注册不可用（扩展点未登记） */
  PROVIDER_NOT_REGISTERED: 10002,
  /** 未实现（前端保留子段） */
  NOT_IMPLEMENTED: 19001,
} as const
