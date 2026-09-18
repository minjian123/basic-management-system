/**
 * `@bms/core`：前端框架无关核心运行时入口。
 *
 * 纯 TS，不依赖 Vue / UI 库 / 插件 / 宿主（护栏 `tests/guard-core-framework-agnostic.spec.ts`）。
 * 基类与能力导出随 `02_01` ~ `02_06` 就位后在本入口追加。
 */

export {
  BaseObject,
  configureBase,
  getBaseSinks,
  resetBaseSinks,
  type BaseConfigSource,
  type BaseLoggerSink,
  type BaseReporterSink,
  type BaseSinks,
  type LogLevel,
} from './base/BaseObject'
export { withBaseObject, type BaseObjectSurface } from './base/mixin'
export {
  BaseComponent,
  type ComponentProps,
  type DensityToken,
  type LifecycleEvent,
  type LifecycleListener,
  type LifecyclePayload,
  type SizeToken,
} from './base/BaseComponent'

export {
  ErrorCodes,
  FRONTEND_RESERVED_SEGMENT,
  isFrontendReservedCode,
  type ErrorCode,
} from './mechanisms/error-codes'
export { BaseCapability } from './mechanisms/capability'
export { BasePluggable, DEFAULT_CONTRACT_VERSION } from './mechanisms/pluggable'
export { BaseError, type BaseErrorOptions } from './mechanisms/error'
export { BaseProviderRegistry, CapabilityRegistry } from './mechanisms/registry'
export { BaseProvider } from './mechanisms/provider'
export { BaseFactory } from './mechanisms/factory'
export { BaseAsyncResource, type Disposable } from './mechanisms/resource'
export { BaseSubscription } from './mechanisms/subscription'
export {
  BaseNullObject,
  BasePlaceholder,
  BaseStub,
  type PlaceholderReason,
} from './mechanisms/placeholder'

export { BaseApi, type HttpMethod } from './contracts/api'
export { BaseDataObject } from './contracts/data-object'
export { BaseEntity } from './contracts/entity'
export { BasePageQuery, type SortOrder } from './contracts/page-query'
export { stableStringify } from './domain/serialize'
