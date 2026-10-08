/**
 * 权限配置元数据装配：把 platform 契约的菜单 / 表单 / 字段 / 按钮 / 动作元数据映射为
 * 授权编排所需的内核元数据（`PermissionMetadata`）；菜单元数据落 platform 平台库（`/menus` 等）。
 *
 * 数据权限字典类型清单缺后端列表端点（当前仅 `GET /dicts/{dict_type}`），`dictTypes` 暂为空（遗留后端补端点）；
 * 扩展权限注册清单本期为空注册（未注册即隐藏扩展子页签）。
 */

import type { ActionMeta, FieldMeta, FormMeta, PermissionMenuNode, PermissionMetadata } from '@bms/core'
import type { platform } from '@bms/api-types'

import { get } from './request'

type Schemas = platform.components['schemas']

/** 菜单节点契约（维护视图，树形嵌套）。 */
type MenuItemSchema = Schemas['MenuItem']
/** 表单行契约。 */
type FormItemSchema = Schemas['FormItem']
/** 字段行契约。 */
type FieldItemSchema = Schemas['FieldItem']
/** 按钮行契约。 */
type ButtonItemSchema = Schemas['ButtonItem']
/** 动作行契约。 */
type ActionItemSchema = Schemas['ActionItem']

/**
 * 菜单节点 → 内核菜单节点（仅菜单入口）。
 *
 * @param item 契约菜单节点。
 */
function toMenuNode(item: MenuItemSchema): PermissionMenuNode {
  return {
    id: String(item.id),
    name: item.name,
    icon: item.icon ?? undefined,
    children: (item.children ?? []).map(toMenuNode),
  }
}

/**
 * 装配授权元数据（并行取菜单 / 表单 / 字段 / 按钮 / 动作）。
 *
 * @returns 内核元数据。
 */
export async function fetchPermissionMetadata(): Promise<PermissionMetadata> {
  const [menus, forms, fields, buttons, actions] = await Promise.all([
    get<Schemas['MenuTree']>('platform', '/menus'),
    get<Schemas['FormList']>('platform', '/forms'),
    get<Schemas['FieldList']>('platform', '/fields'),
    get<Schemas['ButtonList']>('platform', '/buttons'),
    get<Schemas['ActionList']>('platform', '/actions'),
  ])

  const formActions: Record<string, string[]> = {}
  for (const button of (buttons.items ?? []) as ButtonItemSchema[]) {
    const formId = String(button.form_id)
    const list = formActions[formId] ?? []
    if (!list.includes(String(button.action_id))) {
      list.push(String(button.action_id))
    }
    formActions[formId] = list
  }

  const formFields: Record<string, string[]> = {}
  for (const field of (fields.items ?? []) as FieldItemSchema[]) {
    const formId = String(field.form_id)
    const list = formFields[formId] ?? []
    list.push(String(field.id))
    formFields[formId] = list
  }

  const formMetas: FormMeta[] = ((forms.items ?? []) as FormItemSchema[]).map((form) => ({
    id: String(form.id),
    name: form.component ?? `表单 ${form.id}`,
    menuIds: (form.menu_ids ?? []).map((id) => String(id)),
  }))

  const fieldMetas: FieldMeta[] = ((fields.items ?? []) as FieldItemSchema[]).map((field) => ({
    id: String(field.id),
    name: field.name,
  }))

  const actionMetas: ActionMeta[] = ((actions.items ?? []) as ActionItemSchema[]).map((action) => ({
    id: String(action.id),
    name: action.name,
  }))

  return {
    menus: ((menus.items ?? []) as MenuItemSchema[]).map(toMenuNode),
    forms: formMetas,
    actions: actionMetas,
    fields: fieldMetas,
    formActions,
    formFields,
    dictTypes: [],
    extensions: [],
  }
}
