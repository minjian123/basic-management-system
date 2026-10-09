/**
 * 用户端点封装：`/api/v1/users`（列表 / CRUD / 启停 / 重置密码 / 角色查看 / 分配编排 / SSO 绑定查看）。
 *
 * 服务段寻址与统一解包由宿主请求层承担（不手拼服务前缀）；响应类型取 `@bms/api-types`
 * 的 `platform` / `identity` 命名空间（契约生成类型，禁止手写漂移）。
 */

import type { identity, platform } from '@bms/api-types'

import { del, get, post, put } from './request'

type Schemas = platform.components['schemas']
type IdentitySchemas = identity.components['schemas']

/**
 * 雪花 ID 传输形态：契约声明为整型，但 JSON 输出统一**字符串化**（超出 JS 安全整数）；
 * 请求侧按数值字符串提交（后端宽松模式将 `"8025…"` 解析为 `int`），避免精度丢失与二次漂移。
 */
export type SnowflakeId = string

/** 最小用户查询行。 */
export type UserItem = Schemas['UserItem']
/** 用户分页响应。 */
export type UserPage = Schemas['BasePageResponse_UserItem_']
/** 用户详情。 */
export type UserDetail = Schemas['UserDetail']
/** 新建用户请求 / 结果。 */
export type UserAdminCreateRequest = Schemas['UserAdminCreateRequest']
export type UserAdminCreateResult = Schemas['UserAdminCreateResult']
/** 修改用户请求。 */
export type UserUpdateRequest = Schemas['UserUpdateRequest']
/** 启停请求 / 结果。 */
export type UserStatusUpdateRequest = Schemas['UserStatusUpdateRequest']
export type UserStatusResult = Schemas['UserStatusResult']
/** 重置密码请求 / 结果。 */
export type UserPasswordResetRequest = Schemas['UserPasswordResetRequest']
export type UserPasswordResetResult = Schemas['UserPasswordResetResult']
/** 用户直接角色清单。 */
export type UserRoleList = Schemas['UserRoleList']
export type UserRoleItem = Schemas['UserRoleItem']
/** 分配编排请求 / 结果（跨服务原子；见 `02_02/_02`）。 */
export type UserAssignmentsRequest = Schemas['UserAssignmentsRequest']
export type UserAssignmentsResult = Schemas['UserAssignmentsResult']
export type UserAssignmentProfile = Schemas['UserAssignmentProfile']
export type UserAssignmentPosts = Schemas['UserAssignmentPosts']
export type UserAssignmentDepts = Schemas['UserAssignmentDepts']
/** 账号状态取值。 */
export type UserStatus = NonNullable<Schemas['UserStatusUpdateRequest']['status']>
/** SSO 身份绑定清单（identity 服务）。 */
export type SsoIdentityList = IdentitySchemas['SsoIdentityList']

/** 用户查询参数（关键字 / 状态 + 分页）。 */
export interface UserListParams {
  /** 关键字（账号 / 姓名 / 邮箱 / 手机号）。 */
  kw?: string
  /** 账号状态。 */
  status?: string
  /** 页码。 */
  page?: number
  /** 每页条数。 */
  size?: number
}

/**
 * 用户列表（关键字四字段 + 状态 + 分页）。
 *
 * @param params 查询参数。
 */
export function listUsers(params: UserListParams = {}): Promise<UserPage> {
  return get<UserPage>('platform', '/users', { ...params })
}

/**
 * 用户详情（含联系方式与乐观锁版本）。
 *
 * @param userId 用户主键。
 */
export function getUser(userId: SnowflakeId): Promise<UserDetail> {
  return get<UserDetail>('platform', `/users/${userId}`)
}

/**
 * 新建用户（初始密码可空；缺省后端随机生成并一次性回显）。
 *
 * @param body 新建请求。
 */
export function createUser(body: UserAdminCreateRequest): Promise<UserAdminCreateResult> {
  return post<UserAdminCreateResult>('platform', '/users', body)
}

/**
 * 修改用户基本资料（昵称 / 邮箱 / 手机；乐观锁）。
 *
 * @param userId 用户主键。
 * @param body 修改请求（含 `version`）。
 */
export function updateUser(userId: SnowflakeId, body: UserUpdateRequest): Promise<UserDetail> {
  return put<UserDetail>('platform', `/users/${userId}`, body)
}

/**
 * 启用 / 停用账号（停用即时失效该用户全部会话）。
 *
 * @param userId 用户主键。
 * @param status 目标状态。
 */
export function updateUserStatus(userId: SnowflakeId, status: UserStatus): Promise<UserStatusResult> {
  const body: UserStatusUpdateRequest = { status }
  return put<UserStatusResult>('platform', `/users/${userId}/status`, body)
}

/**
 * 软删除用户。
 *
 * @param userId 用户主键。
 */
export function deleteUser(userId: SnowflakeId): Promise<null> {
  return del<null>('platform', `/users/${userId}`)
}

/**
 * 重置密码（强制改密可选；全部会话失效）。
 *
 * @param userId 用户主键。
 * @param body 重置请求。
 */
export function resetUserPassword(userId: SnowflakeId, body: UserPasswordResetRequest): Promise<UserPasswordResetResult> {
  return put<UserPasswordResetResult>('platform', `/users/${userId}/password`, body)
}

/**
 * 查看用户直接角色（只读）。
 *
 * @param userId 用户主键。
 */
export function listUserRoles(userId: SnowflakeId): Promise<UserRoleList> {
  return get<UserRoleList>('platform', `/users/${userId}/roles`)
}

/**
 * 用户保存编排（分段全量覆盖；跨服务原子）。
 *
 * @param userId 用户主键。
 * @param body 分段请求（未参与的段传 `null`）。
 */
export function applyUserAssignments(
  userId: SnowflakeId,
  body: UserAssignmentsRequest,
): Promise<UserAssignmentsResult> {
  return put<UserAssignmentsResult>('platform', `/users/${userId}/assignments`, body)
}

/**
 * 查看用户 SSO 身份绑定（只读；端点归 identity 服务）。
 *
 * @param userId 用户主键。
 */
export function listUserIdentities(userId: SnowflakeId): Promise<SsoIdentityList> {
  return get<SsoIdentityList>('identity', `/users/${userId}/identities`)
}
