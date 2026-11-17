/**
 * 设计器页的模型归并（10_02）：生效字段 + 自建字段 → 设计器字段清单；层内属性 → 保存请求项。
 *
 * 纯函数、无 IO：页面只做取数与状态编排，字段派生、键派生与属性清洗在此集中（便于单测）。
 */

import type { FieldRenderAttrs, FormField } from '@bms/core'
import type { FieldAttrsPatch } from '@bms/ui_ep'

import type { ExtFieldItem, FieldAttrItem, LayoutEffectiveResponse } from '@/api/formDesign'

/** 自建字段键最大长度（后端限制 60，留出前缀余量）。 */
const MAX_FIELD_KEY_LENGTH = 60

/**
 * 由英文名称派生字段键（驼峰转蛇形 → 小写 → 仅留字母数字下划线 → 合并下划线 → 去首尾下划线）。
 *
 * 后端要求 `^[a-z][a-z0-9_]{0,59}$`；派生不出合法键时返回空串（调用方据此拒收并要求补英文名）。
 *
 * @param nameEn 英文名称。
 * @returns 字段键（非法为空串）。
 */
export function extFieldKey(nameEn: string): string {
  const key = nameEn
    .replace(/([a-z0-9])([A-Z])/g, '$1_$2')
    .replace(/[\s.-]+/g, '_')
    .toLowerCase()
    .replace(/[^a-z0-9_]/g, '')
    .replace(/_+/g, '_')
    .replace(/^_+|_+$/g, '')
    .slice(0, MAX_FIELD_KEY_LENGTH)
  return /^[a-z][a-z0-9_]*$/.test(key) ? key : ''
}

/**
 * 自建字段行 → 设计器字段项（分组 `tenant`；停用 / 待建列 / 建列失败不可拖入）。
 *
 * @param item 自建字段行。
 * @returns 设计器字段。
 */
export function toTenantField(item: ExtFieldItem): FormField {
  const usable = item.status === 'enabled' && item.ddl_status === 'active'
  return {
    key: item.field_key,
    label: item.name,
    type: item.type,
    group: 'tenant',
    status: item.status === 'disabled' ? 'disabled' : (item.ddl_status as FormField['status']),
    ...(usable ? {} : { disabled: true }),
  }
}

/**
 * 生效布局响应 + 自建字段清单 → 设计器字段清单（平台在前、租户在后，各自按 `sort` 升序、同序按键升序）。
 *
 * @param response 生效布局响应（平台字段来源）。
 * @param extItems 自建字段清单。
 * @returns 合并字段清单。
 */
export function designerFields(response: LayoutEffectiveResponse, extItems: readonly ExtFieldItem[]): FormField[] {
  const platform = (response.fields ?? [])
    .filter((field) => field.group !== 'tenant')
    .map((field) => ({ sort: field.sort, field }))
    .sort((left, right) => left.sort - right.sort || left.field.key.localeCompare(right.field.key))
    .map(({ field }) => {
      const attrs = (field.attrs ?? {}) as FieldRenderAttrs
      const item: FormField = {
        key: field.key,
        label: field.label,
        type: field.type,
        group: 'platform',
        status: field.status as FormField['status'],
        ...attrs,
      }
      if (field.disabled) {
        item.disabled = true
      }
      return item
    })
  const tenant = [...extItems]
    .sort((left, right) => left.sort - right.sort || left.field_key.localeCompare(right.field_key))
    .map((item) => toTenantField(item))
  return [...platform, ...tenant]
}

/**
 * 层内属性 → 属性面板初值。
 *
 * @param attrs 层内属性（缺省空对象）。
 * @returns 面板补丁（只带已配置项）。
 */
export function toAttrDraft(attrs: FieldRenderAttrs | undefined): FieldAttrsPatch {
  if (attrs === undefined) {
    return {}
  }
  const draft: FieldAttrsPatch = {}
  if (attrs.required === true) {
    draft.required = true
  }
  if (typeof attrs.placeholder === 'string' && attrs.placeholder !== '') {
    draft.placeholder = attrs.placeholder
  }
  if (attrs.defaultValue !== undefined && attrs.defaultValue !== null && attrs.defaultValue !== '') {
    draft.defaultValue = attrs.defaultValue
  }
  if (Array.isArray(attrs.rules) && attrs.rules.length > 0) {
    draft.rules = attrs.rules
  }
  if (typeof attrs.optionSetKey === 'string' && attrs.optionSetKey !== '') {
    draft.optionSetKey = attrs.optionSetKey
  }
  if (typeof attrs.widget === 'string' && attrs.widget !== '') {
    draft.widget = attrs.widget
  }
  if (attrs.readonly === true) {
    draft.readonly = true
  }
  if (attrs.hidden === true) {
    draft.hidden = true
  }
  return draft
}

/**
 * 清洗属性补丁为保存用 `attrs`（丢弃空串 / `undefined` / `false` 与空规则；与后端 `dump_attrs` 同口径）。
 *
 * @param patch 面板补丁。
 * @returns 请求体 `attrs`（无有效项返回空对象）。
 */
export function cleanAttrs(patch: FieldAttrsPatch): Record<string, unknown> {
  const result: Record<string, unknown> = {}
  if (patch.required === true) {
    result.required = true
  }
  if (typeof patch.placeholder === 'string' && patch.placeholder !== '') {
    result.placeholder = patch.placeholder
  }
  if (patch.defaultValue !== undefined && patch.defaultValue !== null && patch.defaultValue !== '') {
    result.defaultValue = patch.defaultValue
  }
  if (Array.isArray(patch.rules) && patch.rules.length > 0) {
    result.rules = patch.rules
  }
  if (typeof patch.optionSetKey === 'string' && patch.optionSetKey !== '') {
    result.optionSetKey = patch.optionSetKey
  }
  if (typeof patch.widget === 'string' && patch.widget !== '') {
    result.widget = patch.widget
  }
  if (patch.readonly === true) {
    result.readonly = true
  }
  if (patch.hidden === true) {
    result.hidden = true
  }
  return result
}

/**
 * 字段清单 + 层内属性 → 属性保存请求项（**只带有非空属性的字段**；空属性的字段落默认值）。
 *
 * @param fields 设计器字段清单。
 * @param drafts 字段键 → 面板补丁。
 * @returns 请求项（插入序）。
 */
export function attrsPayload(fields: readonly FormField[], drafts: Readonly<Record<string, FieldAttrsPatch>>): FieldAttrItem[] {
  const items: FieldAttrItem[] = []
  for (const field of fields) {
    const attrs = cleanAttrs(drafts[field.key] ?? {})
    if (Object.keys(attrs).length === 0) {
      continue
    }
    items.push({ field_key: field.key, field_type: field.type, attrs })
  }
  return items
}

/**
 * 取某层某角色的行主键（恢复默认时定位待删除行）。
 *
 * @param rows 行清单（含 `id` / `scope` / `role_id`）。
 * @param scope 层级。
 * @param roleId 角色（非角色层级传 `0`）。
 * @returns 主键（无行返回空串）。
 */
export function pickRowId(
  rows: readonly { id: string; scope: string; role_id: string }[],
  scope: string,
  roleId = '0',
): string {
  const hit = rows.find((row) => row.scope === scope && row.role_id === roleId)
  return hit?.id ?? ''
}
