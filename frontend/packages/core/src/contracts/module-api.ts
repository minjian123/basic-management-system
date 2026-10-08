/**
 * 模块请求能力契约（框架无关）：模块与宿主之间的**上层请求契约**。
 *
 * 模块按「服务键 + 资源子路径」调用（**平台服务**）或经**产品域作用域**按「产品键 + 域 + 资源子路径」调用
 * （**产品服务**，`ModuleApi.product()`）；前缀组装、凭据注入、统一响应解包、401 静默刷新与重放
 * 一律由宿主请求层处理（模块**不接触凭据、不感知服务寻址**，且不得自建 HTTP 客户端、不得自拼前缀）。
 *
 * 分层分工：`contracts/request.ts` 的 `RequestAdapter` / `RequestConfig` 是**核心 ↔ 宿主**的底层契约；
 * 本契约是**模块 ↔ 宿主**的上层契约，实现入口见能力基类 `BaseModuleApi`（`capabilities/module-api.ts`）。
 */

import type { HttpMethod } from './api'
import type { ProductKey, ServiceKey } from './service-endpoint'

/** 模块请求入参（按服务键 + 资源子路径；不含服务前缀与凭据类参数）。 */
export interface ModuleApiRequest {
  /** HTTP 方法。 */
  method: HttpMethod
  /** 服务键（未登记的服务键由 `serviceUrl` 抛错，不静默放行）。 */
  service: ServiceKey
  /** 资源子路径（缺省为服务前缀本身；可带或不带首部 `/`）。 */
  path?: string
  /** 查询参数。 */
  params?: Record<string, unknown>
  /** 请求体。 */
  data?: unknown
  /** 附加请求头（不得覆盖鉴权头——宿主拦截器后置注入）。 */
  headers?: Record<string, string>
  /** 幂等键（写方法；`post` / `put` 由能力基类按宿主口径生成，本字段供逃生口显式指定）。 */
  idempotencyKey?: string
}

/** 产品域请求入参（产品键与域段由 `ModuleApi.product()` 固定；不含前缀与凭据类参数）。 */
export interface ModuleApiScopeRequest {
  /** HTTP 方法。 */
  method: HttpMethod
  /** 资源子路径（相对产品域前缀；缺省为前缀本身）。 */
  path?: string
  /** 查询参数。 */
  params?: Record<string, unknown>
  /** 请求体。 */
  data?: unknown
  /** 附加请求头（不得覆盖鉴权头——宿主拦截器后置注入）。 */
  headers?: Record<string, string>
  /** 幂等键（写方法；便捷方法由能力基类按宿主口径生成，本字段供逃生口显式指定）。 */
  idempotencyKey?: string
}

/**
 * 产品域请求作用域（**产品服务**经产品命名空间 `/api/{产品键}/v1/{域}/...` 访问）。
 *
 * 语义与平台服务通道一致：模块不接触凭据、不感知寻址；域段由产品自持。
 */
export interface ModuleApiScope {
  /**
   * GET 请求。
   *
   * @param path 资源子路径（缺省为产品域前缀本身）。
   * @param params 查询参数。
   */
  get<T = unknown>(path?: string, params?: Record<string, unknown>): Promise<T>
  /**
   * POST 请求（自动生成幂等键）。
   *
   * @param path 资源子路径。
   * @param data 请求体。
   */
  post<T = unknown>(path?: string, data?: unknown): Promise<T>
  /**
   * PUT 请求（自动生成幂等键）。
   *
   * @param path 资源子路径。
   * @param data 请求体。
   */
  put<T = unknown>(path?: string, data?: unknown): Promise<T>
  /**
   * PATCH 请求（自动生成幂等键）。
   *
   * @param path 资源子路径。
   * @param data 请求体。
   */
  patch<T = unknown>(path?: string, data?: unknown): Promise<T>
  /**
   * DELETE 请求。
   *
   * @param path 资源子路径。
   * @param params 查询参数。
   */
  del<T = unknown>(path?: string, params?: Record<string, unknown>): Promise<T>
  /**
   * 通用请求（逃生口：特殊方法 / 附加头 / 显式幂等键）。
   *
   * @param config 请求入参。
   */
  request<T = unknown>(config: ModuleApiScopeRequest): Promise<T>
}

/** 模块请求能力（宿主注入；模块不感知服务寻址与凭据）。 */
export interface ModuleApi {
  /**
   * GET 请求。
   *
   * @param service 服务键。
   * @param path 资源子路径（缺省为服务前缀本身）。
   * @param params 查询参数。
   */
  get<T = unknown>(service: ServiceKey, path?: string, params?: Record<string, unknown>): Promise<T>
  /**
   * POST 请求（自动生成幂等键）。
   *
   * @param service 服务键。
   * @param path 资源子路径。
   * @param data 请求体。
   */
  post<T = unknown>(service: ServiceKey, path?: string, data?: unknown): Promise<T>
  /**
   * PUT 请求（自动生成幂等键）。
   *
   * @param service 服务键。
   * @param path 资源子路径。
   * @param data 请求体。
   */
  put<T = unknown>(service: ServiceKey, path?: string, data?: unknown): Promise<T>
  /**
   * DELETE 请求。
   *
   * @param service 服务键。
   * @param path 资源子路径。
   * @param params 查询参数。
   */
  del<T = unknown>(service: ServiceKey, path?: string, params?: Record<string, unknown>): Promise<T>
  /**
   * 通用请求（逃生口：特殊方法 / 附加头 / 显式幂等键）。
   *
   * @param config 请求入参。
   */
  request<T = unknown>(config: ModuleApiRequest): Promise<T>
  /**
   * 产品域作用域（**产品服务**经产品命名空间 `/api/{产品键}/v1/{域}/...` 访问）。
   *
   * 未登记的产品键 / 非法域段**立即抛错**（参数段位，零请求、零发地址）；域段由产品自持。
   *
   * @param product 产品键。
   * @param domain 域段（产品服务内部域）。
   */
  product(product: ProductKey, domain: string): ModuleApiScope
}
