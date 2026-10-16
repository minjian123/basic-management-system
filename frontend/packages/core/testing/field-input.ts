/**
 * 字段族基础契约（`@bms/core/testing`）。
 *
 * 面向 `11_03` 新增的四件（`TimeField` / `PercentField` / `EnumMultiField` / `TriStateSwitch`）：
 * 四件均为**纯前端字段件**（无后端数据源依赖），契约面为「受控值 + 空态 + 校验 + 只读回显」，
 * 故本套件按「值语义 + 校验语义 + 只读语义」三段冻结，各端（PC `ui-ep` / 移动端 / 自定义件）
 * 传入驱动器跑同一套断言（《AI开发规范》架构铁律「两轨汇入同一体系 + 同一套契约测试」）。
 */

import { describe, expect, it } from 'vitest'

/** 字段族基础契约面（四件共同面）。 */
export interface FieldInputContractTarget<T> {
  /** 当前值（未设置返回 `undefined`）。 */
  readonly value: T | undefined
  /** 是否空态（未设置）。 */
  readonly isEmpty: boolean
  /** 设置值（受控入口）。 */
  setValue(value: T | undefined): void
  /** 当前校验错误文案（合法为空串）。 */
  readonly errorText: string
  /** 当前只读回显文本（未设置按占位）。 */
  readonly displayText: string
}

/** 单值字段契约面（时间 / 百分比 / 三态开关）。 */
export type SingleValueContractTarget<T> = FieldInputContractTarget<T>

/** 多值字段契约面（枚举多选）。 */
export type MultiValueContractTarget<T> = FieldInputContractTarget<T[]>

/** 空值占位（与展示域基类统一口径）。 */
export const FIELD_EMPTY_PLACEHOLDER = '—'

/**
 * 单值字段基础契约（时间 / 百分比 / 三态开关）。
 *
 * 断言：受控设值 → 值可读；清空 → 空态且只读回显占位；必填校验由具体件用例覆盖。
 *
 * @param name 契约名。
 * @param create 目标工厂。
 * @param sample 样例值（非空）。
 */
export function describeSingleValueFieldContract<T>(
  name: string,
  create: () => SingleValueContractTarget<T>,
  sample: T,
): void {
  describe(name, () => {
    it('受控设值后值可读且非空态', () => {
      const target = create()
      target.setValue(sample)
      expect(target.value).toEqual(sample)
      expect(target.isEmpty).toBe(false)
    })

    it('清空后回到空态且只读回显占位', () => {
      const target = create()
      target.setValue(sample)
      target.setValue(undefined)
      expect(target.value).toBeUndefined()
      expect(target.isEmpty).toBe(true)
      expect(target.displayText).toBe(FIELD_EMPTY_PLACEHOLDER)
    })

    it('空值不产生校验错误（必填独立判定）', () => {
      const target = create()
      target.setValue(undefined)
      expect(target.errorText).toBe('')
    })
  })
}

/**
 * 多值字段基础契约（枚举多选）。
 *
 * 断言：受控设值（数组）→ 值可读；清空 → 空态（空数组归一到空态）且只读回显占位。
 *
 * @param name 契约名。
 * @param create 目标工厂。
 * @param sample 样例值（非空数组）。
 */
export function describeMultiValueFieldContract<T>(
  name: string,
  create: () => MultiValueContractTarget<T>,
  sample: T[],
): void {
  describe(name, () => {
    it('受控设值后值可读且非空态', () => {
      const target = create()
      target.setValue(sample)
      expect(target.value).toEqual(sample)
      expect(target.isEmpty).toBe(false)
    })

    it('清空（空数组 / 未设置）后回到空态且只读回显占位', () => {
      const target = create()
      target.setValue(sample)
      target.setValue([])
      expect(target.isEmpty).toBe(true)
      expect(target.displayText).toBe(FIELD_EMPTY_PLACEHOLDER)
    })

    it('空值不产生校验错误（必填独立判定）', () => {
      const target = create()
      target.setValue([])
      expect(target.errorText).toBe('')
    })
  })
}
