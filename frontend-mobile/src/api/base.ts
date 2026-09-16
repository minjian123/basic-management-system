/** 模块 API 基类：统一路径前缀与请求方法封装（复用 http.ts 的 request<T> 统一响应解析）。 */

import type { AxiosRequestConfig } from 'axios'

import { BaseFrontend, type FrontendBaseOptions } from '@/base/BaseFrontend'

import { request } from './http'

export class BaseApi extends BaseFrontend {
  private readonly basePath: string

  constructor(basePath: string, options: FrontendBaseOptions = {}) {
    // 根系接入：ns 固定 api，identifier 取模块路径前缀（日志与错误上报定位）
    super({ ns: 'api', identifier: basePath, ...options })
    this.basePath = basePath
  }

  protected get<T>(url = '', config?: AxiosRequestConfig): Promise<T> {
    return request<T>({ ...config, url: `${this.basePath}${url}`, method: 'GET' })
  }

  protected post<T>(url = '', data?: unknown, config?: AxiosRequestConfig): Promise<T> {
    return request<T>({ ...config, url: `${this.basePath}${url}`, method: 'POST', data })
  }

  protected put<T>(url = '', data?: unknown, config?: AxiosRequestConfig): Promise<T> {
    return request<T>({ ...config, url: `${this.basePath}${url}`, method: 'PUT', data })
  }

  protected delete<T>(url = '', config?: AxiosRequestConfig): Promise<T> {
    return request<T>({ ...config, url: `${this.basePath}${url}`, method: 'DELETE' })
  }
}
