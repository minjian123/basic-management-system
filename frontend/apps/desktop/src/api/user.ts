/**
 * 用户端点封装（最小只读查询）：`GET /api/v1/users`。
 *
 * 供角色「选择用户」弹窗与已分配列表回显；用户完整域 CRUD 归 `02_01`（同一端点扩展）。
 * 响应类型取 `@bms/api-types` 的 `platform` 命名空间。
 */

import type { platform } from '@bms/api-types'

import { get } from './request'

type Schemas = platform.components['schemas']

/** 最小用户查询行。 */
export type UserItem = Schemas['UserItem']
/** 用户分页响应。 */
export type UserPage = Schemas['BasePageResponse_UserItem_']

/** 用户查询参数（关键字 / 状态 + 分页）。 */
export interface UserListParams {
  /** 关键字（账号 / 姓名）。 */
  kw?: string
  /** 账号状态。 */
  status?: string
  /** 页码。 */
  page?: number
  /** 每页条数。 */
  size?: number
}

/**
 * 用户最小字段列表（选择用户弹窗取数）。
 *
 * @param params 查询参数。
 */
export function listUsers(params: UserListParams = {}): Promise<UserPage> {
  return get<UserPage>('platform', '/users', { ...params })
}
