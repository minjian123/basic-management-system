/**
 * 表单定制端点封装：`/api/v1/form-design/*` 与 `/api/v1/forms/{form_code}/*`（10_02）。
 *
 * 三处转换集中在本模块（唯一入口）：生效字段属性**展平**、选项集快照键转 camelCase、
 * 三层布局行与层内属性行**归并**为设计器输入的 `FormLayoutLevels` 与属性表；页面只消费
 * `@bms/core` 的布局模型与 `@bms/ui_ep` 的件契约。服务段寻址与统一解包由宿主请求层承担。
 */

import type { FieldRenderAttrs, FormLayout, FormLayoutLevels, LayoutEffective } from '@bms/core'
import type { platform } from '@bms/api_types'

import { del, get, post, put } from './request'

type Schemas = platform.components['schemas']

/** 布局 / 属性清单响应。 */
export type LayoutList = Schemas['LayoutListResponse']
/** 层级布局行。 */
export type LayoutLevelRow = Schemas['LayoutLevelRow']
/** 层级字段属性行。 */
export type FieldAttrRow = Schemas['FieldAttrRow']
/** 布局保存请求 / 结果。 */
export type LayoutSaveRequest = Schemas['LayoutSaveRequest']
export type LayoutSaveResult = Schemas['LayoutSaveResult']
/** 属性保存请求项 / 请求。 */
export type FieldAttrItem = Schemas['FieldAttrItem']
export type FieldAttrSaveRequest = Schemas['FieldAttrSaveRequest']
/** 自建字段项 / 清单 / 新建 / 编辑。 */
export type ExtFieldItem = Schemas['ExtFieldItem']
export type ExtFieldList = Schemas['ExtFieldListResponse']
export type ExtFieldCreateRequest = Schemas['ExtFieldCreateRequest']
export type ExtFieldUpdateRequest = Schemas['ExtFieldUpdateRequest']
/** 生效布局响应 / 动态校验。 */
export type LayoutEffectiveResponse = Schemas['LayoutEffectiveResponse']
export type FormValidateResponse = Schemas['FormValidateResponse']

/** 设计层级（与后端 `scope` 同值）。 */
export type DesignScope = 'platform' | 'tenant' | 'role'

/** 层内属性表（字段键 → 属性补丁）。 */
export type LayerAttrs = Record<string, FieldRenderAttrs>

/**
 * 生效字段属性展平：`attrs` 内既有 camelCase 键原样上提（后端 `dump_attrs` 同口径）。
 *
 * @param field 生效字段（`attrs` 嵌套）。
 * @returns 展平后的字段（并入字段清单用）。
 */
export function flattenEffectiveField(field: Schemas['EffectiveField']): {
  key: string
  label: string
  type: string
  group: string
  sort: number
  status: string
  disabled: boolean
  attrs: FieldRenderAttrs
} {
  const attrs = (field.attrs ?? {}) as FieldRenderAttrs
  return {
    key: field.key,
    label: field.label,
    type: field.type,
    group: field.group,
    sort: field.sort,
    status: field.status,
    disabled: field.disabled,
    attrs,
  }
}

/**
 * 生效布局响应 → 前端 `LayoutEffective`（选项集键转 camelCase）。
 *
 * @param response 契约响应。
 * @returns 生效布局（渲染器与设计器画布同源）。
 */
export function toEffectiveLayout(response: LayoutEffectiveResponse): LayoutEffective {
  const fields = (response.fields ?? []).map((field) => {
    const flat = flattenEffectiveField(field)
    return {
      key: flat.key,
      label: flat.label,
      type: flat.type,
      group: flat.group === 'tenant' ? ('tenant' as const) : ('platform' as const),
      status: flat.status as LayoutEffective['fields'][number]['status'],
      disabled: flat.disabled,
      ...flat.attrs,
    }
  })
  const optionSets = (response.option_sets ?? []).map((snapshot) => ({
    optionSetKey: snapshot.option_set_key,
    items: (snapshot.items ?? []).map((item) => {
      // `value` / `label` 按字符串直出（契约必填；`String()` 兜住生成类型未收窄为 `str` 的情形）；
      // 其余项为可选，按下发有无归一。
      const resolved: { value: string; label: string; color?: string; disabled?: boolean; sort?: number } = {
        value: String(item.value),
        label: String(item.label),
      }
      if (typeof item.color === 'string' && item.color !== '') {
        resolved.color = item.color
      }
      if (item.disabled === true) {
        resolved.disabled = true
      }
      if (typeof item.sort === 'number') {
        resolved.sort = item.sort
      }
      return resolved
    }),
  }))
  const permissions: Record<string, { visible?: boolean; editable?: boolean }> = {}
  for (const [key, value] of Object.entries(response.permissions ?? {})) {
    permissions[key] = { visible: value.visible, editable: value.editable }
  }
  return {
    layout: response.layout as unknown as FormLayout,
    fields,
    level: 'tenant',
    source: response.source as LayoutEffective['source'],
    readonly: response.readonly,
    fallback: response.fallback,
    optionSets,
    permissions,
  }
}

