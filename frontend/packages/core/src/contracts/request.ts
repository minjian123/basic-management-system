/**
 * 请求适配契约（框架无关）：统一响应 / 分页响应 / 适配器接口。
 *
 * 实际请求实现（Axios 实例、拦截器、401 刷新、提示注入）由宿主请求层注入；
 * 未注入适配器时 `request()` 抛 `BaseError(19001)`（占位不请求）。
 */

import { BaseError } from '../mechanisms/error'
import { ErrorCodes } from '../mechanisms/error-codes'
import type { HttpMethod } from './api'

/** 统一响应。 */
export interface ApiResponse<T = unknown> {
  /** 业务码。 */
  code: number
  /** 消息。 */
  message: string
  /** 数据。 */
  data: T
}

/** 分页响应。 */
export interface PageResponse<T = unknown> {
  /** 列表。 */
  list: T[]
  /** 总条数。 */
  total: number
  /** 页码。 */
  page: number
  /** 页长。 */
  size: number
}

/** 请求配置。 */
export interface RequestConfig {
  /** 方法。 */
  method: HttpMethod
  /** 地址。 */
  url: string
  /** 查询参数。 */
  params?: Record<string, unknown>
  /** 请求体。 */
  data?: unknown
  /** 附加请求头。 */
  headers?: Record<string, string>
  /** 幂等键（写方法）。 */
  idempotencyKey?: string
}

/** 请求适配器（宿主实现）。 */
export interface RequestAdapter {
  /** 执行请求并返回业务数据。 */
  request<T>(config: RequestConfig): Promise<T>
}

let adapter: RequestAdapter | undefined

/**
 * 注入请求适配器（宿主装配期调用）。
 *
 * @param next 适配器。
 */
export function configureRequestAdapter(next: RequestAdapter): void {
  adapter = next
}

/** 读取当前请求适配器。 */
export function getRequestAdapter(): RequestAdapter | undefined {
  return adapter
}

/**
 * 执行请求（经注入适配器；未注入则抛 `BaseError(NOT_IMPLEMENTED)`）。
 *
 * @param config 请求配置。
 */
export async function request<T>(config: RequestConfig): Promise<T> {
  if (adapter === undefined) {
    throw new BaseError(ErrorCodes.NOT_IMPLEMENTED, '请求适配器未注入')
  }
  return adapter.request<T>(config)
}
