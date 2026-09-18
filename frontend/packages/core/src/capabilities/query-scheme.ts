/**
 * 查询方案组件基类（查询方案族）：条件模型 / 方案保存·应用 / 参数化。
 */

import { BasePersistedState } from './persisted-state'

/** 查询条件。 */
export interface QueryCondition {
  /** 字段。 */
  field: string
  /** 运算符。 */
  operator: string
  /** 值。 */
  value: unknown
}

/** 查询方案。 */
export interface QueryScheme {
  /** 方案名。 */
  name: string
  /** 条件清单。 */
  conditions: QueryCondition[]
}

/** 查询方案组件基类（抽象）。 */
export abstract class BaseQueryScheme extends BasePersistedState {
  /** 能力键（组件基类身份）。 */
  override readonly identifier: string = 'query-scheme'
  /** 已保存方案。 */
  readonly schemes: QueryScheme[] = []
  /** 当前应用方案名。 */
  activeScheme: string | undefined

  /**
   * 保存方案（同名覆盖）。
   *
   * @param scheme 方案。
   */
  saveScheme(scheme: QueryScheme): void {
    const index = this.schemes.findIndex((entry) => entry.name === scheme.name)
    const stored: QueryScheme = { name: scheme.name, conditions: scheme.conditions.map((item) => ({ ...item })) }
    if (index >= 0) {
      this.schemes[index] = stored
    } else {
      this.schemes.push(stored)
    }
    this.setLocal([...this.schemes])
  }

  /**
   * 应用方案（返回条件副本）。
   *
   * @param name 方案名。
   */
  applyScheme(name: string): QueryCondition[] | undefined {
    const scheme = this.schemes.find((entry) => entry.name === name)
    if (scheme === undefined) {
      return undefined
    }
    this.activeScheme = name
    return scheme.conditions.map((item) => ({ ...item }))
  }
}
