/**
 * 服务寻址契约（框架无关）：外部路径的「域 → 前缀」**单一来源**。
 *
 * 两类命名空间并列（模块 / 页面一律经本模块组装地址，**禁止自拼前缀**）：
 * - **平台服务**：`/api/{service_key}/v1/...`——网关按服务目录生成外部路由（重写为服务内 `/api/v1`）；
 *   服务键与后端服务目录同源，**运行期以目录快照派生**（`catalog/lookup`），未加载时按形态校验并保留
 *   编译期基线清单 `SERVICE_KEYS`（对账基准）。
 * - **产品服务**：`/api/{product_key}/v1/{domain}/...`——网关只为产品服务生成**产品命名空间**路由，
 *   不为产品服务生成服务级路由；产品键**运行期取自目录快照**（`03_02`），前端不再维护手写清单，
 *   域段由**产品自持**（基座不维护产品内部域清单，避免双事实源）。
 *
 * 未加载目录时只校验**标识形态**（`IDENTIFIER_PATTERN`）：产品侧插件与单测可在目录就绪前取址，
 * 目录就绪后按目录严格判定。
 */

import { catalogState, derivedServiceKeys, productKeys } from '../catalog/lookup'
import { BaseError } from '../mechanisms/error'
import { ErrorCodes } from '../mechanisms/error-codes'

/** 服务键（运行期取自目录快照；类型放宽为字符串，校验在运行期）。 */
export type ServiceKey = string

/** 编译期服务键基线（未加载目录时的回退与「目录派生一致性」对账基准；9 个已启用平台服务）。 */
export const SERVICE_KEYS: readonly ServiceKey[] = [
  'platform',
  'identity',
  'tenant',
  'file',
  'notification',
  'search',
  'ai',
  'report',
  'txn',
]

/** 产品键（运行期取自目录快照；类型放宽为字符串，校验在运行期）。 */
export type ProductKey = string

/** 外部路径版本段。 */
export const API_VERSION_SEGMENT = 'v1'

/** 标识形态（服务键与产品键共用：小写字母开头，可含数字与连字符）。 */
export const IDENTIFIER_PATTERN = /^[a-z][a-z0-9-]*$/

/** 产品域段格式（产品服务内部域：小写字母开头，可含数字 / 连字符 / 下划线）。 */
const PRODUCT_DOMAIN_PATTERN = /^[a-z][a-z0-9_-]*$/

/**
 * 服务键判定（未加载目录按形态放行，已加载按目录严格判定）。
 *
 * @param value 待判定值。
 * @returns 是否为可用服务键。
 */
export function isServiceKey(value: unknown): value is ServiceKey {
  if (typeof value !== 'string' || !IDENTIFIER_PATTERN.test(value)) {
    return false
  }
  if (catalogState() !== 'ready') {
    return true
  }
  return derivedServiceKeys().includes(value)
}

/**
 * 产品键判定（未加载目录按形态放行，已加载按目录严格判定）。
 *
 * @param value 待判定值。
 * @returns 是否为可用产品键。
 */
export function isProductKey(value: unknown): value is ProductKey {
  if (typeof value !== 'string' || !IDENTIFIER_PATTERN.test(value)) {
    return false
  }
  if (catalogState() !== 'ready') {
    return true
  }
  return productKeys().includes(value)
}

/**
 * 路径归一（去首部斜杠、折叠重复斜杠；查询串与深层路径原样保留）。
 *
 * @param path 资源子路径。
 * @returns 归一后的路径。
 */
function normalizePath(path: string): string {
  return path.replace(/^\/+/, '').replace(/\/{2,}/g, '/')
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
  const normalized = normalizePath(path)
  return normalized === '' ? prefix : `${prefix}/${normalized}`
}

/**
 * 产品域段归一与校验（产品自持域：`org` / `sup` / `cus` / `mat` 等）。
 *
 * @param domain 域段（可带首尾 `/`，去空白后判定）。
 * @returns 归一后的域段。
 * @throws BaseError 域段缺失或格式非法（`CAPABILITY_VIOLATION`，参数段位）。
 */
export function productDomain(domain: string): string {
  const segment = normalizePath(String(domain).trim()).replace(/\/+$/, '')
  if (!PRODUCT_DOMAIN_PATTERN.test(segment)) {
    throw new BaseError(ErrorCodes.CAPABILITY_VIOLATION, `非法的产品域段：${String(domain)}`)
  }
  return segment
}

/**
 * 产品命名空间前缀（`/api/{product}/v1/{domain}`）。
 *
 * @param product 产品键。
 * @param domain 域段（产品服务内部域）。
 * @returns 外部产品域前缀。
 * @throws BaseError 未登记的产品键 / 域段非法（`CAPABILITY_VIOLATION`，参数段位）。
 */
export function productPrefix(product: ProductKey, domain: string): string {
  if (!isProductKey(product)) {
    throw new BaseError(ErrorCodes.CAPABILITY_VIOLATION, `未登记的产品键：${String(product)}`)
  }
  return `/api/${product}/${API_VERSION_SEGMENT}/${productDomain(domain)}`
}

/**
 * 产品段 URL 组装（`/api/{product}/v1/{domain}{path}`）。
 *
 * 路径归一与服务通道同口径。
 *
 * @param product 产品键。
 * @param domain 域段（产品服务内部域）。
 * @param path 资源子路径（可带或不带首部 `/`；缺省空）。
 * @returns 外部请求地址。
 * @throws BaseError 未登记的产品键 / 域段非法（`CAPABILITY_VIOLATION`，参数段位）。
 */
export function productUrl(product: ProductKey, domain: string, path = ''): string {
  const prefix = productPrefix(product, domain)
  const normalized = normalizePath(path)
  return normalized === '' ? prefix : `${prefix}/${normalized}`
}
