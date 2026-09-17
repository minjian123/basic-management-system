/**
 * 能力注册表与提供者（框架无关核心）：能力经登记在册后可用，**不注册不可用**。
 *
 * - `registerCapability`：登记能力（key 唯一；冲突默认告警保留首个，`strict` 抛 `BaseError(10003)`）；
 * - `createCapability(key, options)`：按登记创建实例（未注册抛 `BaseError(10002)`）；
 * - 登记项含 `create` 工厂，能力实现可替换（对齐后端插件注册表语义）。
 */

import { BaseError, ErrorCodes } from '../mechanisms/error'
import type { BaseCapability, CapabilityOptions } from '../mechanisms/capability'
import { ProviderRegistry } from '../providers'
import type { CapabilityDescriptor } from '../contracts'

export interface CapabilityRegistration<T extends BaseCapability = BaseCapability>
  extends CapabilityDescriptor {
  create: (options: CapabilityOptions) => T
}

/** 能力注册表（单例：核心运行时实例；测试可 `resetCapabilityRegistry()`） */
export class CapabilityRegistry extends ProviderRegistry<CapabilityRegistration> {
  /** 按 key 创建实例（不注册不可用；`options` 为各能力自有形状，注册表作动态装配点） */
  create<T extends BaseCapability = BaseCapability>(key: string, options: object = {}): T {
    const registration = this.get(key)
    if (!registration) {
      throw new BaseError(ErrorCodes.PROVIDER_NOT_REGISTERED, `能力「${key}」未注册（不注册不可用）`)
    }
    return registration.create({ ...options, key } as CapabilityOptions) as T
  }
}

export const capabilityRegistry = new CapabilityRegistry()

export function registerCapability(registration: CapabilityRegistration): void {
  capabilityRegistry.register(registration)
}

export function createCapability<T extends BaseCapability = BaseCapability>(
  key: string,
  options: object = {},
): T {
  return capabilityRegistry.create<T>(key, options)
}
