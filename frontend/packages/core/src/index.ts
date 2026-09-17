/**
 * @bms/core：前端框架无关核心（纯 TS；不得依赖 Vue / UI 库 / 插件 / 宿主）。
 */

export { BaseFrontend, silentLogger, emptyConfig, type FrontendLogger, type FrontendConfigReader, type FrontendBaseOptions, type LogLevel } from './base/BaseFrontend'
export {
  BaseComponent,
  RESERVED_ATTR_KEYS,
  type ComponentBaseOptions,
  type SizeLevel,
  type DensityLevel,
  type MechanismRegistry,
} from './base/BaseComponent'
export { BaseError, ErrorCodes, type BaseErrorOptions } from './mechanisms/error'
export {
  BaseCapability,
  registerKnownCapabilities,
  knownCapabilitiesView,
  resetKnownCapabilities,
  type CapabilityOptions,
} from './mechanisms/capability'
export { BaseRegistry, type RegistryItemLike, type RegisterOptions } from './mechanisms/registry'
export { BasePlaceholder, type PlaceholderOptions, type PlaceholderReason, type PlaceholderFallback } from './mechanisms/placeholder'
export { BaseAsyncResource, type ResourceDisposer } from './mechanisms/resource'
export { BaseSubscription, nullSubscriptionBus, type SubscriptionBus, type SubscriptionHandler } from './mechanisms/subscription'
export { ProviderRegistry, getProvider, requireProvider } from './providers'
export { observable, type Observable, type MutableObservable } from './base/observable'
export * from './capabilities'
export * from './contracts'
export {
  computeVirtualRange,
  type VirtualRangeInput,
  type VirtualRangeResult,
  type VirtualScrollMetrics,
} from './domain/virtual-range'
export {
  createMemoryScrollStorage,
  createScrollPositionStore,
  createSessionScrollStorage,
  defaultScrollStorage,
  type ScrollMetrics,
  type ScrollPositionStore,
  type ScrollStorage,
} from './domain/scroll-position'
export { resolveSize } from './domain/size'
export {
  createInputContext,
  type InputContext,
  type InputContextOptions,
  type InputMode,
  type ReadonlyMode,
} from './domain/input'
export {
  defaultPasswordStrengthRules,
  evaluatePasswordStrength,
  type PasswordStrengthLevel,
  type PasswordStrengthMissing,
  type PasswordStrengthResult,
  type PasswordStrengthRules,
} from './domain/password'
export {
  applyPrecision,
  clampNumber,
  formatNumber,
  inNumberRange,
  parseFormattedNumber,
  parseNumberInput,
  type NumberParseOptions,
  type NumberParseResult,
} from './domain/number'
export {
  filterOptions,
  groupOptions,
  isOptionSelectable,
  labelOfOption,
  normalizeOptionValue,
  orderOptionValues,
  reachMaxCount,
} from './domain/option'
export { normalizeBooleanValue } from './domain/boolean'
export { createConfirmService, type ConfirmService } from './domain/confirm-service'
export { createPermissionGate, type PermissionGate } from './domain/permission-gate'
export { createMenuSourceService, type MenuSourceService } from './domain/menu-source-service'
export { createViewResolverService, type ViewResolverService } from './domain/view-resolver-service'
