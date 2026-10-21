/**
 * 业务码端点封装：`/api/v1/businesses`（平台维护视图）。
 *
 * 业务码为纯资源维度（权限码左半），平台统一维护、租户只读；`code` 创建后只读。
 */

import type { platform } from '@bms/api-types'

import { del, get, post, put } from './request'
import type { I18nNames, MetaStatus, SnowflakeId } from './menuMeta'

type Schemas = platform.components['schemas']

/** 业务码行。 */
export type BusinessItem = Schemas['BusinessItem']
/** 业务码清单。 */
export type BusinessList = Schemas['BusinessList']

/** 业务码新增载荷。 */
export interface BusinessCreatePayload {
  /** 业务码（kebab-case，创建后只读）。 */
  code: string
  /** 状态。 */
  status: MetaStatus
  /** 多语言名称。 */
  i18n: I18nNames
}

/** 业务码更新载荷（`code` 不可改）。 */
export interface BusinessUpdatePayload {
  /** 状态。 */
  status: MetaStatus
  /** 多语言名称。 */
  i18n: I18nNames
}

/**
 * 取业务码清单（含各码下权限码数量）。
 *
 * @returns 业务码清单。
 */
export function listBusinesses(): Promise<BusinessList> {
  return get<BusinessList>('platform', '/businesses')
}

/**
 * 新增业务码（重复 `40209`）。
 *
 * @param payload 新增载荷。
 * @returns 新建业务码行。
 */
export function createBusiness(payload: BusinessCreatePayload): Promise<BusinessItem> {
  return post<BusinessItem>('platform', '/businesses', payload)
}

/**
 * 更新业务码（停用联动其权限码；被引用整批拒绝 `40206`）。
 *
 * @param id 业务码主键。
 * @param payload 更新载荷。
 * @returns 更新后的业务码行。
 */
export function updateBusiness(id: SnowflakeId, payload: BusinessUpdatePayload): Promise<BusinessItem> {
  return put<BusinessItem>('platform', `/businesses/${id}`, payload)
}

/**
 * 删除业务码（软删除；其下有权限码或被表单引用时 `40206`）。
 *
 * @param id 业务码主键。
 */
export function deleteBusiness(id: SnowflakeId): Promise<null> {
  return del<null>('platform', `/businesses/${id}`)
}
