/**
 * 字段族基础契约套件自验（`11_03` 新增四件的契约面）。
 *
 * 套件本身在 `testing/field-input.ts` 冻结；本用例以**最小驱动器**跑通套件全部断言，
 * 真实件（`TimeField` / `PercentField` / `OptionSetMultiField` / `TriStateSwitch`）在 `ui-ep` 侧
 * 以同一套件驱动（同契约多实现）。
 */

import {
  FIELD_EMPTY_PLACEHOLDER,
  describeMultiValueFieldContract,
  describeSingleValueFieldContract,
  type MultiValueContractTarget,
  type SingleValueContractTarget,
} from '@bms/core/testing'
import { describe, expect, it } from 'vitest'

/** 最小单值驱动器（模拟时间 / 百分比 / 三态开关的共同面）。 */
function singleDriver<T>(placeholder = FIELD_EMPTY_PLACEHOLDER): SingleValueContractTarget<T> {
  let current: T | undefined
  return {
    get value(): T | undefined {
      return current
    },
    get isEmpty(): boolean {
      return current === undefined
    },
    setValue: (next) => {
      current = next
    },
    errorText: '',
    get displayText(): string {
      return current === undefined ? placeholder : String(current)
    },
  }
}

/** 最小多值驱动器（模拟枚举多选）。 */
function multiDriver<T>(): MultiValueContractTarget<T> {
  let current: T[] = []
  return {
    get value(): T[] {
      return current
    },
    get isEmpty(): boolean {
      return current.length === 0
    },
    setValue: (next) => {
      current = next ?? []
    },
    errorText: '',
    get displayText(): string {
      return current.length === 0 ? FIELD_EMPTY_PLACEHOLDER : current.map(String).join('、')
    },
  }
}

describeSingleValueFieldContract<number>('字段族基础契约：单值（最小驱动器）', () => singleDriver<number>(), 42)

describeMultiValueFieldContract<string>(
  '字段族基础契约：多值（最小驱动器）',
  () => multiDriver<string>(),
  ['a', 'b'],
)

describe('字段族基础契约套件自验', () => {
  it('单值驱动器：设值 / 清空 / 占位', () => {
    const target = singleDriver<string>()
    expect(target.displayText).toBe(FIELD_EMPTY_PLACEHOLDER)
    target.setValue('12:30')
    expect(target.value).toBe('12:30')
    expect(target.displayText).toBe('12:30')
    target.setValue(undefined)
    expect(target.isEmpty).toBe(true)
  })

  it('多值驱动器：顿号拼接与空态占位', () => {
    const target = multiDriver<string>()
    target.setValue(['高', '中'])
    expect(target.displayText).toBe('高、中')
    target.setValue([])
    expect(target.displayText).toBe(FIELD_EMPTY_PLACEHOLDER)
    expect(target.isEmpty).toBe(true)
  })

  it('占位常量与展示域统一口径', () => {
    expect(FIELD_EMPTY_PLACEHOLDER).toBe('—')
  })
})
