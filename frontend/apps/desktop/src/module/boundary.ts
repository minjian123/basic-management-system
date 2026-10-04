/** 模块边界错误态：模块加载 / 渲染失败时由边界组件渲染兜底（复用 `03_02` 错误页）。 */

import { isPublicPath } from '@bms/core'
import { ref, type Ref } from 'vue'

/** 模块错误态。 */
export interface ModuleErrorState {
  /** 模块名。 */
  module: string
  /** 模块版本。 */
  version: string
  /** 失败原因。 */
  reason: string
}

const state = ref<ModuleErrorState | null>(null)

/**
 * 记录模块错误。
 *
 * @param error 错误态。
 */
export function setModuleError(error: ModuleErrorState): void {
  state.value = error
}

/** 清除模块错误（重试前调用）。 */
export function clearModuleError(): void {
  state.value = null
}

/** 模块错误态（响应式）。 */
export function useModuleError(): Ref<ModuleErrorState | null> {
  return state
}

/** 模块失败阻断判定入参。 */
export interface ModuleFailureScope {
  /** 失败态（无失败为 `null`）。 */
  failure: ModuleErrorState | null
  /** 目标路由路径（不含查询串）。 */
  path: string
  /** 目标路由归属模块名（平台自身路由为 `undefined`）。 */
  routeModule?: string | undefined
  /** 免登录 / 基础路由白名单（宿主口径：`resolvePublicPaths()`）。 */
  publicPaths: readonly string[]
}

/**
 * 判定模块失败是否阻断目标路由（需求 01-7）。
 *
 * 口径：模块**加载 / 清单失败**只阻断**归属该失败模块**的路由；`/login`、`/403`、`/404`、`/500` 等
 * 免登录与基础路由（`DEFAULT_PUBLIC_PATHS`）与平台自身路由**不受影响**——模块产物服务不可用时仍能
 * 正常登录、正常看到错误页。当前路由**自身渲染失败**不属本判定（由边界组件本地标记承载，保持
 * 「渲染错误页 + 重试」既有行为）。
 *
 * @param input 判定入参。
 * @returns 是否阻断（true 时渲染模块错误页）。
 */
export function blocksModuleFailure(input: ModuleFailureScope): boolean {
  if (input.failure === null) {
    return false
  }
  if (isPublicPath(input.path, input.publicPaths)) {
    return false
  }
  return input.routeModule !== undefined && input.routeModule === input.failure.module
}
