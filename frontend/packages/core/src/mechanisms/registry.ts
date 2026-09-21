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

/** 同键冲突处置档位：`strict` 抛错 / `lenient` 告警保留首个。 */
export type DuplicatePolicy = 'strict' | 'lenient'

/** 提供者注册表基座（抽象）。 */
export abstract class BaseProviderRegistry<T> extends BasePluggable {
  /** 已登记提供者（保持登记顺序）。 */
  private readonly providers = new Map<string, T>()

  /** 注册项键（各域注册表覆写）。 */
  protected abstract providerKey(provider: T): string

  /** 同键冲突处置档位（缺省 `strict`；子类可覆写为 `lenient`）。 */
  get duplicatePolicy(): DuplicatePolicy {
    return 'strict'
  }

  /**
   * 登记提供者（同键拒重，不静默覆盖；宽和档告警保留首个）。
   *
   * @param provider 注册项。
   * @throws BaseError 键已登记且为严格档（`REGISTRY_CONFLICT`）。
   */
  register(provider: T): void {
    const key = this.providerKey(provider)
    if (this.providers.has(key)) {
      if (this.duplicatePolicy === 'lenient') {
        this.log('warn', `${this.pluginKey} 重复登记（宽和档保留首个）：${key}`)
        return
      }
      throw new BaseError(ErrorCodes.REGISTRY_CONFLICT, `${this.pluginKey} 重复登记：${key}`)
    }
    this.providers.set(key, provider)
  }

  /**
   * 注销提供者（幂等）。
   *
   * @param key 注册项键。
   * @returns 是否命中并移除。
   */
  unregister(key: string): boolean {
    return this.providers.delete(key)
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
  /** 插件键。 */
  readonly pluginKey = 'capability-registry'
  /** 实现名。 */
  readonly pluginName = 'core'

  /** 注册项键取能力键。 */
  protected providerKey(provider: BaseCapability): string {
    return provider.key
  }
}
