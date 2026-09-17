/**
 * 提供者（框架无关核心）：能力实现经注册表登记，业务与组件只经 `getXxx()` 提供者取用。
 *
 * 两档口径（对齐后端提供者语义）：
 * - `getProvider`：未命中返回 `undefined`（不替各域裁决兜底）；
 * - `requireProvider`：**不注册不可用**——未命中抛 `BaseError(10002)`（扩展点强制）。
 */

import { BaseError, ErrorCodes } from '../mechanisms/error'
import { BaseRegistry, type RegistryItemLike } from '../mechanisms/registry'

export class ProviderRegistry<T extends RegistryItemLike = RegistryItemLike> extends BaseRegistry<T> {}

export function getProvider<T extends RegistryItemLike>(
  registry: ProviderRegistry<T>,
  key: string,
): T | undefined {
  return registry.get(key)
}

export function requireProvider<T extends RegistryItemLike>(
  registry: ProviderRegistry<T>,
  key: string,
): T {
  const provider = registry.get(key)
  if (!provider) {
    throw new BaseError(ErrorCodes.PROVIDER_NOT_REGISTERED, `扩展点「${key}」未注册（不注册不可用）`)
  }
  return provider
}
