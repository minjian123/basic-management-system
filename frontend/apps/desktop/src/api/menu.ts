/**
 * 菜单端点封装：动态菜单接口（`GET /api/v1/menus/my`）。
 *
 * 服务段寻址与统一解包由宿主请求层承担（不手拼服务前缀）；响应类型取 `@bms/api-types`
 * 的 `platform` 命名空间（契约生成类型，禁止手写漂移）。
 */

import type { platform } from '@bms/api-types'

import { get } from './request'

/** 动态菜单节点（platform 契约生成类型）。 */
export type MyMenuNode = platform.components['schemas']['MyMenuNode']

/** 动态菜单下的表单元数据。 */
export type MyMenuForm = platform.components['schemas']['MyMenuForm']

/** 动态菜单下的按钮元数据（按动作权限标记可见）。 */
export type MyMenuButton = platform.components['schemas']['MyMenuButton']

/** 动态菜单下的字段元数据（按字段权限标记可见 / 可编辑）。 */
export type MyMenuField = platform.components['schemas']['MyMenuField']

/** 动态菜单响应体（菜单树 + 表单元数据 + 权限码集合）。 */
export type MyMenuResponse = platform.components['schemas']['MyMenuResponse']

/**
 * 取当前用户的动态菜单树 + 表单元数据 + 权限码集合（登录即可访问）。
 *
 * @returns 动态菜单响应体。
 */
export function fetchMyMenus(): Promise<MyMenuResponse> {
  return get<MyMenuResponse>('platform', '/menus/my')
}
