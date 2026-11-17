/**
 * 领域纯函数：列表页查询区派生（布局查询字段 → 查询字段声明）。
 *
 * 查询区字段由布局 `query.fields` 决定顺序，是否可查由字段类型与状态决定（类型白名单见
 * `FORM_QUERY_TYPES`；停用 / 待建列 / 建列失败不计入）。派生产物直接喂既有查询筛选件
 * （`FilterField[]`），折叠阈值与控件映射复用筛选件常量，本模块不重复定义。
 *
 * 框架无关、不触 DOM、不请求，同输入同输出。
 */

import { normalizeFieldRefs, type FormLayout, type FormLayoutInput } from './form-layout'
import { normalizeField, type FormFieldInput } from './form-render'
import type { FilterField, FilterFieldType, FilterOption } from './filter'
import type { OptionSetSnapshot } from './option-set'

/** 可进入查询区的字段类型（文件 / 字典 / 富文本 / 多语言名不进查询区）。 */
export const FORM_QUERY_TYPES: readonly string[] = [
  'text',
  'longtext',
  'number',
  'datetime',
  'option',
  'option_multi',
  'switch',
]

/** 表单字段类型 → 查询字段类型（`longtext` 落文本域，其余同名）。 */
const QUERY_FIELD_TYPE_BY_FORM_TYPE: Readonly<Record<string, FilterFieldType>> = {
  text: 'text',
  longtext: 'textarea',
  number: 'number',
  datetime: 'datetime',
  option: 'option',
  option_multi: 'option_multi',
  switch: 'switch',
}

/** 查询区派生入参。 */
export interface FormQuerySource {
  /** 生效布局（缺省或未配置查询区即返回空清单）。 */
  layout?: FormLayout | FormLayoutInput | undefined
  /** 合并字段清单（可缺省项由归一补确定值）。 */
  fields?: readonly FormFieldInput[] | undefined
  /** 选项集快照集（枚举条件的候选项来源；缺失即空选项）。 */
  optionSets?: readonly OptionSetSnapshot[] | undefined
}

/**
 * 取选项集快照条目并转查询候选项。
 *
 * @param optionSets 选项集快照集。
 * @param optionSetKey 选项集标识。
 * @returns 查询候选项（无快照返回空数组）。
 */
function toFilterOptions(
  optionSets: readonly OptionSetSnapshot[],
  optionSetKey: string | undefined,
): FilterOption[] {
  if (optionSetKey === undefined) {
    return []
  }
  const snapshot = optionSets.find((item) => item.optionSetKey === optionSetKey)
  if (snapshot === undefined) {
    return []
  }
  return snapshot.items.map((item) => ({ label: item.label, value: item.value }))
}

/**
 * 由生效布局派生列表页查询字段声明。
 *
 * 规则：顺序取 `layout.query.fields`（归一去重保序）；清单中不存在 / 停用 / 建列失败 / 类型不在
 * 白名单的字段跳过；枚举字段的候选项取 `optionSets` 快照（快照缺失即空选项，不阻断查询）。
 *
 * @param source 派生入参（布局 + 字段清单 + 选项集快照）。
 * @returns 查询字段声明（插入序；空配置返回空数组）。
 */
export function formQueryFields(source: FormQuerySource): FilterField[] {
  const keys = normalizeFieldRefs(source.layout?.query?.fields ?? []).map((ref) => ref.key)
  if (keys.length === 0) {
    return []
  }
  const fields = (source.fields ?? []).map((field, index) => normalizeField(field, index))
  const byKey = new Map(fields.map((field) => [field.key, field]))
  const optionSets = source.optionSets ?? []
  const result: FilterField[] = []
  for (const key of keys) {
    const field = byKey.get(key)
    if (field === undefined) {
      continue
    }
    if (field.disabled === true || (field.status !== undefined && field.status !== 'active')) {
      continue
    }
    if (!FORM_QUERY_TYPES.includes(field.type)) {
      continue
    }
    const type = QUERY_FIELD_TYPE_BY_FORM_TYPE[field.type]
    if (type === undefined) {
      continue
    }
    const item: FilterField = { key: field.key, label: field.label, type, query: true }
    if (type === 'option' || type === 'option_multi') {
      item.options = toFilterOptions(optionSets, field.optionSetKey)
    }
    if (field.placeholder !== undefined) {
      item.placeholder = field.placeholder
    }
    if (field.defaultValue !== undefined) {
      item.defaultValue = field.defaultValue
    }
    result.push(item)
  }
  return result
}
