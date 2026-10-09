/**
 * 角色端点封装：`/api/v1/roles`（角色 CRUD / 用户分配 / 授权 / 字段权限 / 数据权限）。
 *
 * 服务段寻址与统一解包由宿主请求层承担（不手拼服务前缀）；响应类型取 `@bms/api-types`
 * 的 `platform` 命名空间（契约生成类型，禁止手写漂移）。
 */

import type { platform } from '@bms/api-types'

import { del, get, post, put } from './request'

type Schemas = platform.components['schemas']

/**
 * 雪花 ID 传输形态：契约声明为整型，但 JSON 输出统一**字符串化**（超出 JS 安全整数）；
 * 请求侧按数值字符串提交（后端宽松模式将 `"8025…"` 解析为 `int`），避免精度丢失与二次漂移。
 */
export type SnowflakeId = string

/** 角色状态（契约 `RoleStatus`）。 */
export type RoleStatus = NonNullable<Schemas['RoleCreateRequest']['status']>

/** 批量分配载荷（ID 字符串口径，见 `SnowflakeId`）。 */
export interface RoleAssignPayload {
  /** 用户主键清单。 */
  user_ids: SnowflakeId[]
}

/** 授权条目载荷（ID 字符串口径，见 `SnowflakeId`）。 */
export interface RolePermissionEntryPayload {
  /** 授权类型（menu/form/action）。 */
  perm_type: 'menu' | 'form' | 'action'
  /** 授权目标 ID。 */
  target_id: SnowflakeId
  /** 来源菜单入口 ID（`0` = 表单级直接授予）。 */
  source_menu_id: SnowflakeId
}

/** 授权全量覆盖载荷。 */
export interface RolePermissionPayload {
  /** 授权条目清单（全量）。 */
  entries: RolePermissionEntryPayload[]
}

/** 字段权限条目载荷（ID 字符串口径）。 */
export interface RoleFieldEntryPayload {
  /** 表单 ID。 */
  form_id: SnowflakeId
  /** 字段 ID。 */
  field_id: SnowflakeId
  /** 是否可见。 */
  visible: boolean
  /** 是否可编辑。 */
  editable: boolean
  /** 来源菜单入口 ID（`0` = 表单级直接授予）。 */
  source_menu_id: SnowflakeId
}

/** 字段权限全量覆盖载荷。 */
export interface RoleFieldPayload {
  /** 字段权限条目清单（全量）。 */
  entries: RoleFieldEntryPayload[]
}

/** 数据权限条目载荷（ID 字符串口径）。 */
export interface RoleDataScopeEntryPayload {
  /** 字典类型 ID。 */
  dict_type_id: SnowflakeId
  /** 策略类型（select/region/match/extension）。 */
  policy_type: 'select' | 'region' | 'match' | 'extension'
  /** 结构化策略配置（按策略分结构）。 */
  config: Record<string, unknown>[]
}

/** 数据权限全量覆盖载荷。 */
export interface RoleDataScopePayload {
  /** 数据权限条目清单（全量）。 */
  entries: RoleDataScopeEntryPayload[]
}

/** 角色保存编排请求（分段全量覆盖；`null` = 不参与该段）。 */
export interface RoleAssignmentsPayload {
  /** 角色本体分段（`null` = 不改；非空时 `version` 乐观锁）。 */
  role: { code?: string; name?: string; status?: RoleStatus; version: number } | null
  /** 角色直接用户全量集合（`null` = 不改；`[]` = 清空）。 */
  user_ids: SnowflakeId[] | null
  /** 角色-岗位全量覆盖（`null` = 不改；角色侧无主要项）。 */
  role_posts: { post_ids: SnowflakeId[] } | null
  /** 角色-部门全量覆盖（`null` = 不改；角色侧无主要项）。 */
  role_depts: { dept_ids: SnowflakeId[] } | null
}

/** 角色保存编排结果。 */
export type RoleAssignmentsResult = Schemas['RoleAssignmentsResult']

/** 角色列表行。 */
export type RoleItem = Schemas['RoleItem']
/** 角色详情（含版本与审计字段）。 */
export type RoleDetail = Schemas['RoleDetail']
/** 新增角色请求。 */
export type RoleCreateRequest = Schemas['RoleCreateRequest']
/** 修改角色请求（乐观锁）。 */
export type RoleUpdateRequest = Schemas['RoleUpdateRequest']
/** 角色分页响应。 */
export type RolePage = Schemas['BasePageResponse_RoleItem_']
/** 已分配用户行。 */
export type AssignedUserItem = Schemas['AssignedUserItem']
/** 已分配用户分页响应。 */
export type AssignedUserPage = Schemas['BasePageResponse_AssignedUserItem_']
/** 批量分配请求。 */
export type RoleAssignRequest = Schemas['RoleAssignRequest']
/** 批量分配结果。 */
export type RoleAssignedUsers = Schemas['RoleAssignedUsers']
/** 授权条目行 / 清单 / 请求。 */
export type RolePermissionEntryItem = Schemas['RolePermissionEntryItem']
export type RolePermissions = Schemas['RolePermissions']
export type RolePermissionRequest = Schemas['RolePermissionRequest']
/** 字段权限条目行 / 清单 / 请求。 */
export type RoleFieldEntryItem = Schemas['RoleFieldEntryItem']
export type RoleFields = Schemas['RoleFields']
export type RoleFieldRequest = Schemas['RoleFieldRequest']
/** 数据权限条目行 / 清单 / 请求。 */
export type RoleDataScopeEntryItem = Schemas['RoleDataScopeEntryItem']
export type RoleDataScopes = Schemas['RoleDataScopes']
export type RoleDataScopeRequest = Schemas['RoleDataScopeRequest']

