/**
 * 选项域纯函数（框架无关核心）：下拉 / 单选 / 复选 / 字典 / 枚举共用。
 *
 * 统一「无效值剔除 / 去重保序 / 文本解析 / 分组 / 多选上限」口径，双端实现只做展示。
 */

import type { OptionGroup, OptionItem, OptionValue } from '../contracts/option'

/** 多选值去重并按 **选项顺序** 保序（与勾选顺序无关） */
export function orderOptionValues(value: readonly OptionValue[], options: readonly OptionItem[]): OptionValue[] {
  const order = new Map<OptionValue, number>()
  for (const item of options) {
    if (!order.has(item.value)) {
      order.set(item.value, order.size)
    }
  }
  return [...new Set(value)].sort(
    (a, b) =>
      (order.get(a) ?? Number.MAX_SAFE_INTEGER) - (order.get(b) ?? Number.MAX_SAFE_INTEGER),
  )
}

/**
 * 归一受控值：剔除不在选项集内的值。
 *
 * 单选：无有效值 → `null`；多选：无效值剔除 + 去重保序（空 → `[]`）。
 */
export function normalizeOptionValue(
  value: OptionValue | readonly OptionValue[] | null | undefined,
  options: readonly OptionItem[],
  multiple: boolean,
): OptionValue | OptionValue[] | null {
  const known = new Set(options.map((item) => item.value))
  if (multiple) {
    const list = Array.isArray(value)
      ? (value as readonly OptionValue[])
      : value === null || value === undefined
        ? []
        : [value as OptionValue]
    return orderOptionValues(
      list.filter((item) => known.has(item)),
      options,
    )
  }
  if (Array.isArray(value)) {
    return value.find((item) => known.has(item)) ?? null
  }
  if (value === null || value === undefined) {
    return null
  }
  return known.has(value as OptionValue) ? (value as OptionValue) : null
}

/** 取选项文本（未命中回退 `String(value)`；多值按「、」拼接，空值 → `''`） */
export function labelOfOption(
  value: OptionValue | readonly OptionValue[] | null | undefined,
  options: readonly OptionItem[],
): string {
  if (Array.isArray(value)) {
    const known = value.filter((item) => options.some((option) => option.value === item))
    return orderOptionValues(known as readonly OptionValue[], options)
      .map((item) => labelOfOption(item, options))
      .filter((text) => text !== '')
      .join('、')
  }
  if (value === null || value === undefined) {
    return ''
  }
  const hit = options.find((item) => item.value === value)
  return hit ? hit.label : String(value)
}

/** 分组视图（同组连续排列，顺序保持 `options` 出现顺序；无分组项归 `''`） */
export function groupOptions(options: readonly OptionItem[]): OptionGroup[] {
  const groups: OptionGroup[] = []
  let current: { group: string; items: OptionItem[] } | null = null
  for (const item of options) {
    const group = item.group ?? ''
    if (!current || current.group !== group) {
      current = { group, items: [] }
      groups.push(current)
    }
    current.items.push(item)
  }
  return groups
}

/** 是否已达多选上限（`maxCount` 缺省或 ≤ 0 视为不限制） */
export function reachMaxCount(value: readonly OptionValue[], maxCount?: number): boolean {
  if (maxCount === undefined || maxCount <= 0) {
    return false
  }
  return value.length >= maxCount
}

/** 选项是否可选中（禁用项不可选；达上限时未选中项不可选、已选中项可取消） */
export function isOptionSelectable(
  item: OptionItem,
  value: readonly OptionValue[],
  maxCount?: number,
): boolean {
  if (item.disabled === true) {
    return false
  }
  if (value.includes(item.value)) {
    return true
  }
  return !reachMaxCount(value, maxCount)
}

/** 本地过滤（按 `label` 包含匹配，大小写不敏感） */
export function filterOptions(options: readonly OptionItem[], keyword: string): readonly OptionItem[] {
  const text = keyword.trim().toLowerCase()
  if (text === '') {
    return options
  }
  return options.filter((item) => item.label.toLowerCase().includes(text))
}
