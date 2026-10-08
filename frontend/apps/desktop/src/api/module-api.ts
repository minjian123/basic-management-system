/**
 * 模块请求能力宿主实现：把注入给模块的请求能力（服务键 + 路径）接到宿主请求层。
 *
 * 服务前缀组装与请求执行由核心 `BaseModuleApi` 组合完成（经核心 `request()` 走**已注入的适配器**）；
 * 令牌注入、统一响应解包、401 静默刷新与重放全部在宿主请求层（`api/http.ts`）——模块不接触凭据，
 * 也不感知服务寻址（《架构设计 · 前端模块契约》「请求能力」节）。宿主只提供**幂等键口径**这一实现点。
 */

import { BaseModuleApi, type ModuleApi } from '@bms/core'

import { newKey } from './request'

/** 宿主实现的模块请求能力（幂等键沿用宿主请求层口径）。 */
export class HostModuleApi extends BaseModuleApi {
  /**
   * 生成写方法幂等键（宿主口径：`<前缀>:<时间戳>:<随机>`）。
   *
   * @param target 寻址主体（平台服务为服务键；产品服务为 `产品键:域`）。
   * @param path 资源子路径。
   */
  createIdempotencyKey(target: string, path: string): string {
    return newKey(`${target}:${path}`)
  }
}

/**
 * 构造模块请求能力（宿主入口装配一次，注入全部模块）。
 *
 * @returns 请求能力实例。
 */
export function createModuleApi(): ModuleApi {
  return new HostModuleApi()
}