/** 角色列表查询参数（关键字 / 状态 + 分页）。 */
export interface RoleListParams {
  /** 关键字（角色码 / 名称）。 */
  kw?: string
  /** 状态。 */
  status?: string
  /** 页码。 */
  page?: number
  /** 每页条数。 */
  size?: number
}

/** 已分配用户查询参数。 */
export interface AssignedUserParams {
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
 * 角色列表（关键字 / 状态筛选 + 分页）。
 *
 * @param params 查询参数。
 */
export function listRoles(params: RoleListParams = {}): Promise<RolePage> {
  return get<RolePage>('platform', '/roles', { ...params })
}

/**
 * 角色详情。
 *
 * @param roleId 角色主键。
 */
export function getRole(roleId: string): Promise<RoleDetail> {
  return get<RoleDetail>('platform', `/roles/${roleId}`)
}

/**
 * 角色保存编排（分段全量覆盖；跨服务原子）。
 *
 * 一次请求提交角色本体 + 用户分配 + mdm 岗位 / 部门分配；`provider=xa` 走 TM 全局事务、
 * `provider=null`（dev / test）走顺序提交（见 `02_03/_02` 详设）。
 *
 * @param roleId 角色主键。
 * @param body 分段全量覆盖载荷（`null` = 该段不参与）。
 */
export function applyRoleAssignments(
  roleId: string,
  body: RoleAssignmentsPayload,
): Promise<RoleAssignmentsResult> {
  return put<RoleAssignmentsResult>('platform', `/roles/${roleId}/assignments`, body)
}

/**
 * 新增角色。
 *
 * @param body 新增请求。
 */
export function createRole(body: RoleCreateRequest): Promise<RoleDetail> {
  return post<RoleDetail>('platform', '/roles', body)
}

/**
 * 修改角色（名称 / 状态；乐观锁）。
 *
 * @param roleId 角色主键。
 * @param body 修改请求（含 `version`）。
 */
export function updateRole(roleId: string, body: RoleUpdateRequest): Promise<RoleDetail> {
  return put<RoleDetail>('platform', `/roles/${roleId}`, body)
}

/**
 * 删除角色。
 *
 * @param roleId 角色主键。
 */
export function deleteRole(roleId: string): Promise<null> {
  return del<null>('platform', `/roles/${roleId}`)
}

/**
 * 角色已分配用户（筛选 + 分页）。
 *
 * @param roleId 角色主键。
 * @param params 查询参数。
 */
export function listRoleUsers(roleId: string, params: AssignedUserParams = {}): Promise<AssignedUserPage> {
  return get<AssignedUserPage>('platform', `/roles/${roleId}/users`, { ...params })
}

/**
 * 批量分配用户（幂等 upsert）。
 *
 * @param roleId 角色主键。
 * @param body 分配载荷（ID 字符串口径）。
 */
export function assignRoleUsers(roleId: string, body: RoleAssignPayload): Promise<RoleAssignedUsers> {
  return post<RoleAssignedUsers>('platform', `/roles/${roleId}/users`, body)
}

/**
 * 解绑用户。
 *
 * @param roleId 角色主键。
 * @param userId 用户主键。
 */
export function unassignRoleUser(roleId: string, userId: string): Promise<null> {
  return del<null>('platform', `/roles/${roleId}/users/${userId}`)
}

/**
 * 角色授权条目（菜单 / 表单 / 操作）。
 *
 * @param roleId 角色主键。
 */
export function getRolePermissions(roleId: string): Promise<RolePermissions> {
  return get<RolePermissions>('platform', `/roles/${roleId}/permissions`)
}

/**
 * 全量覆盖角色授权。
 *
 * @param roleId 角色主键。
 * @param body 授权请求。
 */
export function replaceRolePermissions(roleId: string, body: RolePermissionPayload): Promise<RolePermissions> {
  return put<RolePermissions>('platform', `/roles/${roleId}/permissions`, body)
}

/**
 * 角色字段权限条目。
 *
 * @param roleId 角色主键。
 */
export function getRoleFields(roleId: string): Promise<RoleFields> {
  return get<RoleFields>('platform', `/roles/${roleId}/fields`)
}

/**
 * 全量覆盖角色字段权限。
 *
 * @param roleId 角色主键。
 * @param body 字段权限请求。
 */
export function replaceRoleFields(roleId: string, body: RoleFieldPayload): Promise<RoleFields> {
  return put<RoleFields>('platform', `/roles/${roleId}/fields`, body)
}

/**
 * 角色数据权限条目。
 *
 * @param roleId 角色主键。
 */
export function getRoleDataScopes(roleId: string): Promise<RoleDataScopes> {
  return get<RoleDataScopes>('platform', `/roles/${roleId}/data-permissions`)
}

/**
 * 全量覆盖角色数据权限。
 *
 * @param roleId 角色主键。
 * @param body 数据权限请求。
 */
export function replaceRoleDataScopes(roleId: string, body: RoleDataScopePayload): Promise<RoleDataScopes> {
  return put<RoleDataScopes>('platform', `/roles/${roleId}/data-permissions`, body)
}
