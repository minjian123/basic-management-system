/**
 * 查询方案组件基类（查询方案族）：条件模型 / 方案保存·应用 / 参数化 / 三级作用域。
 *
 * 当前条件为**取数唯一来源**；条件序列化与失效剔除委托领域纯函数（`domain/filter.ts`），
 * 方案远端读写由使用方注入处理函数（**未注入即仅本地**，不发请求）。
 */

import { BasePersistedState } from './persisted-state'

import {
  QUERY_SCHEME_TARGET_BUSINESS,
  buildQueryParams,
  hasSchemeName,
  isConditionActive,
  normalizeConditions,
  normalizeSchemes,
  pruneConditions,
  resolveDefaultScheme,
  type FilterCondition,
  type FilterField,
  type QuerySchemeEntry,
  type QuerySchemeScope,
} from '../domain/filter'

/** 查询条件（与筛选契约同形；保留既有导出名）。 */
export type QueryCondition = FilterCondition

/** 查询方案（基类内态；除方案名与条件外均为可选）。 */
export interface QueryScheme {
  /** 方案标识。 */
  id?: string
  /** 方案名。 */
  name: string
  /** 作用域（缺省 `user`）。 */
  scope?: QuerySchemeScope
  /** 条件清单。 */
  conditions: QueryCondition[]
  /** 是否默认方案。 */
  isDefault?: boolean
  /** 是否共享。 */
  shared?: boolean
  /** 归属用户标识。 */
  ownerId?: string
}

/** 查询方案组件基类（抽象）。 */
export abstract class BaseQueryScheme extends BasePersistedState {
  /** 能力键（组件基类身份）。 */
  override readonly identifier: string = 'query-scheme'
  /** 当前条件（取数唯一来源）。 */
  readonly conditions: FilterCondition[] = []
  /** 当前关键字。 */
  keyword = ''
  /** 默认条件种子（重置回此）。 */
  readonly defaults: FilterCondition[] = []
  /** 已保存方案。 */
  readonly schemes: QueryScheme[] = []
  /** 当前应用方案名。 */
  activeScheme: string | undefined

  /** 默认方案（三级优先级取最高且标记默认者）。 */
  get defaultScheme(): QueryScheme | undefined {
    return this.resolveDefault()
  }

  /**
   * 设置默认条件种子并写入当前条件。
   *
   * @param conditions 条件种子。
   */
  setDefaults(conditions: readonly FilterCondition[]): void {
    this.defaults.length = 0
    this.defaults.push(...conditions.map((item) => ({ ...item })))
    this.setConditions(this.defaults)
  }

  /**
   * 设置当前条件（脏值剔除）。
   *
   * @param conditions 条件清单。
   */
  setConditions(conditions: readonly FilterCondition[]): void {
    this.conditions.length = 0
    this.conditions.push(...normalizeConditions(conditions))
    if (!this.isDisposed) {
      this.notifyLifecycle('update')
    }
  }

  /**
   * 设置关键字。
   *
   * @param value 关键字。
   */
  setKeyword(value: string): void {
    if (value === this.keyword) {
      return
    }
    this.keyword = value
    if (!this.isDisposed) {
      this.notifyLifecycle('update')
    }
  }

  /** 重置条件（回默认条件种子并清关键字）。 */
  resetConditions(): void {
    this.keyword = ''
    this.setConditions(this.defaults)
  }

  /** 参与请求的条件（剔空）。 */
  activeConditions(): FilterCondition[] {
    return this.conditions.filter((condition) => isConditionActive(condition))
  }

  /** 取数查询参数（条件 + 关键字）。 */
  queryParams(): Record<string, unknown> {
    return buildQueryParams(this.conditions, this.keyword)
  }

  /**
   * 失效条件剔除（字段不存在 / 非查询类 / 选项失效）。
   *
   * @param fields 查询类字段清单。
   * @returns 剔除数量。
   */
  prune(fields: readonly FilterField[]): number {
    const result = pruneConditions(this.conditions, fields)
    if (result.removed > 0) {
      this.setConditions(result.conditions)
    }
    return result.removed
  }