/**
 * 三层布局行 → 设计器输入的层级布局（`role` 层按所选角色取一份）。
 *
 * @param rows 布局行清单。
 * @param roleId 所选角色（角色视图；缺省不设 `role` 层）。
 * @returns 三级层级布局。
 */
export function toLevels(rows: readonly LayoutLevelRow[], roleId?: string): FormLayoutLevels {
  const levels: FormLayoutLevels = {}
  for (const row of rows) {
    if (row.scope === 'platform') {
      levels.platform = row.layout_config as unknown as FormLayout
    } else if (row.scope === 'tenant') {
      levels.tenant = row.layout_config as unknown as FormLayout
    } else if (row.scope === 'role' && roleId !== undefined && row.role_id === roleId) {
      levels.role = row.layout_config as unknown as FormLayout
    }
  }
  return levels
}

/**
 * 层内属性行归并（同一 `scope` + `role_id` 的行合并为属性表）。
 *
 * @param rows 属性行清单。
 * @param scope 层级。
 * @param roleId 角色（非角色层级传 `0`）。
 * @returns 字段键 → 属性。
 */
export function toLayerAttrs(rows: readonly FieldAttrRow[], scope: DesignScope, roleId = '0'): LayerAttrs {
  const result: LayerAttrs = {}
  for (const row of rows) {
    if (row.scope !== scope) {
      continue
    }
    if (scope === 'role' ? row.role_id !== roleId : row.role_id !== '0') {
      continue
    }
    result[row.field_key] = (row.attrs ?? {}) as FieldRenderAttrs
  }
  return result
}

/**
 * 取该表单的三层布局 + 三层属性。
 *
 * @param formCode 表单标识（业务码）。
 */
export function listLayouts(formCode: string): Promise<LayoutList> {
  return get<LayoutList>('platform', '/form-design/layouts', { form_code: formCode })
}

/**
 * 保存某层级布局（整份覆盖）。
 *
 * @param payload 保存请求。
 */
export function saveLayout(payload: LayoutSaveRequest): Promise<LayoutSaveResult> {
  return put<LayoutSaveResult>('platform', '/form-design/layouts', payload)
}

/**
 * 删除某层级布局（恢复默认：回退下一级）。
 *
 * @param layoutId 布局主键。
 */
export function deleteLayout(layoutId: string): Promise<LayoutSaveResult> {
  return del<LayoutSaveResult>('platform', `/form-design/layouts/${layoutId}`)
}

/**
 * 保存某层级字段属性（整份覆盖；空清单即清空该层）。
 *
 * @param payload 保存请求。
 */
export function saveAttrs(payload: FieldAttrSaveRequest): Promise<LayoutSaveResult> {
  return put<LayoutSaveResult>('platform', '/form-design/attrs', payload)
}

/**
 * 删除某层级的全部属性（恢复默认）。
 *
 * @param attrId 属性主键。
 */
export function deleteAttrs(attrId: string): Promise<LayoutSaveResult> {
  return del<LayoutSaveResult>('platform', `/form-design/attrs/${attrId}`)
}

/**
 * 自建字段清单（含 `ddl_status` / `status`）。
 *
 * @param formCode 表单标识。
 */
export function listExtFields(formCode: string): Promise<ExtFieldList> {
  return get<ExtFieldList>('platform', '/form-design/fields', { form_code: formCode })
}

/**
 * 新建自建字段（触发动态建列）。
 *
 * @param payload 新建请求。
 */
export function createExtField(payload: ExtFieldCreateRequest): Promise<ExtFieldItem> {
  return post<ExtFieldItem>('platform', '/form-design/fields', payload)
}

/**
 * 编辑 / 停用自建字段（停用不删列）。
 *
 * @param fieldId 字段主键。
 * @param payload 编辑请求。
 */
export function updateExtField(fieldId: string, payload: ExtFieldUpdateRequest): Promise<ExtFieldItem> {
  return put<ExtFieldItem>('platform', `/form-design/fields/${fieldId}`, payload)
}

/**
 * 建列失败重试（复用同一元数据与列名）。
 *
 * @param fieldId 字段主键。
 */
export function retryExtField(fieldId: string): Promise<ExtFieldItem> {
  return post<ExtFieldItem>('platform', `/form-design/fields/${fieldId}/retry`)
}

/**
 * 当前用户生效布局（渲染路径）。
 *
 * @param formCode 表单标识。
 */
export function getEffectiveLayout(formCode: string): Promise<LayoutEffectiveResponse> {
  return get<LayoutEffectiveResponse>('platform', `/forms/${encodeURIComponent(formCode)}/layout-effective`)
}

/**
 * 动态校验自测（与业务接口同源）。
 *
 * @param formCode 表单标识。
 * @param values 字段键 → 待校验值。
 */
export function validateForm(formCode: string, values: Record<string, unknown>): Promise<FormValidateResponse> {
  return post<FormValidateResponse>('platform', `/forms/${encodeURIComponent(formCode)}/validate`, { values })
}
