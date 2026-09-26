/** 请求入口：统一经核心 `request`（适配器由宿主装配注入）；地址经「域 → 服务前缀」单一来源组装。 */

import { request, serviceUrl, type RequestConfig, type ServiceKey } from '@bms/core'

/**
 * 服务段地址组装（`/api/{service}/v1{path}`）。
 *
 * 唯一入口：模块 / 页面不得自拼服务前缀（《前端开发规范》§11「多服务寻址」）。
 *
 * @param service 服务键。
 * @param path 资源子路径（可带或不带首部 `/`；缺省空）。
 */
export function apiUrl(service: ServiceKey, path = ''): string {
  return serviceUrl(service, path)
}

/**
 * GET 请求。
 *
 * @param service 服务键。
 * @param path 资源子路径。
 * @param params 查询参数。
 */
export function get<T>(service: ServiceKey, path: string, params?: Record<string, unknown>): Promise<T> {
  return request<T>({ method: 'GET', url: apiUrl(service, path), params })
}

/**
 * POST 请求（自动带幂等键）。
 *
 * @param service 服务键。
 * @param path 资源子路径。
 * @param data 请求体。
 */
export function post<T>(service: ServiceKey, path: string, data?: unknown): Promise<T> {
  return request<T>({ method: 'POST', url: apiUrl(service, path), data, idempotencyKey: newKey() })
}

/**
 * PUT 请求（自动带幂等键）。
 *
 * @param service 服务键。
 * @param path 资源子路径。
 * @param data 请求体。
 */
export function put<T>(service: ServiceKey, path: string, data?: unknown): Promise<T> {
  return request<T>({ method: 'PUT', url: apiUrl(service, path), data, idempotencyKey: newKey() })
}

/**
 * DELETE 请求。
 *
 * @param service 服务键。
 * @param path 资源子路径。
 * @param params 查询参数。
 */
export function del<T>(service: ServiceKey, path: string, params?: Record<string, unknown>): Promise<T> {
  return request<T>({ method: 'DELETE', url: apiUrl(service, path), params })
}

/**
 * 生成写接口幂等键。
 *
 * @param prefix 前缀（便于排障）。
 */
export function newKey(prefix = 'k'): string {
  return `${prefix}:${Date.now()}:${Math.random().toString(36).slice(2)}`
}

export type { RequestConfig }
