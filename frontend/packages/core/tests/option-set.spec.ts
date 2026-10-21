// kiwi_id: 2337
/** 选项集领域纯函数与解析器契约自验（06_10）。 */
import { describe, expect, it } from 'vitest'

import {
  OPTION_EMPTY_TEXT,
  OPTION_MULTI_SEPARATOR,
  OPTION_SET_DROPDOWN_THRESHOLD,
  buildOptionSetIndex,
  isOptionSetFieldType,
  missingOptionValues,
  optionLabelOf,
  optionLabelsOf,
  resolveOptionSetItems,
  suggestOptionWidget,
} from '../src'
import type { OptionSetItem } from '../src'
import {
  OPTION_SET_CONTRACT_SNAPSHOTS,
  OPTION_SET_CONTRACT_TRANSLATE,
  describeOptionSetResolverContract,
} from '../testing'

describe('选项集解析', () => {
  it('sort 升序 → 同 value 去重保留首个 → 空值剔除', () => {
    const items: OptionSetItem[] = [
      { value: 'c', label: '丙', sort: 3 },
      { value: 'a', label: '甲', sort: 1 },
      { value: 'a', label: '甲重复', sort: 2 },
      { value: 'b', label: '乙', sort: 2 },
      { value: '', label: '空值' },
    ]
    const resolved = resolveOptionSetItems(items)
    expect(resolved.map((item) => item.value)).toEqual(['a', 'b', 'c'])
    expect(resolved.map((item) => item.label)).toEqual(['甲', '乙', '丙'])
    expect(resolved.map((item) => item.sort)).toEqual([1, 2, 3])
  })

  it('i18n：labelKey 命中翻译、缺翻译 / 空翻译 / 未注入回退 label，label 仍空回退 value', () => {
    const translated = resolveOptionSetItems(
      [
        { value: 'mid', label: '中', labelKey: 'option.mid', sort: 1 },
        { value: 'high', label: '高', labelKey: 'option.high', sort: 2 },
        { value: 'low', label: '', labelKey: 'option.low', sort: 3 },
        { value: 'none', label: '', sort: 4 },
      ],
      {
        translate: (labelKey) =>
          labelKey === 'option.mid' ? '中（译）' : labelKey === 'option.high' ? '' : undefined,
      },
    )
    expect(translated.map((item) => item.label)).toEqual(['中（译）', '高', 'low', 'none'])

    const fallback = resolveOptionSetItems([{ value: 'mid', label: '中', labelKey: 'option.mid' }])
    expect(fallback[0]?.label).toBe('中')
  })

  it('颜色与禁用保留、未设置项不产出多余字段', () => {
    const [item] = resolveOptionSetItems([{ value: 'a', label: '甲', color: 'danger', disabled: true }])
    expect(item).toEqual({ value: 'a', label: '甲', sort: 0, color: 'danger', disabled: true })
    const [plain] = resolveOptionSetItems([{ value: 'b', label: '乙', color: '', labelKey: '' }])
    expect(plain).toEqual({ value: 'b', label: '乙', sort: 0 })
  })

  it('快照集索引：同 key 保留首个、空 key 与非对象项跳过', () => {
    const index = buildOptionSetIndex([
      { optionSetKey: 'bms.demo.level', items: [{ value: 'b', label: '乙', sort: 2 }, { value: 'a', label: '甲', sort: 1 }] },
      { optionSetKey: 'bms.demo.level', items: [{ value: 'z', label: '重复' }] },
      { optionSetKey: '', items: [{ value: 'x', label: '空' }] },
      null as never,
    ])
    expect(Object.keys(index)).toEqual(['bms.demo.level'])
    expect(index['bms.demo.level']?.map((item) => item.value)).toEqual(['a', 'b'])
    expect(buildOptionSetIndex(undefined)).toEqual({})
  })

  it('脏条目降级：未下发清单 / 非字符串值 / 缺 sort', () => {
    expect(resolveOptionSetItems(undefined)).toEqual([])
    const resolved = resolveOptionSetItems([
      { value: 1 as never, label: '数字值' },
      { value: 'b', label: '乙' },
      { value: null as never, label: '空值' },
    ])
    expect(resolved.map((item) => item.value)).toEqual(['1', 'b'])
    expect(resolved.map((item) => item.sort)).toEqual([0, 0])
  })
})

describe('选项集回显与缺项', () => {
  const items = resolveOptionSetItems([
    { value: 'low', label: '低', sort: 1 },
    { value: 'mid', label: '中', sort: 2 },
    { value: 'high', label: '高', sort: 3 },
  ])

  it('单值取 label，未命中返回 undefined（调用方回退原值）', () => {
    expect(optionLabelOf(items, 'mid')).toBe('中')
    expect(optionLabelOf(items, 'ghost')).toBeUndefined()
  })

  it('多选按选项集顺序、顿号分隔、缺项按输入顺序回退原值、重复值去重', () => {
    expect(optionLabelsOf(items, ['high', 'low', 'low'])).toBe('低、高')
    expect(optionLabelsOf(items, ['ghost', 'low'])).toBe('低、ghost')
    expect(optionLabelsOf(items, ['high', 'ghost', 'ghost'])).toBe('高、ghost')
    expect(optionLabelsOf(items, [])).toBe('')
    expect(OPTION_MULTI_SEPARATOR).toBe('、')
    expect(OPTION_EMPTY_TEXT).toBe('—')
  })

  it('缺项清单去重保序', () => {
    expect(missingOptionValues(items, ['ghost', 'low', 'ghost', 'phantom'])).toEqual(['ghost', 'phantom'])
    expect(missingOptionValues(items, ['low'])).toEqual([])
  })
})

describe('建议形态与类型判定', () => {
  it('选项数超过 8 建议下拉（单选 dropdown / 多选 dropdown-multi）', () => {
    expect(OPTION_SET_DROPDOWN_THRESHOLD).toBe(8)
    expect(suggestOptionWidget('option', 8)).toBeUndefined()
    expect(suggestOptionWidget('option', 9)).toBe('dropdown')
    expect(suggestOptionWidget('option_multi', 9)).toBe('dropdown-multi')
    expect(suggestOptionWidget('text', 9)).toBeUndefined()
  })

  it('选项集字段类型判定', () => {
    expect(isOptionSetFieldType('option')).toBe(true)
    expect(isOptionSetFieldType('option_multi')).toBe(true)
    expect(isOptionSetFieldType('dict')).toBe(false)
  })
})

describeOptionSetResolverContract('选项集解析器契约（核心快照索引）', () => ({
  resolve: (optionSetKey) =>
    buildOptionSetIndex(OPTION_SET_CONTRACT_SNAPSHOTS, { translate: OPTION_SET_CONTRACT_TRANSLATE })[optionSetKey],
}))
