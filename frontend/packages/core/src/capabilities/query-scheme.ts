/** 查询方案能力：条件模型 / 方案保存与应用（持久化经 `persisted-state` 对接），依赖 `persisted-state`。 */

import { BaseCapability, type CapabilityOptions } from '../mechanisms/capability'
import { observable } from '../base/observable'

export type QueryCondition = Record<string, unknown>

export interface QueryScheme {
  name: string
  conditions: readonly QueryCondition[]
}

export interface QuerySchemeOptions extends Omit<CapabilityOptions, 'key'> {
  key?: string
}

export class BaseQueryScheme extends BaseCapability {
  readonly conditions = observable<readonly QueryCondition[]>([])
  readonly schemes = observable<readonly QueryScheme[]>([])

  constructor(options: QuerySchemeOptions = {}) {
    super({ ...options, key: options.key ?? 'query-scheme' })
  }

  setConditions(conditions: readonly QueryCondition[]): void {
    this.conditions.set(conditions)
  }

  /** 保存当前条件为方案（同名覆盖） */
  save(name: string): void {
    const scheme: QueryScheme = { name, conditions: [...this.conditions.get()] }
    const list = this.schemes.get().filter((item) => item.name !== name)
    this.schemes.set([...list, scheme])
  }

  apply(name: string): boolean {
    const scheme = this.schemes.get().find((item) => item.name === name)
    if (!scheme) {
      return false
    }
    this.conditions.set([...scheme.conditions])
    return true
  }

  describe(): Record<string, unknown> {
    return { ...super.describe(), schemes: this.schemes.get().length }
  }
}
