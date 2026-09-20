/**
 * 查询方案契约（`@bms/core/testing`）。
 *
 * 查询筛选区（`07_05`）/ 移动端与字典高级查询为「同一契约多实现」，各自在本套件中传入适配器跑同一套断言：
 * 条件序列化逐分支、空条件不传、失效剔除、方案保存·应用·删除·重命名·默认（三级优先级）。
 */

import { describe, expect, it } from 'vitest'

import type { FilterCondition, FilterField, QuerySchemeEntry, QuerySchemeScope } from '../src'

/** 方案（结构化最小面）。 */
export interface QuerySchemeContractScheme {
  /** 方案名。 */
  name: string
  /** 作用域。 */
  scope?: QuerySchemeScope
  /** 条件清单。 */
  conditions: readonly FilterCondition[]
  /** 是否默认。 */
  isDefault?: boolean
}

/** 查询方案契约面（结构化接口）。 */
export interface QuerySchemeContractTarget {
  /** 当前条件。 */
  readonly conditions: readonly FilterCondition[]
  /** 当前关键字。 */
  readonly keyword: string
  /** 已保存方案。 */
  readonly schemes: readonly QuerySchemeContractScheme[]
  /** 当前应用方案名。 */
  readonly activeScheme: string | undefined
  /** 默认方案名。 */
  readonly defaultSchemeName: string | undefined
  /** 设置当前条件。 */
  setConditions(conditions: readonly FilterCondition[]): void
  /** 设置关键字。 */
  setKeyword(value: string): void
  /** 重置条件。 */
  resetConditions(): void
  /** 取数查询参数。 */
  queryParams(): Record<string, unknown>
  /** 失效剔除（返回剔除数）。 */
  prune(fields: readonly FilterField[]): number
  /** 整体回写方案。 */
  setSchemes(schemes: readonly QuerySchemeEntry[]): void
  /** 保存方案。 */
  saveScheme(scheme: QuerySchemeContractScheme): void
  /** 应用方案。 */
  applyScheme(name: string): readonly FilterCondition[] | undefined
  /** 删除方案。 */
  removeScheme(name: string): boolean
  /** 重命名方案。 */
  renameScheme(oldName: string, newName: string): boolean
  /** 设默认方案。 */
  setDefaultScheme(name: string | undefined): void
}

/**
 * 查询方案契约（`07_05` 冻结）。
 *
 * @param name 契约名。
 * @param create 目标工厂。
 */
export function describeQuerySchemeContract(name: string, create: () => QuerySchemeContractTarget): void {
  describe(name, () => {
    it('条件序列化逐分支（等值 / 多值 / 区间 / 空值标记 / 空条件不传）', () => {
      const target = create()
      target.setConditions([
        { field: 'status', operator: 'eq', value: 'enabled' },
        { field: 'tags', operator: 'in', value: ['a', 'b'] },
        { field: 'created', operator: 'between', value: ['2026-09-01', '2026-09-12'] },
        { field: 'phone', operator: 'is_null', value: null },
        { field: 'email', operator: 'is_not_null', value: null },
        { field: 'name', operator: 'like', value: '' },
      ])
      expect(target.queryParams()).toEqual({
        status: 'enabled',
        tags: 'a,b',
        created_start: '2026-09-01',
        created_end: '2026-09-12',
        phone_is_null: '1',
        email_is_not_null: '1',
      })

      target.setKeyword('张')
      expect(target.queryParams()).toMatchObject({ keyword: '张' })
    })

    it('关键字与重置', () => {
      const target = create()
      target.setKeyword('张')
      expect(target.keyword).toBe('张')
      target.setConditions([{ field: 'status', operator: 'eq', value: 'enabled' }])
      target.resetConditions()
      expect(target.keyword).toBe('')
      expect(target.conditions).toEqual([])
      expect(target.queryParams()).toEqual({})
    })

    it('失效剔除（字段缺失 / 非查询类）', () => {
      const target = create()
      target.setConditions([
        { field: 'gone', operator: 'eq', value: 1 },
        { field: 'status', operator: 'eq', value: 'enabled' },
        { field: 'remark', operator: 'like', value: 'x' },
      ])
      const fields: FilterField[] = [
        { key: 'status', label: '状态', type: 'select' },
        { key: 'remark', label: '备注', type: 'text', query: false },
      ]
      expect(target.prune(fields)).toBe(2)
      expect(target.conditions).toEqual([{ field: 'status', operator: 'eq', value: 'enabled' }])
    })

    it('方案保存·应用·删除·重命名（同名覆盖、条件副本）', () => {
      const target = create()
      target.saveScheme({ name: '默认', conditions: [{ field: 'a', operator: 'eq', value: 1 }] })
      target.saveScheme({ name: '默认', conditions: [{ field: 'b', operator: 'eq', value: 2 }] })
      expect(target.schemes).toHaveLength(1)

      const applied = target.applyScheme('默认') ?? []
      expect(applied).toEqual([{ field: 'b', operator: 'eq', value: 2 }])
      expect(target.activeScheme).toBe('默认')

      const mutated = applied as FilterCondition[]
      mutated[0] = { field: 'b', operator: 'eq', value: 99 }
      expect(target.applyScheme('默认')).toEqual([{ field: 'b', operator: 'eq', value: 2 }])

      expect(target.renameScheme('缺失', 'x')).toBe(false)
      expect(target.renameScheme('默认', '默认')).toBe(false)
      expect(target.renameScheme('默认', '我的')).toBe(true)
      expect(target.activeScheme).toBe('我的')
      expect(target.removeScheme('我的')).toBe(true)
      expect(target.removeScheme('我的')).toBe(false)
      expect(target.applyScheme('缺失')).toBeUndefined()
    })

    it('方案默认与三级优先级（个人 > 租户 > 平台）', () => {
      const target = create()
      target.setSchemes([
        {
          name: '平台默认',
          scope: 'platform',
          target: 'business',
          conditions: [{ field: 'a', operator: 'eq', value: 1 }],
          isDefault: true,
        },
        {
          name: '租户默认',
          scope: 'tenant',
          target: 'business',
          conditions: [{ field: 'b', operator: 'eq', value: 2 }],
          isDefault: true,
        },
      ])
      expect(target.defaultSchemeName).toBe('租户默认')
      expect(target.schemes).toHaveLength(2)

      target.setDefaultScheme('平台默认')
      expect(target.defaultSchemeName).toBe('平台默认')
      expect(target.schemes.find((scheme) => scheme.name === '租户默认')?.isDefault).toBe(false)

      target.setDefaultScheme(undefined)
      expect(target.defaultSchemeName).toBeUndefined()
    })
  })
}
