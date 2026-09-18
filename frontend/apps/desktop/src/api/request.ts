/** 请求入口：统一经核心 `request`（适配器由宿主装配注入）。 */

import { request, type RequestConfig } from '@bms/core'

/** 路径前缀。 */
export const API_PREFIX = '/api/v1'

/**
 * GET 请求。
 *
 * @param url 地址（自动加前缀）。
 * @param params 查询参数。
 */
export function get<T>(url: string, params?: Record<string, unknown>): Promise<T> {
  return request<T>({ method: 'GET', url: `${API_PREFIX}${url}`, params })
}

/**
 * POST 请求（自动带幂等键）。
 *
 * @param url 地址。
 * @param data 请求体。
 */
export function post<T>(url: string, data?: unknown): Promise<T> {
  return request<T>({ method: 'POST', url: `${API_PREFIX}${url}`, data, idempotencyKey: newKey() })
}

/**
 * PUT 请求（自动带幂等键）。
 *
 * @param url 地址。
 * @param data 请求体。
 */
export function put<T>(url: string, data?: unknown): Promise<T> {
  return request<T>({ method: 'PUT', url: `${API_PREFIX}${url}`, data, idempotencyKey: newKey() })
}

/**
 * DELETE 请求。
 *
 * @param url 地址。
 * @param params 查询参数。
 */
export function del<T>(url: string, params?: Record<string, unknown>): Promise<T> {
  return request<T>({ method: 'DELETE', url: `${API_PREFIX}${url}`, params })
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
