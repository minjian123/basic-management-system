/**
 * @bms/core：前端框架无关核心（纯 TS；不得依赖 Vue / UI 库 / 插件 / 宿主）。
 */

export { BaseFrontend, silentLogger, emptyConfig, type FrontendLogger, type FrontendConfigReader, type FrontendBaseOptions, type LogLevel } from './base/BaseFrontend'
export { BaseComponent, type ComponentBaseOptions, type SizeLevel, type DensityLevel } from './base/BaseComponent'
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
export type { CapabilityDescriptor, RenderBinding } from './contracts'
