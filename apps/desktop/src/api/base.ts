/**
 * 模块 API 基类：统一路径前缀与请求方法封装（经 `request<T>` 解包，禁止裸用 axios）。
 *
 * 写方法（POST / PUT / DELETE）未显式给幂等键时**自动生成** `Idempotency-Key`；
 * 请求选项（`silent` / `raw` / `timeout` / `signal` / `idempotencyKey`）透传。
 */

import { BaseFrontend, type FrontendBaseOptions } from '@bms/core'

import { hostBaseOptions } from '@/adapters/host-base'

import { createRequestId } from './http'
import { request, type RequestOptions } from './request'

/** 写方法（自动幂等键） */
const WRITE_METHODS = new Set(['POST', 'PUT', 'DELETE'])

/** BaseApi 请求选项（`RequestOptions` 别名，供模块 API 签名引用） */
export type BaseApiRequestOptions = RequestOptions

/** BaseApi 构造选项（根系选项 + 实例标识） */
export interface BaseApiOptions extends FrontendBaseOptions {
  /** 实例标识（日志与上报定位；缺省取模块路径前缀） */
  identifier?: string
}

export class BaseApi extends BaseFrontend {
  /** 实例标识（日志与错误上报定位） */
  readonly identifier: string
  private readonly basePath: string

  constructor(basePath: string, options: BaseApiOptions = {}) {
    // 根系接入：ns 固定 api，identifier 取模块路径前缀（日志与错误上报定位）
    const identifier = options.identifier ?? basePath
    const ns = options.ns ?? 'api'
    super({ ...hostBaseOptions({ ns, identifier }), ...options })
    this.identifier = identifier
    this.basePath = basePath
  }

  /** 补默认选项（写方法自动生成幂等键；显式传入优先） */
  private withOptions(method: string, options?: RequestOptions): RequestOptions | undefined {
    if (!WRITE_METHODS.has(method)) {
      return options
    }
    if (options?.idempotencyKey) {
      return options
    }
    return { ...(options ?? {}), idempotencyKey: createRequestId() }
  }

  protected get<T>(url = '', params?: object, options?: RequestOptions): Promise<T> {
    return request<T>({ url: `${this.basePath}${url}`, method: 'GET', params }, options)
  }

  protected post<T>(url = '', data?: unknown, options?: RequestOptions): Promise<T> {
    const finalOptions = this.withOptions('POST', options)
    return request<T>({ url: `${this.basePath}${url}`, method: 'POST', data }, finalOptions)
  }

  protected put<T>(url = '', data?: unknown, options?: RequestOptions): Promise<T> {
    const finalOptions = this.withOptions('PUT', options)
    return request<T>({ url: `${this.basePath}${url}`, method: 'PUT', data }, finalOptions)
  }

  protected delete<T>(url = '', params?: object, options?: RequestOptions): Promise<T> {
    const finalOptions = this.withOptions('DELETE', options)
    return request<T>({ url: `${this.basePath}${url}`, method: 'DELETE', params }, finalOptions)
  }
}
