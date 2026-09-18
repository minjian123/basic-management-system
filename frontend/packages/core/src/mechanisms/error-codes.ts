/**
 * 前端内建错误码段位（对齐平台；`19xxx` 为前端保留子段）。
 *
 * 段位对齐平台：参数 / 未登记 / 冲突 / 限流 / 权限；前端保留自有子段 `19xxx`。
 * 不自造段位、不复用平台已发布码。`BaseError` 本体（`mechanisms/error.ts`）由 `02_05` 落地，
 * 直接引用本常量；文案映射走 i18n `error.{code}`（《命名规范》「前端命名」节）。
 */

/** 前端内建错误码（骨架集；扩充走《命名规范》段位登记）。 */
export const ErrorCodes = {
  /** 能力声明 / 依赖校验违规（参数段位）。 */
  CAPABILITY_VIOLATION: 10001,
  /** 未注册不可用（扩展点未登记）。 */
  PROVIDER_NOT_REGISTERED: 10002,
  /** 注册表唯一性冲突（冲突段位）。 */
  REGISTRY_CONFLICT: 10003,
  /** 限流。 */
  RATE_LIMITED: 10005,
  /** 权限不足。 */
  PERMISSION_DENIED: 30001,
  /** 未实现（前端保留子段 `19xxx`）。 */
  NOT_IMPLEMENTED: 19001,
} as const

/** 前端内建错误码取值类型。 */
export type ErrorCode = (typeof ErrorCodes)[keyof typeof ErrorCodes]

/** 前端保留子段（`19000` ~ `19999`）。 */
export const FRONTEND_RESERVED_SEGMENT = [19000, 19999] as const

/** 判断错误码是否落前端保留子段。 */
export function isFrontendReservedCode(code: number): boolean {
  return code >= FRONTEND_RESERVED_SEGMENT[0] && code <= FRONTEND_RESERVED_SEGMENT[1]
}
