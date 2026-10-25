/**
 * 菜单元数据端点封装：`/api/v1/menus`、`/forms`、`/buttons`、`/fields`（平台维护视图）。
 *
 * 服务段寻址与统一解包由宿主请求层承担（不手拼服务前缀）；响应类型取 `@bms/api_types`
 * 的 `platform` 命名空间（契约生成类型，禁止手写漂移）。
 *
 * ID 口径：契约响应把雪花 ID 统一**字符串化**输出，请求侧按数值字符串提交（后端宽松模式
 * 解析为 `int`），与 `api/role.ts` 的 `SnowflakeId` 同口径。
 */

import type { platform } from '@bms/api_types'

import { del, get, post, put } from './request'

type Schemas = platform.components['schemas']

/** 雪花 ID 传输形态（字符串，避免超出 JS 安全整数）。 */
export type SnowflakeId = string

/** 启用状态。 */
export type MetaStatus = 'enabled' | 'disabled'

/** 多语言名称映射（locale → 文案）。 */
export type I18nNames = Record<string, string>

/** 菜单节点（平台维护视图，树形嵌套）。 */
export type MenuItem = Schemas['MenuItem']
/** 菜单树。 */
export type MenuTree = Schemas['MenuTree']
/** 表单行（菜单入口多对多）。 */
export type FormItem = Schemas['FormItem']
/** 表单清单。 */
export type FormList = Schemas['FormList']
/** 按钮行。 */
export type ButtonItem = Schemas['ButtonItem']
/** 按钮清单。 */
export type ButtonList = Schemas['ButtonList']
/** 字段行。 */
export type FieldItem = Schemas['FieldItem']
/** 字段清单。 */
export type FieldList = Schemas['FieldList']

/** 菜单新增 / 更新载荷（整体替换语义）。 */
export interface MenuPayload {
  /** 父菜单 ID（`0` 为根）。 */
  parent_id: SnowflakeId
  /** 前端路由路径。 */
  path: string
  /** 视图组件标识（空 = 目录节点）。 */
  component: string | null
  /** 完整 icon key。 */
  icon: string | null
  /** 同级排序。 */
  sort: number
  /** 仅隐藏侧栏入口。 */
  hidden: boolean
  /** 状态。 */
  status: MetaStatus
  /** 多语言名称。 */
  i18n: I18nNames
}

/** 表单新增 / 更新载荷（菜单入口全量替换）。 */
export interface FormPayload {
  /** 关联菜单入口 ID 清单（全量；空 = 无入口表单）。 */
  menu_ids: SnowflakeId[]
  /** 所属业务码 ID。 */
  business_id: SnowflakeId
  /** 视图组件标识。 */
  component: string | null
  /** 状态。 */
  status: MetaStatus
}

/** 按钮新增 / 更新载荷。 */
export interface ButtonPayload {
  /** 所属表单 ID（更新时不提交）。 */
  form_id?: SnowflakeId
  /** 挂接权限码 ID。 */
  permission_id: SnowflakeId
  /** 按钮名。 */
  name: string
  /** 按钮形态。 */
  type: 'toolbar' | 'interface'
  /** 同表内排序。 */
  sort: number
  /** 状态。 */
  status: MetaStatus
}

/** 字段新增 / 更新载荷。 */
export interface FieldPayload {
  /** 所属表单 ID（更新时不提交）。 */
  form_id?: SnowflakeId
  /** 字段键（表单内唯一；更新时不提交）。 */
  field_key?: string
  /** 字段类型。 */
  type: string
  /** 同表内排序。 */
  sort: number
  /** 状态。 */
  status: MetaStatus
  /** 多语言名称。 */
  i18n: I18nNames
}

/**
 * 取菜单树（平台维护视图，含 hidden / disabled；一次返回不分页）。
 *
 * @returns 菜单树。
 */
export function listMenus(): Promise<MenuTree> {
  return get<MenuTree>('platform', '/menus')
}

/**
 * 新增菜单。
 *
 * @param payload 新增载荷。
 * @returns 新建菜单行。
 */
export function createMenu(payload: MenuPayload): Promise<MenuItem> {
  return post<MenuItem>('platform', '/menus', payload)
}

