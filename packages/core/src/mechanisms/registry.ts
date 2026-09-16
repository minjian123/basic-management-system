/**
 * 注册表基座（框架无关核心，对齐后端 `BaseProviderRegistry`）：
 * 唯一性拒重（严格域抛错 / 一般域告警保留首个）、`get` 未命中 `undefined`（不替各域裁决）、
 * 保序（`keys` / `values`）、只读快照（`snapshot`，数量取 `count`）。
 */

import { BaseError, ErrorCodes } from './error'

export interface RegistryItemLike {
  readonly key: string
  describe(): Record<string, unknown>
}

export interface RegisterOptions {
  /** 严格域：冲突抛 `BaseError(10003)`（默认告警并保留首个） */
  strict?: boolean
  /** 冲突告警回调 */
  onWarn?: (message: string) => void
}

export class BaseRegistry<T extends RegistryItemLike = RegistryItemLike> {
  private readonly items = new Map<string, T>()

  register(item: T, options: RegisterOptions = {}): void {
    const existing = this.items.get(item.key)
    if (existing) {
      const message = `注册项「${item.key}」重复登记（保留首个）`
      if (options.strict) {
        throw new BaseError(ErrorCodes.REGISTRY_CONFLICT, message)
      }
      options.onWarn?.(message)
      return
    }
    this.items.set(item.key, item)
  }

  get(key: string): T | undefined {
    return this.items.get(key)
  }

  /** 已注册 key（插入序） */
  keys(): string[] {
    return [...this.items.keys()]
  }

  values(): T[] {
    return [...this.items.values()]
  }

  /** 只读快照（浅拷贝） */
  snapshot(): Readonly<Record<string, T>> {
    return Object.freeze(Object.fromEntries(this.items))
  }

  get count(): number {
    return this.items.size
  }
}
