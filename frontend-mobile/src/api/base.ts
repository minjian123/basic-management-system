/** 模块 API 基类：统一路径前缀与请求方法封装（复用 http.ts 的 request<T> 统一响应解析）。 */

import type { AxiosRequestConfig } from 'axios'

import { request } from './http'

export class BaseApi {
  private readonly basePath: string

  constructor(basePath: string) {
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
