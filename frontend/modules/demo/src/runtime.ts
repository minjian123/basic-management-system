/**
 * 演示模块运行期状态与宿主请求能力持有（宿主注入上下文的**只读消费**结果）。
 *
 * `setup(context)` 时记录注入项；页面经 `loadHostUserSummary()` 使用宿主请求能力取真实数据。
 * 未注入请求能力（独立预览 / 未接线）时返回 `undefined`，由调用方降级（不假定存在）；模块不直连
 * 宿主 store / router、不持久化、不自建 HTTP（隔离约定，见任务 03_01 / 06_02）。
 */

import type { identity } from '@bms/api-types'
import type { ModuleApi, ModuleHostContext } from '@bms/core'

/** 当前用户概要（**生成类型**：不手写重复定义；与宿主 `/auth/me` 同字段同语义）。 */
export type HostUserSummary = identity.components['schemas']['UserSummary']

/** 模块运行期状态。 */
export interface DemoRuntimeState {
  /** 宿主注入的权限码数量（只读快照）。 */
  permissionCount: number
}

/** 当前状态（初始为空上下文口径）。 */
let state: DemoRuntimeState = { permissionCount: 0 }
/** 宿主注入的请求能力（未注入为 `undefined`）。 */
let hostApi: ModuleApi | undefined
/** 宿主注入的导航能力（未注入为 `undefined`；**只取 `push`**，不持有宿主 router 实例）。 */
let hostRouter: DemoHostRouter | undefined

/** 宿主导航能力的最小面（只用 `push`；`context.router` 为 `unknown`，须收窄后使用）。 */
export interface DemoHostRouter {
  /** 跳转。 */
  push?: (to: string) => unknown
}

/**
 * 收窄宿主注入的路由对象（只认 `push` 函数；其余形态视为未注入，由调用方降级）。
 *
 * @param router 宿主注入的路由对象（`unknown`）。
 * @returns 最小导航面；不可用时返回 `undefined`。
 */
function narrowRouter(router: unknown): DemoHostRouter | undefined {
  if (typeof router !== 'object' || router === null) {
    return undefined
  }
  const push = (router as { push?: unknown }).push
  return typeof push === 'function' ? { push: push as (to: string) => unknown } : undefined
}

/**
 * 依据宿主上下文计算并缓存运行期状态（同时记录宿主请求与导航能力）。
 *
 * @param context 宿主注入上下文（只读快照）。
 * @returns 计算后的状态。
 */
export function applyHostContext(context: ModuleHostContext): DemoRuntimeState {
  const codes = Array.isArray(context.user) ? context.user.filter((item): item is string => typeof item === 'string') : []
  state = { permissionCount: codes.length }
  hostApi = context.api
  hostRouter = narrowRouter(context.router)
  return state
}

/** 宿主导航能力（未注入返回 `undefined`）。 */
export function hostRouterOf(): DemoHostRouter | undefined {
  return hostRouter
}

/** 读取当前运行期状态（只读）。 */
export function demoRuntime(): DemoRuntimeState {
  return state
}

/** 宿主请求能力（未注入返回 `undefined`）。 */
export function hostApiOf(): ModuleApi | undefined {
  return hostApi
}

/**
 * 经宿主请求能力取当前用户概要（真实端点：identity `GET /auth/me`）。
 *
 * 凭据注入、统一响应解包与 401 静默刷新 / 重放由宿主请求层处理——模块**无任何 401 逻辑**。
 *
 * @returns 当前用户概要；未注入请求能力时返回 `undefined`（调用方降级）。
 */
export async function loadHostUserSummary(): Promise<HostUserSummary | undefined> {
  const api = hostApi
  if (api === undefined) {
    return undefined
  }
  return api.get<HostUserSummary>('identity', '/auth/me')
}
