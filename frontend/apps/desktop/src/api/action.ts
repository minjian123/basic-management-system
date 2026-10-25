/**
 * 动作码端点封装：`/api/v1/actions`（平台维护视图）。
 *
 * 动作码为全局动词维度（不归属业务），平台统一维护、租户只读；`code` 创建后只读。
 */

import type { platform } from '@bms/api_types'

import { del, get, post, put } from './request'
import type { I18nNames, MetaStatus, SnowflakeId } from './menuMeta'

type Schemas = platform.components['schemas']

/** 动作码行。 */
export type ActionItem = Schemas['ActionItem']
/** 动作码清单。 */
export type ActionList = Schemas['ActionList']

/** 动作码新增载荷。 */
export interface ActionCreatePayload {
  /** 动作码（snake_case：小写字母开头，仅小写字母 / 数字 / 下划线；创建后只读）。 */
  code: string
  /** 状态。 */
  status: MetaStatus
  /** 多语言名称。 */
  i18n: I18nNames
}

/** 动作码更新载荷（`code` 不可改）。 */
export interface ActionUpdatePayload {
  /** 状态。 */
  status: MetaStatus
  /** 多语言名称。 */
  i18n: I18nNames
}

/**
 * 取动作码清单。
 *
 * @returns 动作码清单。
 */
export function listActions(): Promise<ActionList> {
  return get<ActionList>('platform', '/actions')
}

/**
 * 新增动作码（重复 `40209`）。
 *
 * @param payload 新增载荷。
 * @returns 新建动作码行。
 */
export function createAction(payload: ActionCreatePayload): Promise<ActionItem> {
  return post<ActionItem>('platform', '/actions', payload)
}

/**
 * 更新动作码（停用联动其权限码；被引用整批拒绝 `40206`）。
 *
 * @param id 动作码主键。
 * @param payload 更新载荷。
 * @returns 更新后的动作码行。
 */
export function updateAction(id: SnowflakeId, payload: ActionUpdatePayload): Promise<ActionItem> {
  return put<ActionItem>('platform', `/actions/${id}`, payload)
}

/**
 * 删除动作码（软删除；其下有权限码时 `40206`）。
 *
 * @param id 动作码主键。
 */
export function deleteAction(id: SnowflakeId): Promise<null> {
  return del<null>('platform', `/actions/${id}`)
}
