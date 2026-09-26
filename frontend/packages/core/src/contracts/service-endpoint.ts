/**
 * 服务寻址契约（框架无关）：外部路径 `/api/{service_key}/v1/...` 的「域 → 服务前缀」单一来源。
 *
 * 网关按服务目录生成外部路由 `/api/{service_key}/v1`（重写为服务内 `/api/v1`）；前端请求
 * 一律经本模块组装地址，**禁止各模块 / 页面自拼服务前缀**。服务键与后端服务目录
 * `SERVICE_CATALOG`（`service_key`）同源，顺序保持一致（9 个已启用服务）。
 */

import { BaseError } from '../mechanisms/error'
import { ErrorCodes } from '../mechanisms/error-codes'

/** 服务键（与后端服务目录 `service_key` 同源）。 */
export type ServiceKey =
  | 'platform'
  | 'identity'
  | 'tenant'
  | 'org'
  | 'file'
  | 'notification'
  | 'search'
  | 'ai'
  | 'report'

/** 服务键清单（顺序与服务目录一致：9 个已启用服务）。 */
export const SERVICE_KEYS: readonly ServiceKey[] = [
  'platform',
  'identity',
  'tenant',
  'org',
  'file',
  'notification',
  'search',
  'ai',
  'report',
]

/** 外部路径版本段。 */
export const API_VERSION_SEGMENT = 'v1'

/**
 * 服务键判定（未知服务不静默放行）。
 *
 * @param value 待判定值。
 * @returns 是否为已登记服务键。
 */
export function isServiceKey(value: unknown): value is ServiceKey {
  return typeof value === 'string' && (SERVICE_KEYS as readonly string[]).includes(value)
}

/**
 * 服务前缀（`/api/{service}/v1`）。
 *
 * @param service 服务键。
 * @returns 外部服务前缀。
 * @throws BaseError 未登记的服务键（`CAPABILITY_VIOLATION`，参数段位）。
 */
export function servicePrefix(service: ServiceKey): string {
  if (!isServiceKey(service)) {
    throw new BaseError(ErrorCodes.CAPABILITY_VIOLATION, `未登记的服务键：${String(service)}`)
  }
  return `/api/${service}/${API_VERSION_SEGMENT}`
}

/**
 * 服务段 URL 组装（`/api/{service}/v1{path}`）。
 *
 * 路径归一：去首部斜杠、折叠重复斜杠；空路径返回前缀本身。
 *
 * @param service 服务键。
 * @param path 资源子路径（可带或不带首部 `/`；缺省空）。
 * @returns 外部请求地址。
 * @throws BaseError 未登记的服务键（`CAPABILITY_VIOLATION`，参数段位）。
 */
export function serviceUrl(service: ServiceKey, path = ''): string {
  const prefix = servicePrefix(service)
  const normalized = path.replace(/^\/+/, '').replace(/\/{2,}/g, '/')
  return normalized === '' ? prefix : `${prefix}/${normalized}`
}
