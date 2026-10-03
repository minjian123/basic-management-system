/**
 * 请求能力基类（抽象）：模块经宿主注入的请求能力按「服务键 + 路径」访问后端。
 *
 * - **凭据不下发**：服务前缀组装、令牌注入、统一响应解包、401 静默刷新与重放由宿主请求层处理；
 * - **请求执行经核心 `request()`**：适配器未注入时抛 `BaseError(NOT_IMPLEMENTED)`（占位零请求）；
 * - **幂等键口径是宿主实现点**：`createIdempotencyKey` 由宿主子类覆写（服务端要求可变）；
 * - **未注入即降级**：模块缺省上下文自行降级，不假定请求能力存在。
 */

import { request } from '../contracts/request'
import { serviceUrl } from '../contracts/service-endpoint'

import { BasePlaceholderState } from './placeholder-state'

import type { ModuleApi, ModuleApiRequest } from '../contracts/module-api'
import type { ServiceKey } from '../contracts/service-endpoint'

/** 请求能力基类（抽象）。 */
export abstract class BaseModuleApi extends BasePlaceholderState implements ModuleApi {
  /** 能力键。 */
  readonly identifier: string = 'module-api'

  /**
   * GET 请求。
   *
   * @param service 服务键。
   * @param path 资源子路径（缺省为服务前缀本身）。
   * @param params 查询参数。
   */
  async get<T = unknown>(service: ServiceKey, path = '', params?: Record<string, unknown>): Promise<T> {
    return this.request<T>({ method: 'GET', service, path, params })
  }

  /**
   * POST 请求（自动生成幂等键）。
   *
   * @param service 服务键。
   * @param path 资源子路径。
   * @param data 请求体。
   */
  async post<T = unknown>(service: ServiceKey, path = '', data?: unknown): Promise<T> {
    return this.request<T>({
      method: 'POST',
      service,
      path,
      data,
      idempotencyKey: this.createIdempotencyKey(service, path),
    })
  }

  /**
   * PUT 请求（自动生成幂等键）。
   *
   * @param service 服务键。
   * @param path 资源子路径。
   * @param data 请求体。
   */
  async put<T = unknown>(service: ServiceKey, path = '', data?: unknown): Promise<T> {
    return this.request<T>({
      method: 'PUT',
      service,
      path,
      data,
      idempotencyKey: this.createIdempotencyKey(service, path),
    })
  }

  /**
   * DELETE 请求。
   *
   * @param service 服务键。
   * @param path 资源子路径。
   * @param params 查询参数。
   */
  async del<T = unknown>(service: ServiceKey, path = '', params?: Record<string, unknown>): Promise<T> {
    return this.request<T>({ method: 'DELETE', service, path, params })
  }

  /**
   * 通用请求（服务键 + 路径 → 外部地址；执行交核心适配器）。
   *
   * @param config 请求入参。
   */
  async request<T = unknown>(config: ModuleApiRequest): Promise<T> {
    return request<T>({
      method: config.method,
      url: serviceUrl(config.service, config.path ?? ''),
      params: config.params,
      data: config.data,
      headers: config.headers,
      idempotencyKey: config.idempotencyKey,
    })
  }

  /**
   * 生成写方法幂等键（**宿主实现点**：口径随服务端要求可变）。
   *
   * @param service 服务键。
   * @param path 资源子路径。
   */
  abstract createIdempotencyKey(service: ServiceKey, path: string): string
}
