/**
 * 领域纯函数：选项集（固定值域）解析与回显。
 *
 * 选项集随表单元数据下发（`optionSetKey` + `optionSets` 快照），**运行期只读、不请求**；
 * 本模块只做「已下发条目的解析」——排序、去重、i18n 回退、颜色 / 禁用归一、回显与缺项、
 * 形态建议。注册与冲突判定归后端选项集基座（`02-28`），前端不重复实现。
 *
 * 框架无关、不触 DOM、不请求，同输入同输出。
 */

/** 选项项（契约级最小结构；`value` 是唯一真值来源）。 */
export interface OptionSetItem {
  /** 选项值（常量字符串，被业务数据引用后冻结）。 */
  value: string
  /** 展示文本（当前 locale）。 */
  label: string
  /** i18n key（缺翻译回退 `label`）。 */
  labelKey?: string
  /** 语义色（只读标签用，缺省回退默认色）。 */
  color?: string
  /** 是否不可新增选择（存量值仍可回显）。 */
  disabled?: boolean
  /** 展示顺序（升序；同序保声明顺序）。 */
  sort?: number
}

/** 选项集快照（表单元数据下发；`optionSetKey` → 条目清单）。 */
export interface OptionSetSnapshot {
  /** 选项集标识（点分小写、带命名空间前缀）。 */
  optionSetKey: string
  /** 条目清单（可乱序、可重复）。 */
  items: readonly OptionSetItem[]
}

/** 选项集解析选项（i18n 翻译注入）。 */
export interface OptionSetResolveOptions {
  /** 翻译函数（`labelKey` → 当前 locale 文本；缺翻译 / 空串回退 `label`）。 */
  translate?: (labelKey: string) => string | undefined
}

/** 选项数超过该阈值时建议改用下拉形态。 */
export const OPTION_SET_DROPDOWN_THRESHOLD = 8

/** 空值展示占位（与展示域基类统一口径）。 */
export const OPTION_EMPTY_TEXT = '—'

/** 多选回显分隔符（展示统一顿号）。 */
export const OPTION_MULTI_SEPARATOR = '、'

/** 选项集字段类型（`option` / `option_multi`）。 */
const OPTION_SET_FIELD_TYPES: readonly string[] = ['option', 'option_multi']

/**
 * 是否选项集字段类型。
 *
 * @param fieldType 字段类型。
 */
export function isOptionSetFieldType(fieldType: string): boolean {
  return OPTION_SET_FIELD_TYPES.includes(fieldType)
}

/**
 * 取翻译文本（缺翻译 / 空串返回 `undefined`）。
 *
 * @param labelKey i18n key。
 * @param options 解析选项。
 */
function translateOf(labelKey: string | undefined, options: OptionSetResolveOptions): string | undefined {
  if (labelKey === undefined || labelKey === '' || options.translate === undefined) {
    return undefined
  }
  const text = options.translate(labelKey)
  return typeof text === 'string' && text !== '' ? text : undefined
}

/**
 * 解析选项集（节点 §5）：按 `sort` 升序 → 相同 `value` 去重（保留首个）→ `labelKey` 翻译、
 * 缺翻译回退 `label`、`label` 仍空回退 `value` → 颜色 / 禁用归一。
 *
 * @param items 条目清单（可乱序、可重复、可含空值）。
 * @param options 解析选项（i18n 翻译）。
 */
export function resolveOptionSetItems(
  items: readonly OptionSetItem[] | undefined,
  options: OptionSetResolveOptions = {},
): OptionSetItem[] {
  const sorted = [...(items ?? [])].sort((left, right) => (left.sort ?? 0) - (right.sort ?? 0))
  const seen = new Set<string>()
  const result: OptionSetItem[] = []
  for (const item of sorted) {
    const value = typeof item.value === 'string' ? item.value : String(item.value ?? '')
    if (value === '' || seen.has(value)) {
      continue
    }
    seen.add(value)
    const label = translateOf(item.labelKey, options) ?? (item.label !== '' ? item.label : value)
    const resolved: OptionSetItem = { value, label, sort: item.sort ?? 0 }
    if (item.labelKey !== undefined && item.labelKey !== '') {
      resolved.labelKey = item.labelKey
    }
    if (item.color !== undefined && item.color !== '') {
      resolved.color = item.color
    }
    if (item.disabled === true) {
      resolved.disabled = true
    }
    result.push(resolved)
  }
  return result
}

/**
 * 快照集 → 索引（`optionSetKey` → 解析后条目；同 key 保留首个）。
 *
 * @param sets 快照集（表单元数据下发）。
 * @param options 解析选项（i18n 翻译）。
 */
export function buildOptionSetIndex(
  sets: readonly OptionSetSnapshot[] | undefined,
  options: OptionSetResolveOptions = {},
): Record<string, OptionSetItem[]> {
  const index: Record<string, OptionSetItem[]> = {}
  for (const set of sets ?? []) {
    const key = set?.optionSetKey
    if (typeof key !== 'string' || key === '' || index[key] !== undefined) {
      continue
    }
    index[key] = resolveOptionSetItems(set.items, options)
  }
  return index
}

/**
 * 取单一值的展示文本（未命中返回 `undefined`，由调用方回退原值）。
 *
 * @param items 解析后条目。
 * @param value 受控值。
 */
export function optionLabelOf(items: readonly OptionSetItem[], value: unknown): string | undefined {
  const text = String(value)
  return items.find((item) => item.value === text)?.label
}

/**
 * 多选回显：按选项集顺序取 label、缺项回退原值、`、` 分隔（空数组返回空串）。
 *
 * @param items 解析后条目。
 * @param values 受控值数组。
 */
export function optionLabelsOf(items: readonly OptionSetItem[], values: readonly unknown[]): string {
  if (values.length === 0) {
    return ''
  }
  const wanted = new Set(values.map((value) => String(value)))
  const labels: string[] = []
  for (const item of items) {
    if (wanted.delete(item.value)) {
      labels.push(item.label)
    }
  }
  // 缺项按输入顺序回退原值（不静默丢值）。
  for (const value of values.map((item) => String(item))) {
    if (wanted.delete(value)) {
      labels.push(value)
    }
  }
  return labels.join(OPTION_MULTI_SEPARATOR)
}

/**
 * 缺项清单（值不在选项集内，去重保序）——件层据此告警与打标。
 *
 * @param items 解析后条目。
 * @param values 受控值数组。
 */
export function missingOptionValues(items: readonly OptionSetItem[], values: readonly unknown[]): string[] {
  const known = new Set(items.map((item) => item.value))
  const seen = new Set<string>()
  const result: string[] = []
  for (const value of values.map((item) => String(item))) {
    if (known.has(value) || seen.has(value)) {
      continue
    }
    seen.add(value)
    result.push(value)
  }
  return result
}

/**
 * 建议控件形态（选项数超过 8 建议下拉；仅建议，不改变件形态）。
 *
 * @param fieldType 字段类型（`option` / `option_multi`）。
 * @param count 解析后选项数。
 */
export function suggestOptionWidget(fieldType: string, count: number): 'dropdown' | 'dropdown-multi' | undefined {
  if (count <= OPTION_SET_DROPDOWN_THRESHOLD) {
    return undefined
  }
  if (fieldType === 'option') {
    return 'dropdown'
  }
  if (fieldType === 'option_multi') {
    return 'dropdown-multi'
  }
  return undefined
}
