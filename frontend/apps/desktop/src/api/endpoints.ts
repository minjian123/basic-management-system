/** 能力源端点解析：按「域 → 服务前缀」单一来源为各能力源注入 endpoint 与令牌头。 */

import { servicePrefix, serviceUrl, type ServiceKey } from '@bms/core'

import { getAccessToken } from './token'

/** 能力源端点选项（结构兼容各 `createHttp*` 的 options）。 */
export interface SourceEndpointOptions {
  /** 端点前缀（如 `/api/platform/v1`）。 */
  endpoint: string
  /** 请求头提供器（有令牌时注入 Bearer）。 */
  headers: () => Record<string, string>
}

/**
 * 鉴权请求头提供器（读取内存令牌，动态取值）。
 *
 * @returns 有令牌返回 `{ Authorization: 'Bearer <token>' }`，否则空对象。
 */
export function authHeaders(): Record<string, string> {
  const token = getAccessToken()
  return token === null ? {} : { Authorization: `Bearer ${token}` }
}

/**
 * 按服务组装能力源端点选项。
 *
 * @param service 服务键。
 */
export function sourceEndpoint(service: ServiceKey): SourceEndpointOptions {
  return { endpoint: servicePrefix(service), headers: authHeaders }
}

/** 字典数据源选项（含高级查询 / 查询方案；`platform`）。 */
export function dictSourceOptions(): SourceEndpointOptions {
  return sourceEndpoint('platform')
}

/** 组织主数据源选项（`org`）。 */
export function orgSourceOptions(): SourceEndpointOptions {
  return sourceEndpoint('org')
}

/** 验证码数据源选项（`identity`）。 */
export function captchaSourceOptions(): SourceEndpointOptions {
  return sourceEndpoint('identity')
}

/** 文件上传通路选项（`file`）。 */
export function uploadTransportOptions(): SourceEndpointOptions {
  return sourceEndpoint('file')
}

/** 全文检索引擎选项（`search`）。 */
export function searchEngineOptions(): SourceEndpointOptions {
  return sourceEndpoint('search')
}

/**
 * AI 流式端点（`ai`）。
 *
 * @param path 流式子路径（缺省 `/chat/stream`）。
 */
export function aiStreamEndpoint(path = '/chat/stream'): string {
  return serviceUrl('ai', path)
}
