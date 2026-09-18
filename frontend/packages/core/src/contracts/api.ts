/**
 * 模块 API 契约基类（纯 TS）：路径前缀 / 请求方法 / 自动幂等键。
 *
 * 实际请求执行（实例 / 拦截器 / 401）由宿主请求层注入（`02_06`），核心不依赖请求库。
 */

import { BaseObject } from '../base/BaseObject'

/** HTTP 方法。 */
export type HttpMethod = 'GET' | 'POST' | 'PUT' | 'PATCH' | 'DELETE'

/** 模块 API 基类（抽象）。 */
export abstract class BaseApi extends BaseObject {
  /** 模块路径前缀（如 `/api/v1/users`）。 */
  abstract readonly pathPrefix: string

  /**
   * 拼模块内子路径。
   *
   * @param sub 以 `/` 开头的子路径。
   */
  protected path(sub: string): string {
    return `${this.pathPrefix}${sub}`
  }

  /**
   * 生成写接口幂等键（宿主可覆写为服务端要求的口径）。
   */
  createIdempotencyKey(): string {
    return `${this.pathPrefix}:${Date.now()}:${Math.random().toString(36).slice(2)}`
  }
}
