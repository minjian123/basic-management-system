/**
 * 权限配置元数据装配：把 platform 契约的菜单 / 表单 / 字段 / 按钮 / 动作元数据映射为
 * 授权编排所需的内核元数据（`PermissionMetadata`）；菜单元数据落 platform 平台库（`/menus` 等）。
 *
 * 数据权限字典清单经 `GET /dicts`（字典数据源登记清单）装配（2026-10-11 02_09）；
 * 扩展权限注册清单本期为空注册（未注册即隐藏扩展子页签）。
 */

import type { ActionMeta, DictKeyMeta, FieldMeta, FormMeta, PermissionMenuNode, PermissionMetadata } from '@bms/core'
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
/** 权限码行契约。 */
type PermissionItemSchema = Schemas['PermissionItem']

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
  const [menus, forms, fields, buttons, permissions] = await Promise.all([
    get<Schemas['MenuTree']>('platform', '/menus'),
    get<Schemas['FormList']>('platform', '/forms'),
    get<Schemas['FieldList']>('platform', '/fields'),
    get<Schemas['ButtonList']>('platform', '/buttons'),
    get<Schemas['PermissionList']>('platform', '/permissions'),
  ])

  const formActions: Record<string, string[]> = {}
  for (const button of (buttons.items ?? []) as ButtonItemSchema[]) {
    const formId = String(button.form_id)
    const list = formActions[formId] ?? []
    if (!list.includes(String(button.permission_id))) {
      list.push(String(button.permission_id))
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

  const actionMetas: ActionMeta[] = ((permissions.items ?? []) as PermissionItemSchema[]).map((permission) => ({
    id: String(permission.id),
    name: permission.code,
  }))

  const dictsRaw = await get<unknown[]>('platform', '/dicts')
  const dictMetas: DictKeyMeta[] = (Array.isArray(dictsRaw) ? dictsRaw : []).flatMap((item) => {
    if (item === null || typeof item !== 'object') {
      return []
    }
    const record = item as Record<string, unknown>
    const key = record.dict_key
    if (typeof key !== 'string' || key === '') {
      return []
    }
    return [{ id: key, code: key, name: typeof record.name === 'string' ? record.name : key }]
  })

  return {
    menus: ((menus.items ?? []) as MenuItemSchema[]).map(toMenuNode),
    forms: formMetas,
    actions: actionMetas,
    fields: fieldMetas,
    formActions,
    formFields,
    dictKeys: dictMetas,
    extensions: [],
  }
}
