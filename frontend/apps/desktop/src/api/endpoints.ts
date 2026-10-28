/** 能力源端点解析：按「域 → 服务前缀」单一来源为各能力源注入 endpoint 与令牌头。 */

import { servicePrefix, serviceUrl, type ServiceKey } from '@bms/core'
import { orgSourceEndpoint } from '@bms/ui_ep'

import { getAccessToken } from './token'

/** 能力源端点选项（结构兼容各 `createHttp*` 的 options）。 */
export interface SourceEndpointOptions {
  /** 端点前缀（如 `/api/platform/v1`）；**缺省表示目录不可用**，消费方据此进入降级、不发起请求。 */
  endpoint?: string
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

/**
 * 组织主数据源选项（**端点运行期取自平台目录快照**）。
 *
 * 组织主数据归**产品服务**（经产品命名空间 `/api/{产品键}/v1/{域段}` 对外），平台不再持有产品键与
 * 命名空间常量：端点由 `@bms/ui_ep` 的 `orgSourceEndpoint()` 按「业务域 + 能力种类」从目录推导
 * （`03_02`）。目录不可用 / 未接入 / 目标不唯一时**不返回端点**（消费方进入降级，不发起请求）。
 */
export function orgSourceOptions(): SourceEndpointOptions {
  const endpoint = orgSourceEndpoint()
  return endpoint === null ? { headers: authHeaders } : { endpoint, headers: authHeaders }
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
