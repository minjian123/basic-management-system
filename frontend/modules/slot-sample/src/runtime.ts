/**
 * 模块运行期派生状态与宿主能力持有（宿主注入上下文的**只读消费**结果）。
 *
 * **具名插槽上下文来源约定**：宿主页把作用实体标识放**路由参数**（如 `/sys/users/:id`），
 * 区域件经**宿主注入的 `router`（只读）**读取当前路由参数——模块不直连宿主实例、不新增契约通道。
 */

import type { ModuleApi, ModuleHostContext } from '@bms/core'

/** 宿主注入路由实例的只读消费面（仅取当前路由参数）。 */
interface HostRouteLike {
  /** 当前路由（响应式引用面）。 */
  currentRoute?: { value?: { params?: Record<string, unknown> } }
}

/** 模块运行期状态（只读快照派生）。 */
export interface SlotSampleRuntimeState {
  /** 宿主注入的权限码数量（只读快照）。 */
  permissionCount: number
}

/** 当前状态（初始为空上下文口径）。 */
let state: SlotSampleRuntimeState = { permissionCount: 0 }
/** 宿主注入的路由实例（只读；未注入为 `undefined`）。 */
let hostRouter: HostRouteLike | undefined
/** 宿主注入的请求能力（未注入为 `undefined`）。 */
let hostApi: ModuleApi | undefined

/**
 * 依据宿主上下文计算并缓存运行期状态（同时记录只读路由与请求能力）。
 *
 * @param context 宿主注入上下文（只读快照）。
 * @returns 计算后的状态。
 */
export function applyHostContext(context: ModuleHostContext): SlotSampleRuntimeState {
  const codes = Array.isArray(context.user)
    ? context.user.filter((item): item is string => typeof item === 'string')
    : []
  state = { permissionCount: codes.length }
  hostRouter = context.router as HostRouteLike | undefined
  hostApi = context.api
  return state
}

/** 读取当前运行期状态（只读）。 */
export function slotSampleRuntime(): SlotSampleRuntimeState {
  return state
}

/** 宿主请求能力（未注入返回 `undefined`）。 */
export function hostApiOf(): ModuleApi | undefined {
  return hostApi
}

/**
 * 当前宿主页的作用实体标识（路由参数 `id`）。
 *
 * @returns 实体标识；宿主未注入路由 / 无参数时返回空串（调用方降级不请求）。
 */
export function currentEntityId(): string {
  const params = hostRouter?.currentRoute?.value?.params
  const value = params === undefined ? undefined : params.id
  if (value === undefined || value === null) {
    return ''
  }
  return typeof value === 'string' ? value : String(value)
}
