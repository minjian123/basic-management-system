/**
 * 注册表基座：提供者登记 / 解析的公共实现（对齐后端 `BaseProviderRegistry`）。
 *
 * 语义：同键**唯一性拒重**、`get` 未命中返回 `undefined`（不替各域裁决兜底）、
 * `keys` / `values` 保序、`snapshot` 只读快照。各扩展点注册表一律基于本基座扩展。
 */

import { BaseCapability } from './capability'
import { BaseError } from './error'
import { ErrorCodes } from './error-codes'
import { BasePluggable } from './pluggable'

/** 提供者注册表基座（抽象）。 */
export abstract class BaseProviderRegistry<T> extends BasePluggable {
  private readonly providers = new Map<string, T>()

  /** 注册项键（各域注册表覆写）。 */
  protected abstract providerKey(provider: T): string

  /**
   * 登记提供者（同键拒重，不静默覆盖）。
   *
   * @param provider 注册项。
   * @throws BaseError 键已登记（`REGISTRY_CONFLICT`）。
   */
  register(provider: T): void {
    const key = this.providerKey(provider)
    if (this.providers.has(key)) {
      throw new BaseError(ErrorCodes.REGISTRY_CONFLICT, `${this.pluginKey} 重复登记：${key}`)
    }
    this.providers.set(key, provider)
  }

  /** 按 key 取提供者（未命中返回 `undefined`）。 */
  get(key: string): T | undefined {
    return this.providers.get(key)
  }

  /** 已登记键（登记顺序）。 */
  keys(): string[] {
    return [...this.providers.keys()]
  }

  /** 已登记提供者（登记顺序）。 */
  values(): T[] {
    return [...this.providers.values()]
  }

  /** 只读快照。 */
  snapshot(): ReadonlyMap<string, T> {
    return new Map(this.providers)
  }
}

/** 能力注册表（缺省实现，注册项为能力基类）。 */
export class CapabilityRegistry extends BaseProviderRegistry<BaseCapability> {
  readonly pluginKey = 'capability-registry'
  readonly pluginName = 'core'

  protected providerKey(provider: BaseCapability): string {
    return provider.key
  }
}
