/**
 * 错误基类：统一错误语义——错误码、用户提示映射与上报委托。
 *
 * 对齐后端 `BizError` 体系（错误码段位 1xxxx 通用 / 2xxxx 认证 / 3xxxx 用户组织 /
 * 4xxxx 配置 / 8xxxx 开放·租户）：前端**不重新发明错误码**，只做「携带 + 映射 + 分流 + 上报」。
 * 按标准 `Error` 派生（保留 `instanceof Error` 与堆栈），并挂接在**组件根机制层**（`mechanisms`）；
 * 上报统一委托根系 `reportError`（去重 / 限流由根系负责），本文件不另建通道。
 */

import type { BaseFrontend } from './BaseFrontend'

/** 未实现（占位 `stub` 调用）——前端内建，待与《后端基类清单》错误码段位对齐 */
export const NOT_IMPLEMENTED_CODE = 10001

/** 限流段（组件设计错误节点 §4） */
export const RATE_LIMIT_CODE = 10005

/** 权限不足（组件设计错误节点 §4；具体码值随后端权限段对齐） */
export const PERMISSION_CODE = 30001

const AUTH_SEGMENT_START = 20000
const AUTH_SEGMENT_END = 29999
const FALLBACK_USER_MESSAGE = '操作失败，请稍后重试'

/** 错误码 → 用户提示映射（未映射时由调用方 i18n `error.{code}` 或通用文案兜底） */
export const ERROR_MESSAGES: Record<number, string> = {
  [NOT_IMPLEMENTED_CODE]: '该功能尚未实现',
  [RATE_LIMIT_CODE]: '操作过于频繁，请稍后再试',
  [PERMISSION_CODE]: '没有操作权限',
}

/** 追加 / 覆盖错误码提示映射（产品与业务错误码由上游登记后注册） */
export function registerErrorMessages(map: Record<number, string>): void {
  Object.assign(ERROR_MESSAGES, map)
}

/** 静态映射查询（无映射返回 `undefined`） */
export function messageForCode(code: number): string | undefined {
  const message: string | undefined = ERROR_MESSAGES[code]
  return message
}

/** 错误构造参数 */
export interface BaseErrorInit {
  /** 错误码（对齐后端段位） */
  code: number
  /** 技术信息（日志与开发态展示；不直接给用户） */
  message?: string
  /** 用户提示（缺省经 `toUserMessage()` 映射） */
  userMessage?: string
  /** 附加数据（校验明细 / 冲突对象 id 等） */
  data?: unknown
  /** 原始错误或响应（保留现场供上报） */
  cause?: unknown
}

/**
 * 错误基类：携带错误码与用户提示，统一响应解析、提示映射与上报。
 *
 * 使用口径：请求层 / 错误边界构造 `BaseError` 后交消息组件展示，并经 `report()` 上报；
 * 用户主动取消（`AbortController`）**不**构造本错误、不提示、不上报。
 */
export class BaseError extends Error {
  /** 错误码（对齐后端段位） */
  readonly code: number
  /** 用户提示（未显式给出时经 `toUserMessage()` 映射） */
  readonly userMessage: string
  /** 附加数据 */
  readonly data?: unknown

  constructor(init: BaseErrorInit) {
    super(init.message ?? `[${init.code}]`)
    this.name = 'BaseError'
    this.code = init.code
    this.userMessage = init.userMessage ?? ''
    this.data = init.data
    if (init.cause !== undefined) {
      this.cause = init.cause
    }
  }

  /**
   * 由统一响应 `{ code, message, data }` 构造。
   *
   * `code === 0`（成功）或结构不符返回 `null`，调用方据此保持既有成功路径不变；
   * 缺 `code` 时回退 `fallbackCode`。
   */
  static fromResponse(response: unknown, fallbackCode?: number): BaseError | null {
    if (!response || typeof response !== 'object') {
      return null
    }
    const record = response as { code?: unknown; message?: unknown; data?: unknown }
    const code = typeof record.code === 'number' ? record.code : fallbackCode
    if (code === undefined || code === 0) {
      return null
    }
    const message = typeof record.message === 'string' && record.message ? record.message : undefined
    return new BaseError({ code, message, data: record.data })
  }

  /** 用户提示：i18n `error.{code}` → 静态映射 → 通用回退（组件不得硬编码错误文案） */
  toUserMessage(base?: Pick<BaseFrontend, 't'> | null): string {
    const key = `error.${this.code}`
    const translated = base?.t(key)
    if (translated && translated !== key) {
      return translated
    }
    return messageForCode(this.code) ?? (this.userMessage || FALLBACK_USER_MESSAGE)
  }

  /** 上报：委托根系 `reportError`（去重 / 限流 / 生产分级由根系负责；不阻断业务） */
  report(base: Pick<BaseFrontend, 'reportError'>, meta?: Record<string, unknown>): void {
    base.reportError(this, { code: this.code, name: this.name, ...meta })
  }

  /** 认证段（2xxxx）：跳登录 / 触发刷新 */
  isAuth(): boolean {
    return this.code >= AUTH_SEGMENT_START && this.code <= AUTH_SEGMENT_END
  }

  /** 权限不足（供拦截层提示并刷新权限缓存） */
  isPermission(): boolean {
    return this.code === PERMISSION_CODE
  }

  /** 限流（供拦截层提示稍后再试） */
  isRateLimit(): boolean {
    return this.code === RATE_LIMIT_CODE
  }
}
