/** Axios 基线：请求/响应拦截器 + 统一响应解析（token 与 401 处理留阶段二）。 */

import axios, { type AxiosInstance, type AxiosRequestConfig } from 'axios'

import type { ApiResponse } from './types'

/** 应用信息（backend 根信息接口，开发期经 Vite /info 代理重写）。 */
export interface AppInfo {
  name: string
  version: string
}

const appInfoClient: AxiosInstance = axios.create({ timeout: 10_000 })

export const http: AxiosInstance = axios.create({
  baseURL: import.meta.env.VITE_API_BASE ?? '/api',
  timeout: 10_000,
})

http.interceptors.request.use((config) => {
  // TODO(阶段二): 注入 Authorization: Bearer <token>（token 仅存内存 Pinia）
  return config
})

http.interceptors.response.use(
  (response) => response,
  (error: unknown) => {
    if (axios.isAxiosError(error) && error.response?.status === 401) {
      // TODO(阶段二): 会话失效处理（刷新 token / 跳转登录）
    }
    return Promise.reject(error)
  },
)

/** 发起业务请求并解开统一响应（code≠0 拒绝）。 */
export async function request<T>(config: AxiosRequestConfig): Promise<T> {
  const response = await http.request<ApiResponse<T>>(config)
  const payload = response.data
  if (payload.code !== 0) {
    // TODO(阶段二): 统一错误提示（按 error.{code} i18n 映射，缺失回退 message）
    return Promise.reject(new Error(payload.message || `业务错误 ${payload.code}`))
  }
  return payload.data
}

/** 获取 backend 应用信息（开发期 /info 代理重写至 backend 根）。 */
export async function fetchAppInfo(): Promise<AppInfo> {
  const response = await appInfoClient.get<ApiResponse<AppInfo>>('/info')
  return response.data.data
}
