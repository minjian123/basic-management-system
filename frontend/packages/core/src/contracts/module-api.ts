/**
 * 模块请求能力契约（框架无关）：模块与宿主之间的**上层请求契约**。
 *
 * 模块按「服务键 + 资源子路径」调用；服务前缀组装、凭据注入、统一响应解包、401 静默刷新与重放
 * 一律由宿主请求层处理（模块**不接触凭据、不感知服务寻址**，且不得自建 HTTP 客户端）。
 *
 * 分层分工：`contracts/request.ts` 的 `RequestAdapter` / `RequestConfig` 是**核心 ↔ 宿主**的底层契约；
 * 本契约是**模块 ↔ 宿主**的上层契约，实现入口见能力基类 `BaseModuleApi`（`capabilities/module-api.ts`）。
 */

import type { HttpMethod } from './api'
import type { ServiceKey } from './service-endpoint'

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
}
