/**
 * 菜单记录页本体草稿：载荷组装 / 脏态指纹 / 本地校验。
 *
 * 后端为整体替换语义（`PUT /menus/{id}` 收完整字段 + 新 `parent_id` / `sort`），
 * 故本模块负责把界面草稿规整为请求载荷，并在保存前做最小本地校验（后端仍为唯一裁决方）。
 */

import type { I18nNames, MenuPayload, MetaStatus } from '@/api/menuMeta'

import { sortI18n } from './linkDraft'

/** 菜单本体草稿。 */
export interface MenuDraft {
  /** 父菜单 ID（`0` 为根）。 */
  parent_id: string
  /** 路由路径。 */
  path: string
  /** 视图组件标识（空串 = 目录）。 */
  component: string
  /** 完整 icon key（空串 = 未选择）。 */
  icon: string
  /** 同级排序。 */
  sort: number
  /** 仅隐藏侧栏入口。 */
  hidden: boolean
  /** 状态。 */
  status: MetaStatus
  /** 多语言名称。 */
  i18n: I18nNames
}

/**
 * 草稿 → 请求载荷（空串归一为 `null`）。
 *
 * @param draft 菜单草稿。
 * @returns 请求载荷。
 */
export function toMenuPayload(draft: MenuDraft): MenuPayload {
  return {
    parent_id: draft.parent_id,
    path: draft.path.trim(),
    component: draft.component.trim() === '' ? null : draft.component.trim(),
    icon: draft.icon.trim() === '' ? null : draft.icon.trim(),
    sort: draft.sort,
    hidden: draft.hidden,
    status: draft.status,
    i18n: sortI18n(draft.i18n),
  }
}

/**
 * 本体脏态指纹（稳定字符串）。
 *
 * @param draft 菜单草稿。
 * @returns 指纹。
 */
export function menuFingerprint(draft: MenuDraft): string {
  return JSON.stringify(toMenuPayload(draft))
}

/**
 * 保存前本地校验。
 *
 * @param draft 菜单草稿。
 * @param requiredLocale 必填语言（当前登录用户语言）。
 * @returns 错误文案；通过返回 `undefined`。
 */
export function validateMenuDraft(draft: MenuDraft, requiredLocale: string): string | undefined {
  if (draft.path.trim() === '') {
    return '路由路径必填'
  }
  if ((draft.i18n[requiredLocale] ?? '').trim() === '') {
    return `名称（${requiredLocale}）不能为空`
  }
  return undefined
}