/**
 * 更新菜单（整体替换）。
 *
 * @param id 菜单主键。
 * @param payload 更新载荷。
 * @returns 更新后的菜单行。
 */
export function updateMenu(id: SnowflakeId, payload: MenuPayload): Promise<MenuItem> {
  return put<MenuItem>('platform', `/menus/${id}`, payload)
}

/**
 * 删除菜单（软删除；被引用时后端拒绝 `40206`）。
 *
 * @param id 菜单主键。
 */
export function deleteMenu(id: SnowflakeId): Promise<null> {
  return del<null>('platform', `/menus/${id}`)
}

/**
 * 取表单清单（含未挂接任何菜单入口的表单）。
 *
 * @param menuId 菜单入口 ID（可选；非空时按关联过滤）。
 * @returns 表单清单。
 */
export function listForms(menuId?: SnowflakeId): Promise<FormList> {
  return get<FormList>('platform', '/forms', menuId === undefined ? undefined : { menu_id: menuId })
}

/**
 * 新增表单。
 *
 * @param payload 新增载荷。
 * @returns 新建表单行。
 */
export function createForm(payload: FormPayload): Promise<FormItem> {
  return post<FormItem>('platform', '/forms', payload)
}

/**
 * 更新表单（菜单入口全量替换）。
 *
 * @param id 表单主键。
 * @param payload 更新载荷。
 * @returns 更新后的表单行。
 */
export function updateForm(id: SnowflakeId, payload: FormPayload): Promise<FormItem> {
  return put<FormItem>('platform', `/forms/${id}`, payload)
}

/**
 * 删除表单（软删除；被引用时后端拒绝 `40206`）。
 *
 * @param id 表单主键。
 */
export function deleteForm(id: SnowflakeId): Promise<null> {
  return del<null>('platform', `/forms/${id}`)
}

/**
 * 取按钮清单（可按表单过滤）。
 *
 * @param formId 表单主键（可选）。
 * @returns 按钮清单。
 */
export function listButtons(formId?: SnowflakeId): Promise<ButtonList> {
  return get<ButtonList>('platform', '/buttons', formId === undefined ? undefined : { form_id: formId })
}

/**
 * 新增按钮。
 *
 * @param payload 新增载荷（含 `form_id`）。
 * @returns 新建按钮行。
 */
export function createButton(payload: ButtonPayload): Promise<ButtonItem> {
  return post<ButtonItem>('platform', '/buttons', payload)
}

/**
 * 更新按钮。
 *
 * @param id 按钮主键。
 * @param payload 更新载荷。
 * @returns 更新后的按钮行。
 */
export function updateButton(id: SnowflakeId, payload: ButtonPayload): Promise<ButtonItem> {
  return put<ButtonItem>('platform', `/buttons/${id}`, payload)
}

/**
 * 删除按钮（软删除）。
 *
 * @param id 按钮主键。
 */
export function deleteButton(id: SnowflakeId): Promise<null> {
  return del<null>('platform', `/buttons/${id}`)
}

/**
 * 取字段清单（可按表单过滤）。
 *
 * @param formId 表单主键（可选）。
 * @returns 字段清单。
 */
export function listFields(formId?: SnowflakeId): Promise<FieldList> {
  return get<FieldList>('platform', '/fields', formId === undefined ? undefined : { form_id: formId })
}

/**
 * 新增字段。
 *
 * @param payload 新增载荷（含 `form_id` / `field_key`）。
 * @returns 新建字段行。
 */
export function createField(payload: FieldPayload): Promise<FieldItem> {
  return post<FieldItem>('platform', '/fields', payload)
}

/**
 * 更新字段。
 *
 * @param id 字段主键。
 * @param payload 更新载荷。
 * @returns 更新后的字段行。
 */
export function updateField(id: SnowflakeId, payload: FieldPayload): Promise<FieldItem> {
  return put<FieldItem>('platform', `/fields/${id}`, payload)
}

/**
 * 删除字段（软删除）。
 *
 * @param id 字段主键。
 */
export function deleteField(id: SnowflakeId): Promise<null> {
  return del<null>('platform', `/fields/${id}`)
}