  /**
   * 整体回写方案清单（远端 / 偏好归一形态）。
   *
   * @param schemes 方案条目。
   */
  setSchemes(schemes: readonly QuerySchemeEntry[]): void {
    this.schemes.length = 0
    this.schemes.push(
      ...schemes.map((scheme) => ({
        id: scheme.id,
        name: scheme.name,
        scope: scheme.scope,
        conditions: scheme.conditions.map((item) => ({ ...item })),
        isDefault: scheme.isDefault,
        shared: scheme.shared,
        ownerId: scheme.ownerId,
      })),
    )
    this.setLocal([...this.schemes])
  }

  /**
   * 从原始值归一方案清单。
   *
   * @param value 原始值。
   */
  normalizeSchemes(value: unknown): void {
    this.setSchemes(normalizeSchemes(value))
  }

  /**
   * 保存方案（同名覆盖）。
   *
   * @param scheme 方案。
   */
  saveScheme(scheme: QueryScheme): void {
    const index = this.schemes.findIndex((entry) => entry.name === scheme.name)
    const stored: QueryScheme = {
      id: scheme.id,
      name: scheme.name,
      scope: scheme.scope ?? 'user',
      conditions: scheme.conditions.map((item) => ({ ...item })),
      isDefault: scheme.isDefault,
      shared: scheme.shared,
      ownerId: scheme.ownerId,
    }
    if (index >= 0) {
      this.schemes[index] = stored
    } else {
      this.schemes.push(stored)
    }
    this.setLocal([...this.schemes])
  }

  /**
   * 应用方案（返回条件副本并写入当前条件）。
   *
   * @param name 方案名。
   */
  applyScheme(name: string): FilterCondition[] | undefined {
    const scheme = this.schemes.find((entry) => entry.name === name)
    if (scheme === undefined) {
      return undefined
    }
    this.activeScheme = name
    const conditions = scheme.conditions.map((item) => ({ ...item }))
    this.setConditions(conditions)
    return conditions
  }

  /**
   * 删除方案。
   *
   * @param name 方案名。
   * @returns 是否删除。
   */
  removeScheme(name: string): boolean {
    const index = this.schemes.findIndex((entry) => entry.name === name)
    if (index < 0) {
      return false
    }
    this.schemes.splice(index, 1)
    if (this.activeScheme === name) {
      this.activeScheme = undefined
    }
    this.setLocal([...this.schemes])
    return true
  }

  /**
   * 重命名方案。
   *
   * @param oldName 原名。
   * @param newName 新名。
   * @returns 是否重命名（原方案不存在或新名冲突返回假）。
   */
  renameScheme(oldName: string, newName: string): boolean {
    const target = newName.trim()
    if (target === '' || target === oldName || hasSchemeName(this.entries(), target)) {
      return false
    }
    const scheme = this.schemes.find((entry) => entry.name === oldName)
    if (scheme === undefined) {
      return false
    }
    scheme.name = target
    if (this.activeScheme === oldName) {
      this.activeScheme = target
    }
    this.setLocal([...this.schemes])
    return true
  }

  /**
   * 设默认方案（传 `undefined` 清除全部默认标记）。
   *
   * @param name 方案名。
   */
  setDefaultScheme(name: string | undefined): void {
    for (const scheme of this.schemes) {
      scheme.isDefault = name !== undefined && scheme.name === name
    }
    this.setLocal([...this.schemes])
  }

  /**
   * 按作用域筛方案。
   *
   * @param scope 作用域。
   */
  schemesByScope(scope: QuerySchemeScope): QueryScheme[] {
    return this.schemes.filter((scheme) => (scheme.scope ?? 'user') === scope)
  }

  /** 解析默认方案（三级优先级）。 */
  resolveDefault(): QueryScheme | undefined {
    const hit = resolveDefaultScheme(this.entries())
    return hit === undefined ? undefined : this.schemes.find((scheme) => scheme.name === hit.name)
  }

  /**
   * 方案条目视图（契约形态）。
   *
   * @returns 方案条目清单。
   */
  private entries(): QuerySchemeEntry[] {
    return this.schemes.map((scheme) => ({
      id: scheme.id,
      name: scheme.name,
      scope: scheme.scope ?? 'user',
      target: QUERY_SCHEME_TARGET_BUSINESS,
      conditions: scheme.conditions,
      isDefault: scheme.isDefault === true,
      shared: scheme.shared === true,
      ownerId: scheme.ownerId,
    }))
  }
}
