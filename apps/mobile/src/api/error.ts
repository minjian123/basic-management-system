/**
 * 请求层错误契约：`ApiError`（继承 `BaseError`）+ 错误码文案映射 `errorMessage`。
 *
 * 统一响应 `{code, message, data}` 的失败分支与 HTTP 错误分支均归一为 `ApiError`，
 * 由调用方捕获（`code` / `httpStatus` / `details` / `traceId`），提示经适配注入。
 */

import { BaseError } from '@bms/core'

import { i18n } from '@/i18n'

/** 会话失效（镜像平台 AUTH 段；后端 `/auth` 未接入时用于 401 占位） */
export const AUTH_SESSION_CODE = 20001

/** 网络异常 / 响应结构异常（前端内建） */
export const NETWORK_ERROR_CODE = -1

/** 服务内部错误（镜像平台 INTERNAL，5xx 归一） */
export const INTERNAL_ERROR_CODE = 10000

/** 参数校验失败（镜像平台 PARAM，400 / 422 等归一） */
export const PARAM_CODE = 10001

/** 资源不存在（镜像平台 NOT_FOUND，404 归一） */
export const NOT_FOUND_CODE = 10002

/** 冲突（镜像平台 CONFLICT；409 乐观锁 / 注册表同 key 等） */
export const CONFLICT_CODE = 10003

/** 权限不足（镜像平台 PERMISSION，403 归一） */
export const PERMISSION_CODE = 30001

/** `ApiError` 构造参数 */
export interface ApiErrorInit {
  code: number
  /** 技术信息（缺省 `[code]`） */
  message?: string
  httpStatus?: number
  /** 业务附加数据（如校验明细） */
  details?: unknown
  traceId?: string
  cause?: unknown
}

/** 请求层统一错误对象（对齐后端 `BizError`：码 + 提示 + 附加数据） */
export class ApiError extends BaseError {
  /** 用户提示（构造时经 `errorMessage` 映射，必有值） */
  declare readonly userMessage: string
  /** HTTP 状态码（业务错误为响应状态，网络异常为 0） */
  readonly httpStatus: number
  /** 业务附加数据（后端 `data`） */
  readonly details?: unknown
  /** 链路标识（后端响应头 / 响应体携带时） */
  readonly traceId?: string

  constructor(init: ApiErrorInit) {
    const message = init.message ?? `[${init.code}]`
    super(init.code, message, {
      userMessage: errorMessage(init.code, message),
      ...(init.cause !== undefined ? { cause: init.cause } : {}),
    })
    this.name = 'ApiError'
    this.httpStatus = init.httpStatus ?? 0
    this.details = init.details
    this.traceId = init.traceId
  }
}

/**
 * 错误提示文案：i18n `error.{code}`（码或语义键）→ 后端 `fallback` → 通用兜底。
 *
 * 示例：`errorMessage(10002)` / `errorMessage('network')` / `errorMessage(999, '后端文案')`。
 */
export function errorMessage(code: number | string, fallback?: string): string {
  const t = i18n.global.t as unknown as (key: string) => string
  const key = `error.${code}`
  const translated = t(key)
  if (translated && translated !== key) {
    return translated
  }
  if (fallback) {
    return fallback
  }
  const generic = t('error.default')
  return generic === 'error.default' ? '操作失败，请稍后重试' : generic
}
