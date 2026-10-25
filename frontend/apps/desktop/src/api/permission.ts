/**
 * 权限码端点封装：`/api/v1/permissions`（平台维护视图）。
 *
 * 权限码 = 业务码 × 动作码组合，为唯一强制校验单位；组合创建后只读（换绑 = 删除重建），
 * 支持手工新增、批量补生成缺失组合、启停与有条件删除。
 */

import type { platform } from '@bms/api_types'

import { del, get, post, put } from './request'
import type { MetaStatus, SnowflakeId } from './menuMeta'

type Schemas = platform.components['schemas']

/** 权限码行。 */
export type PermissionItem = Schemas['PermissionItem']
/** 权限码清单。 */
export type PermissionList = Schemas['PermissionList']
/** 批量补生成结果计数。 */
export type PermissionGenerateResult = Schemas['PermissionGenerateResult']

/** 权限码手工新增载荷。 */
export interface PermissionCreatePayload {
  /** 业务码 ID。 */
  business_id: SnowflakeId
  /** 动作码 ID。 */
  action_id: SnowflakeId
  /** 状态。 */
  status: MetaStatus
}

/** 权限码更新载荷（组合不可换绑，仅状态）。 */
export interface PermissionUpdatePayload {
  /** 状态。 */
  status: MetaStatus
}

/** 批量补生成载荷（范围为空 = 全部启用项）。 */
export interface PermissionGeneratePayload {
  /** 限定业务码 ID 清单（空 = 全部启用业务码）。 */
  business_ids: SnowflakeId[]
  /** 限定动作码 ID 清单（空 = 全部启用动作码）。 */
  action_ids: SnowflakeId[]
  /** 是否包含停用的业务 / 动作码。 */
  include_disabled: boolean
}

/**
 * 取权限码清单（可按业务码过滤）。
 *
 * @param businessId 业务码主键（可选）。
 * @returns 权限码清单。
 */
export function listPermissions(businessId?: SnowflakeId): Promise<PermissionList> {
  return get<PermissionList>('platform', '/permissions', businessId === undefined ? undefined : { business_id: businessId })
}

/**
 * 手工新增权限码组合（重复 `40210`；软删除行命中即恢复）。
 *
 * @param payload 新增载荷。
 * @returns 新建权限码行。
 */
export function createPermission(payload: PermissionCreatePayload): Promise<PermissionItem> {
  return post<PermissionItem>('platform', '/permissions', payload)
}

/**
 * 批量补生成缺失权限码组合。
 *
 * @param payload 范围与是否含停用项。
 * @returns 新建 / 恢复 / 跳过计数。
 */
export function generatePermissions(payload: PermissionGeneratePayload): Promise<PermissionGenerateResult> {
  return post<PermissionGenerateResult>('platform', '/permissions/generate', payload)
}

/**
 * 更新权限码状态（被按钮 / 角色授权引用时 `40206`）。
 *
 * @param id 权限码主键。
 * @param payload 更新载荷。
 * @returns 更新后的权限码行。
 */
export function updatePermission(id: SnowflakeId, payload: PermissionUpdatePayload): Promise<PermissionItem> {
  return put<PermissionItem>('platform', `/permissions/${id}`, payload)
}

/**
 * 删除权限码（软删除；被引用时 `40206`）。
 *
 * @param id 权限码主键。
 */
export function deletePermission(id: SnowflakeId): Promise<null> {
  return del<null>('platform', `/permissions/${id}`)
}
