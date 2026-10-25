/**
 * 自定义图标端点封装：`/api/v1/icons`（租户库 `sys_icon`，真实落库版）。
 *
 * 图标路由响应统一为 `ApiResponse`（data 为图标定义 / 清单），契约未生成具体 schema，
 * 故此处按路由契约字段（`bms_core.schemas.icon`）声明前端类型；`icon_key` 由后端派生
 * （`custom:{图标键}`），前端不得自拼前缀。
 */

import { del, get, post, put } from './request'
import type { I18nNames } from './menuMeta'

/** 图标状态（启用 `active` / 停用 `disabled`）。 */
export type IconStatus = 'active' | 'disabled'

/** 图标定义（清单 / 详情行）。 */
export interface IconItem {
  /** 图标标识（字符串化主键；非业务标识）。 */
  id: string
  /** 自建图标码（snake_case，租户内唯一）。 */
  code: string
  /** 图标名称（默认文案）。 */
  name: string
  /** 图标分组。 */
  category: string
  /** 标签（搜索用）。 */
  tags: string[]
  /** SVG 内容（内联）。 */
  svg: string
  /** 状态。 */
  status: IconStatus
  /** 派生 icon key（`custom:{code}`）。 */
  icon_key: string
  /** 多语言名称。 */
  i18n: I18nNames
  /** 被菜单 / 卡片引用次数。 */
  reference_count: number
}

/** 图标清单响应。 */
export interface IconListResponse {
  /** 图标清单。 */
  icons: IconItem[]
}

/** 图标清单查询参数。 */
export interface IconListQuery {
  /** 分组（缺省全部）。 */
  category?: string
  /** 状态（缺省全部）。 */
  status?: string
  /** 关键字（匹配图标键 / 名称 / 标签）。 */
  keyword?: string
}

/** 图标新增载荷。 */
export interface IconCreatePayload {
  /** 自建图标码（snake_case）。 */
  code: string
  /** 名称。 */
  name: string
  /** 分组。 */
  category: string
  /** 标签。 */
  tags?: string[]
  /** SVG 内容。 */
  svg: string
  /** 多语言名称。 */
  i18n?: I18nNames
}

/** 图标更新载荷（未提供字段保持不变）。 */
export interface IconUpdatePayload {
  /** 名称。 */
  name?: string
  /** 分组。 */
  category?: string
  /** 标签。 */
  tags?: string[]
  /** SVG 内容。 */
  svg?: string
  /** 状态。 */
  status?: IconStatus
  /** 多语言名称。 */
  i18n?: I18nNames
}

/**
 * 取图标清单（登录即可）。
 *
 * @param query 过滤条件。
 * @returns 图标清单。
 */
export function listIcons(query: IconListQuery = {}): Promise<IconListResponse> {
  const params: Record<string, unknown> = {}
  if (query.category !== undefined && query.category !== '') {
    params.category = query.category
  }
  if (query.status !== undefined && query.status !== '') {
    params.status = query.status
  }
  if (query.keyword !== undefined && query.keyword !== '') {
    params.keyword = query.keyword
  }
  return get<IconListResponse>('platform', '/icons', Object.keys(params).length === 0 ? undefined : params)
}

/**
 * 取单图标定义。
 *
 * @param code 图标键。
 * @returns 图标定义。
 */
export function getIcon(code: string): Promise<IconItem> {
  return get<IconItem>('platform', `/icons/${code}`)
}

/**
 * 新增自定义图标（`icon:manage`；SVG 基础校验由后端兜底）。
 *
 * @param payload 新增载荷。
 * @returns 图标定义。
 */
export function createIcon(payload: IconCreatePayload): Promise<IconItem> {
  return post<IconItem>('platform', '/icons', payload)
}

/**
 * 更新自定义图标（`icon:manage`）。
 *
 * @param code 图标键。
 * @param payload 更新载荷。
 * @returns 图标定义。
 */
export function updateIcon(code: string, payload: IconUpdatePayload): Promise<IconItem> {
  return put<IconItem>('platform', `/icons/${code}`, payload)
}

/**
 * 删除自定义图标（被菜单引用时 `40206`）。
 *
 * @param code 图标键。
 * @returns 删除结果。
 */
export function deleteIcon(code: string): Promise<{ deleted: boolean }> {
  return del<{ deleted: boolean }>('platform', `/icons/${code}`)
}
