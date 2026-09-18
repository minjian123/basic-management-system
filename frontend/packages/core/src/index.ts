/**
 * `@bms/core`：前端框架无关核心运行时入口。
 *
 * 纯 TS，不依赖 Vue / UI 库 / 插件 / 宿主（护栏 `tests/guard-core-framework-agnostic.spec.ts`）。
 * 基类与能力导出随 `02_01` ~ `02_06` 就位后在本入口追加。
 */

export {
  ErrorCodes,
  FRONTEND_RESERVED_SEGMENT,
  isFrontendReservedCode,
  type ErrorCode,
} from './mechanisms/error-codes'
