/**
 * 账号锁定端点封装：`/api/v1/account-locks`（列表 / 详情 / 手动锁定 / 解锁）。
 *
 * 服务段寻址与统一解包由宿主请求层承担（不手拼服务前缀）；响应类型取 `@bms/api-types`
 * 的 `platform` 命名空间（契约生成类型，禁止手写漂移）。
 */

import type { platform } from '@bms/api-types'

import { get, post, put } from './request'

import type { SnowflakeId } from './user'

type Schemas = platform.components['schemas']

/** 锁定记录行（含同库回显的用户名 / 姓名）。 */
export type LockItem = Schemas['LockItem']
/** 锁定记录分页响应。 */
export type LockPage = Schemas['BasePageResponse_LockItem_']
/** 手动锁定请求。 */
export type ManualLockRequest = Schemas['ManualLockRequest']

/** 锁定记录查询参数（筛选 + 分页）。 */
export interface LockListParams {
  /** 关键字（用户名 / 姓名）。 */
  kw?: string
  /** 锁定类型（fail_limit / inactive / manual）。 */
  lock_type?: string
  /**
   * 是否生效中（未解锁且未到期）。
   *
   * 界面「未解锁 / 已解锁」两态映射：未解锁 = `true`、已解锁 = `false`（含已到期自动解锁的记录）。
   */
  active?: boolean
  /** 用户主键（精确）。 */
  user_id?: SnowflakeId
  /** 页码。 */
  page?: number
  /** 每页条数。 */
  size?: number
}

/**
 * 锁定记录列表（筛选 + 分页）。
 *
 * @param params 查询参数。
 */
export function listAccountLocks(params: LockListParams = {}): Promise<LockPage> {
  return get<LockPage>('platform', '/account-locks', { ...params })
}

/**
 * 锁定记录详情（含已解锁）。
 *
 * @param lockId 锁定记录主键。
 */
export function getAccountLock(lockId: SnowflakeId): Promise<LockItem> {
  return get<LockItem>('platform', `/account-locks/${lockId}`)
}

/**
 * 手动锁定账号（`manual` 型，无期限；记录锁定人与原因）。
 *
 * @param body 手动锁定请求。
 */
export function lockAccount(body: ManualLockRequest): Promise<LockItem> {
  return post<LockItem>('platform', '/account-locks', body)
}

/**
 * 手动解锁（记录 `unlock_by` / `unlock_at`）。
 *
 * @param lockId 锁定记录主键。
 */
export function unlockAccount(lockId: SnowflakeId): Promise<LockItem> {
  return put<LockItem>('platform', `/account-locks/${lockId}/unlock`)
}
