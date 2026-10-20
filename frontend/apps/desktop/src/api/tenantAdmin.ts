/**
 * 租户管理端点封装：`/api/v1/tenants`（租户 CRUD / 开通 / 停用启用 / 模块开关 / 配额）。
 *
 * 服务段寻址与统一解包由宿主请求层承担（不自拼服务前缀）；响应类型取 `@bms/api-types` 的
 * `tenant` 命名空间（契约生成类型，禁止手写漂移）。
 */

import type { tenant } from '@bms/api-types'

import { get, post, put } from './request'

type Schemas = tenant.components['schemas']

/** 雪花 ID 传输形态（JSON 字符串化，避免精度丢失）。 */
export type TenantId = string

/** 租户状态。 */
export type TenantStatus = Schemas['TenantDetail']['status']

/** 租户列表行。 */
export type TenantItem = Schemas['TenantListItem']

/** 租户分页响应。 */
export type TenantPage = Schemas['TenantList']

/** 租户详情（含模块 / 配额）。 */
export type TenantDetail = Schemas['TenantDetail']

/** 新增（开通）请求。 */
export type TenantCreateRequest = Schemas['TenantCreateRequest']

/** 修改请求。 */
export type TenantUpdateRequest = Schemas['TenantUpdateRequest']

/** 开通结果（初始口令仅本次返回）。 */
export type TenantProvisionResult = Schemas['TenantProvisionResult']

/** 模块项（目录 + 开通清单三态）。 */
export type TenantModuleItem = Schemas['TenantModuleItem']

/** 模块选项（开通向导）。 */
export type TenantModuleOption = Schemas['TenantModuleOption']

/** 配额项（限额与用量）。 */
export type TenantQuotaItem = Schemas['TenantQuotaItem']

/** 配额整组覆盖项。 */
export type TenantQuotaUpdateItem = Schemas['TenantQuotaUpdateItem']

/** 租户列表查询参数。 */
export interface TenantListParams {
  /** 租户编码（模糊）。 */
  code?: string
  /** 租户名称（模糊）。 */
  name?: string
  /** 状态。 */
  status?: string
  /** 页码。 */
  page?: number
  /** 每页条数。 */
  size?: number
}

/**
 * 租户列表（编码 / 名称 / 状态筛选 + 分页；平台租户排除）。
 *
 * @param params 查询参数。
 */
export function listTenants(params: TenantListParams = {}): Promise<TenantPage> {
  return get<TenantPage>('tenant', '/tenants', { ...params })
}

/**
 * 开通向导模块选项（目录全量 + 可勾选标记）。
 */
export function fetchModuleOptions(): Promise<{ items?: TenantModuleOption[] }> {
  return get<{ items?: TenantModuleOption[] }>('tenant', '/tenants/module-options')
}

/**
 * 开通租户（同步全流程；请求层自动带幂等键）。
 *
 * @param body 开通请求。
 */
export function createTenant(body: TenantCreateRequest): Promise<TenantProvisionResult> {
  return post<TenantProvisionResult>('tenant', '/tenants', body)
}

/**
 * 租户详情（含模块 / 配额）。
 *
 * @param tenantId 租户主键。
 */
export function getTenant(tenantId: TenantId): Promise<TenantDetail> {
  return get<TenantDetail>('tenant', `/tenants/${tenantId}`)
}

/**
 * 修改租户（名称 / 域名 / 到期时间）。
 *
 * @param tenantId 租户主键。
 * @param body 修改请求。
 */
export function updateTenant(tenantId: TenantId, body: TenantUpdateRequest): Promise<TenantDetail> {
  return put<TenantDetail>('tenant', `/tenants/${tenantId}`, body)
}

/**
 * 停用租户（事件 + 引擎回收 + 会话撤销）。
 *
 * @param tenantId 租户主键。
 */
export function suspendTenant(tenantId: TenantId): Promise<TenantDetail> {
  return post<TenantDetail>('tenant', `/tenants/${tenantId}/suspend`)
}

/**
 * 启用租户。
 *
 * @param tenantId 租户主键。
 */
export function activateTenant(tenantId: TenantId): Promise<TenantDetail> {
  return post<TenantDetail>('tenant', `/tenants/${tenantId}/activate`)
}

/**
 * 租户模块清单（三态）。
 *
 * @param tenantId 租户主键。
 */
export function fetchTenantModules(tenantId: TenantId): Promise<{ items?: TenantModuleItem[] }> {
  return get<{ items?: TenantModuleItem[] }>('tenant', `/tenants/${tenantId}/modules`)
}

/**
 * 切换租户模块开关。
 *
 * @param tenantId 租户主键。
 * @param moduleKey 模块标识。
 * @param status 目标状态。
 */
export function switchTenantModule(
  tenantId: TenantId,
  moduleKey: string,
  status: 'enabled' | 'disabled',
): Promise<{ items?: TenantModuleItem[] }> {
  return put<{ items?: TenantModuleItem[] }>('tenant', `/tenants/${tenantId}/modules/${moduleKey}`, {
    status,
  })
}

/**
 * 租户配额与用量。
 *
 * @param tenantId 租户主键。
 */
export function fetchTenantQuotas(tenantId: TenantId): Promise<{ items?: TenantQuotaItem[] }> {
  return get<{ items?: TenantQuotaItem[] }>('tenant', `/tenants/${tenantId}/quotas`)
}

/**
 * 更新租户配额（整组覆盖；未列出维度保持原值）。
 *
 * @param tenantId 租户主键。
 * @param items 配额项清单。
 */
export function updateTenantQuotas(
  tenantId: TenantId,
  items: TenantQuotaUpdateItem[],
): Promise<{ items?: TenantQuotaItem[] }> {
  return put<{ items?: TenantQuotaItem[] }>('tenant', `/tenants/${tenantId}/quotas`, { items })
}
